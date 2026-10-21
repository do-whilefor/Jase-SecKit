package board

import (
	"encoding/json"
	"errors"
	"pwnmesh/internal/board/model"
	"slices"
)

const MaxExecuteUpdateBytes = model.MaxExecuteUpdateBytes

const executeUpdateReadMore = `Read: read_graph sections facts/relations with dependency or correction IDs; evidence by one fact ID.
Version: Reads use current shared state; the runtime fences transport pages within each call. Retry affected reads after state_changed.
Meaning: Omission is not absence.`

const executeDiscoveryReadMore = `Meaning: Advisory links at this state version only; path records and corrections may be absent.
Read: Before combining observations, use read_graph section:related with this step_id; compare scope, time and original evidence.
Scope: Original dependencies and permissions are unchanged.`

// ExecuteUpdateCursor acknowledges only corrections to this run's registered
// Step.From. It is not an acknowledgement that the whole graph was read.
type ExecuteUpdateCursor = model.ExecuteUpdateCursor

type ExecuteUpdates = model.ExecuteUpdates

// BuildExecuteUpdates uses one current State and its transaction's event index.
// The caller derives sources and the initial revision from the immutable Job.
// Incomplete responses retain the old cursor, including when they contain a
// useful current review. No evidence or relation reason is silently truncated.
func BuildExecuteUpdates(current State, cursor ExecuteUpdateCursor, sources []string, events []StateChange, maxBytes int) (*ExecuteUpdates, error) {
	if maxBytes <= 0 || maxBytes > MaxExecuteUpdateBytes {
		maxBytes = MaxExecuteUpdateBytes
	}
	out, err := buildDependencyUpdates(current, cursor, sources, events, maxBytes)
	if err != nil {
		return nil, err
	}
	// Exact correction reviews remain pinned for the run. Keep optional
	// discovery separate so later graph changes can retire its advisory pin.
	if len(out.Facts)+len(out.Relations)+len(out.InvalidSources) > 0 {
		return out, nil
	}
	// A missing event range cannot establish which observations are new.
	// Advisory discovery never reduces the mandatory correction budget or
	// changes its completeness, omission counters or cursor semantics.
	if out.Rebased || out.PendingReason == "event_gap" || out.PendingReason == "unknown_event" {
		return out, nil
	}
	newFacts := map[string]bool{}
	for _, event := range events {
		if event.Op == "fact" {
			newFacts[event.ID] = true
		}
	}
	for _, fact := range out.Facts {
		delete(newFacts, fact.ID)
	}
	for _, id := range sources {
		delete(newFacts, id)
	}
	if len(newFacts) == 0 {
		return out, nil
	}
	query := model.RelatedQuery{IDs: sources, AssetIDs: current.AssetIDs("step", cursor.StepID)}
	if len(query.IDs)+len(query.AssetIDs) == 0 {
		return out, nil // No bound scope; never use the selector's planner default.
	}
	var candidates []model.RelatedFact
	for _, fact := range model.RankRelatedFacts(current, query) {
		if newFacts[fact.ID] && fact.RunID != cursor.RunID && fact.SourceStepID != cursor.StepID {
			candidates = append(candidates, fact)
			delete(newFacts, fact.ID)
		}
	}
	if len(candidates) == 0 {
		return out, nil
	}
	discovery := &model.ExecuteDiscovery{Facts: []model.RelatedFact{}, Omitted: len(candidates), ReadMore: executeDiscoveryReadMore}
	base, _ := json.Marshal(out)
	budget := min(maxBytes, len(base)+(4<<10))
	out.Discovery = discovery
	fits := func() bool {
		raw, err := json.Marshal(out)
		return err == nil && len(raw) <= budget
	}
	for _, fact := range candidates {
		if len(discovery.Facts) >= 8 {
			continue
		}
		discovery.Facts = append(discovery.Facts, fact)
		if !fits() {
			discovery.Facts = discovery.Facts[:len(discovery.Facts)-1]
			continue
		}
		discovery.Omitted--
	}
	// Even omission metadata is optional: a full correction response wins.
	if !fits() {
		out.Discovery = nil
	}
	return out, nil
}

func buildDependencyUpdates(current State, cursor ExecuteUpdateCursor, sources []string, events []StateChange, maxBytes int) (*ExecuteUpdates, error) {
	if cursor.ProjectID != current.Graph.Project.ID || cursor.Generation != current.Graph.Project.Generation || cursor.StepID == "" || cursor.RunID == "" || cursor.Revision < 0 || cursor.Revision > current.Revision {
		return nil, errors.New("execute updates: invalid cursor identity or revision")
	}
	if maxBytes <= 0 || maxBytes > MaxExecuteUpdateBytes {
		maxBytes = MaxExecuteUpdateBytes
	}
	version := DecisionStateVersion(current)
	out := &ExecuteUpdates{Version: 1, ExecuteUpdateCursor: cursor, FromRevision: cursor.Revision, ToRevision: current.Revision,
		StateVersion: version, Complete: true, InvalidSources: []string{}, Facts: []FactRecord{}, Relations: []FactRelation{}, Omitted: map[string]int{}}
	// Even a silent acknowledgement has a bound envelope. Check it before the
	// unrelated-event fast path, which does not enter record-budget assembly.
	envelope, err := json.Marshal(out)
	if err != nil {
		return nil, err
	}
	if len(envelope) > maxBytes {
		return nil, errors.New("execute updates: identity envelope exceeds budget")
	}
	pending := func(reason string) {
		out.Complete = false
		if out.PendingReason == "" {
			out.PendingReason = reason
		}
	}
	span := current.Revision - cursor.Revision
	// A long-lived Execute can outgrow the event page. Rebaseline only its
	// immutable dependency scope from this transaction's current state instead
	// of pretending that the truncated event history was read. Every causal
	// record must fit before the Worker may advance its identity-bound cursor.
	out.Rebased = span > model.MaxExecuteUpdateEvents
	if !out.Rebased && int64(len(events)) != span {
		pending("event_gap")
	}
	for i, event := range events {
		if out.Rebased {
			break
		}
		if event.Revision != cursor.Revision+int64(i)+1 || event.Revision > current.Revision || event.ID == "" {
			pending("event_gap")
		}
		switch event.Op {
		case "fact", "reopen", "finding", "goal", "step", "step_completed", "execution_failed", "complete", "hint", "fact_relation", "candidate", "curate", "curation_request", "dispute":
		default:
			pending("unknown_event")
		}
	}
	// Follow the same prerequisites as effective support, plus corrective
	// sources. Never expand unrelated raw observations from a common producer.
	const maxNodes = 256
	selected := map[string]bool{}
	queue := []string{}
	immutableInputs := map[string]bool{}
	if out.Rebased {
		for _, fact := range current.FactRecords {
			if (fact.ID == "origin" || fact.ID == "goal") && fact.Status == "input" && fact.Legacy && fact.SourceStepID == "" && len(fact.DerivedFrom)+len(fact.Evidence) == 0 {
				immutableInputs[fact.ID] = true
			}
		}
	}
	add := func(id string) {
		if selected[id] {
			return
		}
		if len(queue) >= maxNodes {
			out.Omitted["closure_frontier"]++
			pending("closure_limit")
			return
		}
		selected[id] = true
		queue = append(queue, id)
	}
	for _, id := range sources {
		if immutableInputs[id] {
			continue // Already retained in the registered immutable Job input.
		}
		add(id)
	}
	byTarget := map[string][]int{}
	dependencies := current.FactDependencies()
	for i, relation := range current.FactRelations {
		if executeCorrection(relation.Kind) {
			byTarget[relation.Target] = append(byTarget[relation.Target], i)
		}
	}
	for i := 0; i < len(queue); i++ {
		for _, source := range dependencies[queue[i]] {
			if source.ID == "origin" || source.ID == "goal" {
				continue // Immutable user inputs are already bound in the Job.
			}
			add(source.ID)
		}
		for _, index := range byTarget[queue[i]] {
			add(current.FactRelations[index].Source)
		}
	}
	relevant := out.Rebased || !out.Complete
	curated := slices.ContainsFunc(events, func(event StateChange) bool { return event.Op == "curate" })
	curationRelevant := curated && current.ValidateFactSources(sources, false) != nil
	for _, event := range events {
		// A curation batch can correct several facts atomically. Its single
		// event ID identifies the scan, not an individual target. Corrections
		// invalidate a source directly or through its accepted Step support.
		// If every source remains effective, this batch changed another scope;
		// resending unchanged evidence could needlessly exhaust the page budget.
		if selected[event.ID] || event.Op == "curate" && curationRelevant {
			relevant = true
		}
	}
	if !relevant {
		return out, nil
	}
	out.ReadMore = executeUpdateReadMore
	// Reserve space for all omission keys and a pending reason before adding
	// records. Never marshal the entire selected evidence set just to trim it.
	fits := func() bool {
		raw, err := json.Marshal(out)
		return err == nil && len(raw) <= maxBytes-192
	}
	seenSources := map[string]bool{}
	for _, id := range sources {
		if !seenSources[id] && current.ValidateFactSources([]string{id}, false) != nil {
			seenSources[id] = true
			out.InvalidSources = append(out.InvalidSources, id)
			if !fits() {
				out.InvalidSources = out.InvalidSources[:len(out.InvalidSources)-1]
				out.Omitted["invalid_sources"]++
				pending("context_budget")
			}
		}
	}
	for _, relation := range current.FactRelations {
		if executeCorrection(relation.Kind) && selected[relation.Target] && selected[relation.Source] {
			out.Relations = append(out.Relations, relation)
			if !fits() {
				out.Relations = out.Relations[:len(out.Relations)-1]
				out.Omitted["relations"]++
				pending("context_budget")
			}
		}
	}
	for _, fact := range current.FactRecords {
		if selected[fact.ID] {
			out.Facts = append(out.Facts, fact)
			delete(selected, fact.ID)
			if !fits() {
				out.Facts = out.Facts[:len(out.Facts)-1]
				out.Omitted["facts"]++
				pending("context_budget")
			}
		}
	}
	if len(selected) != 0 {
		out.Omitted["missing_facts"] = len(selected)
		pending("missing_fact")
	}
	// A caller may select a tiny custom budget. Even the envelope must fit;
	// returned records and their evidence otherwise remain exact.
	for {
		raw, err := json.Marshal(out)
		if err != nil {
			return nil, err
		}
		if len(raw) <= maxBytes {
			return out, nil
		}
		pending("context_budget")
		switch {
		case len(out.Facts) > 0:
			out.Facts = out.Facts[:len(out.Facts)-1]
			out.Omitted["facts"]++
		case len(out.Relations) > 0:
			out.Relations = out.Relations[:len(out.Relations)-1]
			out.Omitted["relations"]++
		case len(out.InvalidSources) > 0:
			out.InvalidSources = out.InvalidSources[:len(out.InvalidSources)-1]
			out.Omitted["invalid_sources"]++
		default:
			return nil, errors.New("execute updates: identity envelope exceeds budget")
		}
	}
}

func executeCorrection(kind string) bool {
	return kind == "refutes" || kind == "supersedes" || kind == "narrows"
}
