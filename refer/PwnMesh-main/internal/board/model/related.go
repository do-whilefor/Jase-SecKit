package model

import (
	"encoding/json"
	"slices"
	"sort"
	"strings"
	"unicode"
)

type RelatedQuery struct {
	StepID     string      `json:"step_id,omitempty"`
	IDs        []string    `json:"ids,omitempty"`
	AssetIDs   []string    `json:"asset_ids,omitempty"`
	Query      string      `json:"query,omitempty"`
	Limit      int         `json:"limit,omitempty"`
	Assessment *Assessment `json:"assessment,omitempty"`
	// Planner context supplies explicit fact/prose seeds alongside active claims.
	activeAssessments bool
}

// A path explains retrieval, never a new derivation, identity or conclusion.
type RelatedFact struct {
	FactRecord
	WhyRelated     []string `json:"why_related"`
	Path           []string `json:"path"`
	PathTruncated  bool     `json:"path_truncated,omitempty"`
	DetailsOmitted bool     `json:"details_omitted,omitempty"`
}

// RelatedStep preserves a prior assignment and outcome, not a reuse verdict.
type RelatedStep struct {
	ID                      string      `json:"id"`
	Status                  string      `json:"status"`
	Description             string      `json:"description"`
	DescriptionTruncated    bool        `json:"description_truncated,omitempty"`
	Reason                  string      `json:"reason,omitempty"`
	ReasonTruncated         bool        `json:"reason_truncated,omitempty"`
	Result                  string      `json:"result,omitempty"`
	Assessment              *Assessment `json:"assessment,omitempty"`
	AssessmentTruncated     bool        `json:"assessment_truncated,omitempty"`
	SupportValid            bool        `json:"support_valid"`
	Worker                  string      `json:"worker,omitempty"`
	LatestRunID             string      `json:"latest_run_id,omitempty"`
	DisputeID               string      `json:"dispute_id,omitempty"`
	MatchedAssetIDs         []string    `json:"matched_asset_ids,omitempty"`
	MatchedAssetsOmitted    int         `json:"matched_assets_omitted,omitempty"`
	MatchedAssessmentStepID string      `json:"matched_assessment_step_id,omitempty"`
	MatchedQueryTokens      []string    `json:"matched_query_tokens,omitempty"`
}

type RelatedContext struct {
	Facts      []RelatedFact         `json:"fact_records"`
	Relations  []FactRelation        `json:"fact_relations"`
	AssetEdges []AssetEdge           `json:"asset_edges,omitempty"`
	Judgments  []ContextOverviewNode `json:"judgments,omitempty"`
	Steps      []RelatedStep         `json:"steps,omitempty"`
	Omitted    map[string]int        `json:"omitted"`
	ReadMore   string                `json:"read_more"`
}

type relatedRank struct {
	fact                  RelatedFact
	score, depth, ordinal int
}

// RankRelatedFacts is shared by initial context, focused reads and advisory
// execution updates. It does not mutate support or restrict execution scope.
// Limit is applied by callers after ranking, allowing updates to filter new IDs.
func RankRelatedFacts(state State, request RelatedQuery) []RelatedFact {
	byID := make(map[string]FactRecord, len(state.FactRecords))
	ordinal := map[string]int{}
	for i, fact := range state.FactRecords {
		byID[fact.ID], ordinal[fact.ID] = fact, i
	}
	ranks := map[string]*relatedRank{}
	add := func(id, reason string, path []string, score, depth int) bool {
		fact, exists := byID[id]
		if !exists || fact.Status == "input" || id == "origin" || id == "goal" {
			return false
		}
		truncated := len(path) > 64
		if truncated {
			path = append(slices.Clone(path[:63]), id)
		}
		if rank := ranks[id]; rank != nil {
			if !slices.Contains(rank.fact.WhyRelated, reason) && len(rank.fact.WhyRelated) < 4 {
				rank.fact.WhyRelated = append(rank.fact.WhyRelated, reason)
			}
			if score < rank.score || score == rank.score && depth < rank.depth {
				rank.score, rank.depth, rank.fact.Path = score, depth, slices.Clone(path)
				rank.fact.PathTruncated = truncated
				return true
			}
			return false
		}
		ranks[id] = &relatedRank{RelatedFact{FactRecord: fact, WhyRelated: []string{reason}, Path: slices.Clone(path), PathTruncated: truncated}, score, depth, ordinal[id]}
		return true
	}
	query := request.Query
	defaultQuery := request.StepID == "" && len(request.IDs) == 0 && len(request.AssetIDs) == 0 && request.Query == "" && request.Assessment == nil
	assets := map[string][]string{}
	for _, id := range request.AssetIDs {
		assets[id] = []string{id}
	}
	seed := func(id, reason string, path []string) {
		add(id, reason, path, 0, 0)
		for _, assetID := range state.AssetIDs("fact", id) {
			assets[assetID] = append(slices.Clone(path), assetID)
		}
	}
	for _, id := range request.IDs {
		seed(id, "selected", []string{id})
	}
	for _, step := range state.Steps {
		if step.ID != request.StepID && !(defaultQuery && ActiveStepStatus(step.Status)) {
			continue
		}
		query += " " + step.Description
		if step.Assessment != nil {
			query += " " + step.Assessment.Claim
		}
		if step.ID == request.StepID && step.Result != nil {
			seed(*step.Result, "step_result", []string{step.ID, *step.Result})
		}
		for _, id := range step.From {
			seed(id, "prerequisite", []string{step.ID, id})
		}
		for _, upstream := range state.Steps {
			if slices.Contains(step.DependsOn, upstream.ID) && upstream.Result != nil {
				seed(*upstream.Result, "prerequisite", []string{step.ID, upstream.ID, *upstream.Result})
			}
		}
		for _, assetID := range state.AssetIDs("step", step.ID) {
			assets[assetID] = []string{step.ID, assetID}
		}
	}
	assessmentMatches := relatedAssessmentMatches(state, request)
	queryMatches := relatedStepQueryMatches(state, request.Query)
	stepPaths, assessmentKeys := map[string][]string{}, map[string]string{}
	for _, step := range state.Steps {
		if tokens := queryMatches[step.ID]; len(tokens) != 0 {
			stepPaths[step.ID] = []string{"query:" + tokens[0], step.ID}
			if step.Result != nil {
				add(*step.Result, "step_query_match", []string{"query:" + tokens[0], step.ID, *step.Result}, 35, 0)
			}
		}
		if request.StepID != "" && step.ID == request.StepID {
			stepPaths[step.ID] = []string{step.ID}
			if step.Assessment != nil {
				assessmentKeys[step.ID] = FindingIdentity(step.Assessment.Claim, step.Assessment.Scope)
			}
		}
		if seedID, matched := assessmentMatches[step.ID]; matched {
			if seedID == "" {
				seedID = "query:assessment"
			}
			stepPaths[step.ID] = []string{seedID, step.ID}
			assessmentKeys[step.ID] = FindingIdentity(step.Assessment.Claim, step.Assessment.Scope)
			if step.Result != nil {
				add(*step.Result, "same_assessment", []string{seedID, step.ID, *step.Result}, 10, 0)
			}
		}
	}
	// A failed or unfinished Step may have published observations and judgments
	// before its final result. Preserve those originals without completing it.
	if len(stepPaths) != 0 {
		addObservation := func(stepID, id string, path []string) {
			reason := "same_assessment"
			if stepID == request.StepID {
				reason = "step_observation"
			} else if len(queryMatches[stepID]) != 0 {
				reason = "step_query_match"
			}
			add(id, reason, path, 10, 0)
		}
		for _, fact := range state.FactRecords {
			if path, matched := stepPaths[fact.SourceStepID]; matched {
				addObservation(fact.SourceStepID, fact.ID, append(slices.Clone(path), fact.ID))
			}
		}
		for _, candidate := range state.ActiveCandidates() {
			path, matched := stepPaths[candidate.SourceStepID]
			key := assessmentKeys[candidate.SourceStepID]
			if !matched || key != "" && key != FindingIdentity(candidate.Claim, candidate.Scope) {
				continue
			}
			for _, id := range candidate.Sources {
				addObservation(candidate.SourceStepID, id, append(slices.Clone(path), candidate.ID, id))
			}
		}
	}
	if defaultQuery {
		for _, goal := range state.Goals {
			if goal.ID == "goal" {
				query += " " + goal.Condition
			}
		}
	}
	// Only supported observed edges expand the asset neighborhood. Mere shared
	// hosts and endpoint ancestors never imply equivalent identities.
	edges := state.AssetEdges()
	for hop := 0; hop < 2; hop++ {
		next := map[string][]string{}
		for _, edge := range edges {
			if !edge.SupportValid {
				continue
			}
			for _, ends := range [][2]string{{edge.SourceAssetID, edge.TargetAssetID}, {edge.TargetAssetID, edge.SourceAssetID}} {
				path, ok := assets[ends[0]]
				if !ok {
					continue
				}
				path = append(slices.Clone(path), edge.SourceFactID)
				add(edge.SourceFactID, "asset_edge:"+edge.Kind, path, 20+hop, 0)
				if _, known := assets[ends[1]]; !known {
					if _, pending := next[ends[1]]; !pending {
						next[ends[1]] = append(path, ends[1])
					}
				}
			}
		}
		for id, path := range next {
			assets[id] = path
		}
	}
	for _, anchor := range state.AssetAnchors {
		if path, ok := assets[anchor.AssetID]; ok && anchor.NodeKind == "fact" {
			reason := "same_asset"
			if anchor.DiscoveryStepID != "" {
				reason = "step_target"
			}
			add(anchor.NodeID, reason, append(slices.Clone(path), anchor.NodeID), 25, 0)
		}
	}
	// Exact rare tokens provide at most two retrieval hops. Scope is not a
	// join key: a shared environment alone must not recall its whole inventory.
	tokens, postings := map[string][]string{}, map[string][]string{}
	for _, fact := range state.FactRecords {
		if fact.Status == "input" || fact.ID == "origin" || fact.ID == "goal" {
			continue
		}
		body, _ := ContextExcerpt(fact.Description, 4096)
		for _, field := range ObservationContextFields() {
			body += " " + fact.Context[field]
		}
		for _, evidence := range fact.Evidence[:min(len(fact.Evidence), 4)] {
			excerpt, _ := ContextExcerpt(evidence.Excerpt, 2048)
			body += " " + excerpt
		}
		tokens[fact.ID] = relatedTokens(body)
		for _, token := range tokens[fact.ID] {
			postings[token] = append(postings[token], fact.ID)
		}
	}
	rareLimit := max(3, len(state.FactRecords)/16)
	for _, token := range relatedTokens(query) {
		if len(postings[token]) > rareLimit {
			continue
		}
		for _, id := range postings[token] {
			add(id, "query_match:"+token, []string{"query:" + token, id}, 40+len(postings[token]), 1)
		}
	}
	links := relatedSupportLinks(state)
	closure := func() {
		queue := []string{}
		for _, fact := range state.FactRecords {
			if ranks[fact.ID] != nil {
				queue = append(queue, fact.ID)
			}
		}
		for cursor := 0; cursor < len(queue); cursor++ {
			rank := ranks[queue[cursor]]
			for _, link := range links[rank.fact.ID] {
				depth := rank.depth
				if link.reason == "support" {
					depth = 2
				}
				if add(link.id, link.reason, append(slices.Clone(rank.fact.Path), link.id), rank.score, depth) {
					queue = append(queue, link.id)
				}
			}
		}
	}
	closure()
	for hop := 0; hop < 2; hop++ {
		// Snapshot the frontier so storage order cannot create unbounded hops.
		frontier := []relatedRank{}
		for _, fact := range state.FactRecords {
			if rank := ranks[fact.ID]; rank != nil && rank.depth == hop && fact.Status == "valid" && !fact.SupportInvalid {
				frontier = append(frontier, *rank)
			}
		}
		for _, rank := range frontier {
			for _, token := range tokens[rank.fact.ID] {
				if len(postings[token]) > rareLimit {
					continue
				}
				for _, id := range postings[token] {
					target := byID[id]
					if id == rank.fact.ID || target.Status != "valid" || target.SupportInvalid || strings.TrimSpace(target.Scope) != strings.TrimSpace(rank.fact.Scope) {
						continue
					}
					add(id, "shared_token:"+token, append(slices.Clone(rank.fact.Path), id), 60+hop*10+len(postings[token]), hop+1)
				}
			}
		}
		closure()
	}
	ordered := make([]*relatedRank, 0, len(ranks))
	for _, rank := range ranks {
		ordered = append(ordered, rank)
	}
	sort.Slice(ordered, func(i, j int) bool {
		if ordered[i].score != ordered[j].score {
			return ordered[i].score < ordered[j].score
		}
		return ordered[i].ordinal < ordered[j].ordinal
	})
	result := make([]RelatedFact, 0, len(ordered))
	for _, rank := range ordered {
		result = append(result, rank.fact)
	}
	return result
}

const relatedContextReadMore = `Read: Fetch facts, steps and judgments by kind/ID for full details; refine section:related with step_id, assessment, ids, asset_ids or query for omitted leads.
Meaning: Paths, Assessment matches and Step summaries explain retrieval, not proof. Failed or unfinished Steps may have no result; their reason records blockers and revisit conditions, when supplied. Read the full Step when a summary is truncated; a match never authorizes a retry. Compare identity, session, target version, configuration, scope and time; unspecified conditions remain unknown. Cite original fact IDs and do not count shared evidence as independent support.`

// BuildRelatedContext fits connected evidence bundles atomically. A recalled
// observation never silently loses its corrective counterpart or explicit support.
func BuildRelatedContext(state State, request RelatedQuery, maxBytes int) (*RelatedContext, error) {
	if request.Assessment != nil && (!Required(request.Assessment.Claim, StateTextMaxBytes("claim")) || !Required(request.Assessment.Scope, StateTextMaxBytes("scope"))) {
		return nil, Err(422, "related context: assessment requires a canonical claim and scope")
	}
	if request.StepID != "" && !slices.ContainsFunc(state.Steps, func(step Step) bool { return step.ID == request.StepID }) {
		return nil, Err(404, "related context: Step not found")
	}
	for _, id := range request.IDs {
		if !slices.ContainsFunc(state.FactRecords, func(fact FactRecord) bool { return fact.ID == id }) {
			return nil, Err(404, "related context: Fact not found: "+id)
		}
	}
	for _, id := range request.AssetIDs {
		if !slices.ContainsFunc(state.Assets, func(asset Asset) bool { return asset.ID == id }) {
			return nil, Err(404, "related context: Asset not found: "+id)
		}
	}
	if maxBytes <= 0 {
		maxBytes = DefaultContextViewBytes
	}
	limit := request.Limit
	if limit <= 0 {
		limit = 20
	}
	limit = min(limit, 50)
	ranked := RankRelatedFacts(state, request)
	byID := map[string]RelatedFact{}
	for _, fact := range ranked {
		byID[fact.ID] = fact
	}
	judgmentCount := len(state.Candidates) + len(state.Findings) + len(state.Disputes)
	view := &RelatedContext{Facts: []RelatedFact{}, Relations: []FactRelation{}, Omitted: map[string]int{"fact_records": len(ranked), "judgments": judgmentCount, "steps": len(state.Steps)}, ReadMore: relatedContextReadMore}
	base, err := json.Marshal(view)
	if err != nil {
		return nil, err
	}
	if len(base) > maxBytes {
		return nil, Err(422, "related context: budget cannot fit the retrieval metadata")
	}
	// Keep directly matched attempts discoverable before observations consume the
	// budget. The remaining allowance still fits evidence/support atomically.
	appendRelatedSteps(view, relatedSteps(state, request, nil), min(maxBytes, len(base)+maxBytes/3), limit)
	selected := map[string]bool{}
	links := relatedSupportLinks(state)
	edges := state.AssetEdges()
	for _, lead := range ranked {
		if selected[lead.ID] {
			continue
		}
		group := map[string]bool{lead.ID: true}
		for _, id := range lead.Path {
			if _, ok := byID[id]; ok {
				group[id] = true
			}
		}
		queue := []string{}
		for id := range group {
			queue = append(queue, id)
		}
		for cursor := 0; cursor < len(queue) && len(group) <= limit; cursor++ {
			for _, link := range links[queue[cursor]] {
				if _, exists := byID[link.id]; !exists || group[link.id] {
					continue
				}
				group[link.id] = true
				queue = append(queue, link.id)
				if len(group) > limit {
					break
				}
			}
		}
		if len(group) > limit {
			continue
		}
		trial := *view
		trial.Facts = slices.Clone(view.Facts)
		trial.Omitted = map[string]int{"fact_records": len(ranked), "judgments": judgmentCount, "steps": len(state.Steps) - len(view.Steps)}
		for _, fact := range ranked {
			if !group[fact.ID] || selected[fact.ID] {
				continue
			}
			raw, _ := json.Marshal(fact)
			if len(raw) > min(2048, maxBytes/3) {
				fact.Description, _ = ContextExcerpt(fact.Description, 768)
				fact.Evidence = nil
				fact.DetailsOmitted = true
			}
			trial.Facts = append(trial.Facts, fact)
		}
		if len(trial.Facts) > limit {
			continue
		}
		trial.Relations = nil
		trial.AssetEdges = nil
		included := func(id string) bool { return selected[id] || group[id] }
		for _, relation := range state.FactRelations {
			if included(relation.Source) && included(relation.Target) {
				trial.Relations = append(trial.Relations, relation)
			}
		}
		for _, edge := range edges {
			if included(edge.SourceFactID) {
				trial.AssetEdges = append(trial.AssetEdges, edge)
			}
		}
		trial.Omitted["fact_records"] -= len(trial.Facts)
		raw, err := json.Marshal(trial)
		if err != nil {
			return nil, err
		}
		if len(raw) <= maxBytes {
			*view = trial
			for _, fact := range trial.Facts {
				selected[fact.ID] = true
			}
			if len(selected) == limit {
				break
			}
		}
	}
	// Judgment references spend only space left after original evidence bundles.
	judgments := relatedJudgments(state, selected)
	view.Omitted["judgments"] = len(judgments)
	for _, judgment := range judgments {
		view.Judgments = append(view.Judgments, judgment)
		raw, err := json.Marshal(view)
		if err != nil {
			return nil, err
		}
		if len(raw) > maxBytes {
			view.Judgments = view.Judgments[:len(view.Judgments)-1]
			continue
		}
		view.Omitted["judgments"]--
		if len(view.Judgments) == limit {
			break
		}
	}
	// Add producers discovered through selected evidence and any omitted matches.
	steps := relatedSteps(state, request, selected)
	view.Omitted["steps"] = len(steps) - len(view.Steps)
	appendRelatedSteps(view, steps, maxBytes, limit)
	return view, nil
}

func appendRelatedSteps(view *RelatedContext, steps []RelatedStep, maxBytes, limit int) {
	for _, step := range steps {
		if len(view.Steps) >= limit {
			break
		}
		if slices.ContainsFunc(view.Steps, func(old RelatedStep) bool { return old.ID == step.ID }) {
			continue
		}
		view.Steps = append(view.Steps, step)
		raw, err := json.Marshal(view)
		if err != nil || len(raw) > maxBytes {
			view.Steps = view.Steps[:len(view.Steps)-1]
			continue
		}
		view.Omitted["steps"]--
	}
}

// Exact claim/scope matches recall prior assignments, never establish that their
// results are still applicable or that independent verification is redundant.
func relatedAssessmentMatches(state State, request RelatedQuery) map[string]string {
	defaultQuery := request.StepID == "" && len(request.IDs) == 0 && len(request.AssetIDs) == 0 && request.Query == "" && request.Assessment == nil
	key := func(assessment *Assessment) string {
		if assessment == nil || !Required(assessment.Claim, StateTextMaxBytes("claim")) || !Required(assessment.Scope, StateTextMaxBytes("scope")) {
			return ""
		}
		return FindingIdentity(assessment.Claim, assessment.Scope)
	}
	seeds, seedIDs := map[string]string{}, map[string]bool{}
	if identity := key(request.Assessment); identity != "" {
		seeds[identity] = "" // Explicit claim/scope has no originating Step.
	}
	for _, step := range state.Steps {
		if step.ID != request.StepID && !((defaultQuery || request.activeAssessments) && ActiveStepStatus(step.Status)) {
			continue
		}
		if identity := key(step.Assessment); identity != "" {
			seedIDs[step.ID] = true
			if seeds[identity] == "" {
				seeds[identity] = step.ID
			}
		}
	}
	matches := map[string]string{}
	for _, step := range state.Steps {
		if seedIDs[step.ID] || step.Result == nil && step.Status != "failed" && !ActiveStepStatus(step.Status) && step.LatestRunID == "" && Value(step.Worker) == "" {
			continue
		}
		if seedID, matched := seeds[key(step.Assessment)]; matched {
			matches[step.ID] = seedID
		}
	}
	return matches
}

func relatedSteps(state State, request RelatedQuery, selected map[string]bool) []RelatedStep {
	facts, steps := map[string]FactRecord{}, map[string]Step{}
	for _, fact := range state.FactRecords {
		facts[fact.ID] = fact
	}
	for _, step := range state.Steps {
		steps[step.ID] = step
	}
	wanted := map[string]bool{request.StepID: true}
	assessmentMatches := relatedAssessmentMatches(state, request)
	queryMatches := relatedStepQueryMatches(state, request.Query)
	for id := range assessmentMatches {
		wanted[id] = true
	}
	for id := range queryMatches {
		wanted[id] = true
	}
	for id, producer := range FactProducers(facts, steps) {
		if selected[id] && producer != "" {
			wanted[producer] = true
		}
	}
	// Asset selectors match exact targets; neighboring assets do not imply an
	// equivalent attempt. Query matches above are separate discovery hints.
	seedFacts, seedAssets := map[string]bool{}, map[string]bool{}
	for _, id := range request.IDs {
		seedFacts[id] = true
	}
	for _, id := range request.AssetIDs {
		seedAssets[id] = true
	}
	for _, anchor := range state.AssetAnchors {
		if anchor.NodeKind == "step" && anchor.NodeID == request.StepID || anchor.NodeKind == "fact" && seedFacts[anchor.NodeID] {
			seedAssets[anchor.AssetID] = true
		}
	}
	assets := map[string]bool{}
	for _, asset := range state.Assets {
		assets[asset.ID] = seedAssets[asset.ID]
	}
	matches := map[string][]string{}
	for _, anchor := range state.AssetAnchors {
		if anchor.NodeKind != "step" || !assets[anchor.AssetID] {
			continue
		}
		matches[anchor.NodeID] = append(matches[anchor.NodeID], anchor.AssetID)
		step := steps[anchor.NodeID]
		if step.Status == "failed" || step.Status == "needs_review" || step.Result == nil && (step.LatestRunID != "" || Value(step.Worker) != "") {
			wanted[step.ID] = true
		}
	}
	result := []RelatedStep{}
	for _, explicit := range []bool{true, false} {
		for _, step := range state.Steps {
			if !wanted[step.ID] || (step.ID == request.StepID) != explicit {
				continue
			}
			item := RelatedStep{ID: step.ID, Status: step.Status, Result: Value(step.Result), SupportValid: step.SupportValid, Worker: Value(step.Worker), LatestRunID: step.LatestRunID, DisputeID: step.DisputeID}
			item.MatchedAssessmentStepID = assessmentMatches[step.ID]
			item.MatchedQueryTokens = queryMatches[step.ID]
			item.Description, item.DescriptionTruncated = ContextExcerpt(step.Description, 240)
			item.Reason, item.ReasonTruncated = ContextExcerpt(step.Reason, 240)
			matched := matches[step.ID]
			slices.Sort(matched)
			matched = slices.Compact(matched)
			item.MatchedAssetIDs = slices.Clone(matched[:min(len(matched), 8)])
			item.MatchedAssetsOmitted = len(matched) - len(item.MatchedAssetIDs)
			if step.Assessment != nil {
				assessment := *step.Assessment
				var claimTruncated, scopeTruncated bool
				assessment.Claim, claimTruncated = ContextExcerpt(assessment.Claim, 240)
				assessment.Scope, scopeTruncated = ContextExcerpt(assessment.Scope, 240)
				item.AssessmentTruncated = claimTruncated || scopeTruncated
				item.Assessment = &assessment
			}
			result = append(result, item)
		}
	}
	return result
}

// Query-only retrieval must also find attempts that never published a Fact.
// Match bounded, uncommon exact tokens; an unstarted plan is not prior work.
// These matches affect discovery only, never support or retry authorization.
func relatedStepQueryMatches(state State, query string) map[string][]string {
	matches := map[string][]string{}
	queryTokens := relatedTokens(query)
	if len(queryTokens) == 0 {
		return matches
	}
	postings := map[string][]string{}
	attempts := 0
	for _, step := range state.Steps {
		if step.Result == nil && step.LatestRunID == "" && Value(step.Worker) == "" && step.Status != "failed" && step.Status != "needs_review" && step.Status != "completed" {
			continue
		}
		attempts++
		description, _ := ContextExcerpt(step.Description, 4096)
		reason, _ := ContextExcerpt(step.Reason, 4096)
		if step.Assessment != nil {
			claim, _ := ContextExcerpt(step.Assessment.Claim, 4096)
			description += " " + claim
		}
		for _, token := range relatedTokens(description + " " + reason) {
			postings[token] = append(postings[token], step.ID)
		}
	}
	for _, token := range queryTokens {
		if len(postings[token]) > max(3, attempts/16) {
			continue
		}
		for _, id := range postings[token] {
			if len(matches[id]) < 4 {
				matches[id] = append(matches[id], token)
			}
		}
	}
	return matches
}

func relatedJudgments(state State, facts map[string]bool) []ContextOverviewNode {
	touches := func(ids []string) bool { return slices.ContainsFunc(ids, func(id string) bool { return facts[id] }) }
	items := []ContextOverviewNode{}
	selected := map[NodeKey]bool{}
	add := func(node ContextOverviewNode, text string, sources []string) {
		node.Excerpt, node.TextTruncated = ContextExcerpt(text, 240)
		node.Reason, node.ReasonTruncated = ContextExcerpt(node.Reason, 240)
		node.Sources = slices.Clone(sources[:min(len(sources), 16)])
		node.SourcesOmitted = len(sources) - len(node.Sources)
		selected[NodeKey{Kind: node.Kind, ID: node.ID}] = true
		items = append(items, node)
	}
	for _, candidate := range state.ActiveCandidates() {
		if touches(candidate.Sources) {
			projected := state.CandidateView(candidate)
			add(ContextOverviewNode{ID: candidate.ID, Kind: "candidate", Status: candidate.Status, GroupKey: projected.GroupKey, SupportValid: projected.SupportValid, Scope: candidate.Scope, Reason: candidate.Reason}, candidate.Claim, candidate.Sources)
		}
	}
	for _, finding := range state.Findings {
		if touches(finding.Sources) {
			support := finding.SupportValid
			add(ContextOverviewNode{ID: finding.ID, Kind: "finding", Status: finding.Status, GroupKey: FindingIdentity(finding.Claim, finding.Scope), SupportValid: &support, DisputeID: finding.DisputeID, Scope: finding.Scope, Reason: finding.Reason}, finding.Claim, finding.Sources)
		}
	}
	judgmentEnd := len(items)
	for _, dispute := range state.Disputes {
		if dispute.Status != "resolved" && (touches(dispute.ReviewFactIDs) || selected[NodeKey{Kind: "finding", ID: dispute.FindingID}] || slices.ContainsFunc(dispute.CandidateIDs, func(id string) bool { return selected[NodeKey{Kind: "candidate", ID: id}] })) {
			// As in the overview, a dispute's sources are candidate identities.
			add(ContextOverviewNode{ID: dispute.ID, Kind: "dispute", Status: dispute.Status, Reason: dispute.Reason}, dispute.Question, dispute.CandidateIDs)
		}
	}
	return append(slices.Clone(items[judgmentEnd:]), items[:judgmentEnd]...)
}

type relatedSupportLink struct{ id, reason string }

func relatedSupportLinks(state State) map[string][]relatedSupportLink {
	links := map[string][]relatedSupportLink{}
	for id, dependencies := range state.FactDependencies() {
		for _, dependency := range dependencies {
			links[id] = append(links[id], relatedSupportLink{dependency.ID, "support"})
		}
	}
	for _, relation := range state.FactRelations {
		links[relation.Source] = append(links[relation.Source], relatedSupportLink{relation.Target, "correction:" + relation.Kind})
		links[relation.Target] = append(links[relation.Target], relatedSupportLink{relation.Source, "correction:" + relation.Kind})
	}
	return links
}

func relatedTokens(text string) []string {
	parts := strings.FieldsFunc(strings.ToLower(text), func(r rune) bool {
		return !unicode.IsLetter(r) && !unicode.IsDigit(r) && !strings.ContainsRune("-_.:/%", r)
	})
	tokens := []string{}
	for _, token := range parts {
		token = strings.Trim(token, ".:/%-_")
		if len(token) < 3 || len(token) > 256 || strings.Contains("|the|and|for|from|with|that|this|not|are|was|were|has|have|had|into|its|can|will|may|should|must|read|use|using|only|all|any|one|two|new|old|true|false|null|status|scope|observed|observation|evidence|record|records|result|results|source|sources|identify|inspect|check|verify|report|select|selects|selected|route|backend|backends|slot|build|host|port|service|endpoint|catalog|inventory|archived|deployment|local|", "|"+token+"|") {
			continue
		}
		tokens = append(tokens, token)
	}
	slices.Sort(tokens)
	return slices.Compact(tokens)
}
