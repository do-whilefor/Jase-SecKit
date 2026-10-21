package board

import (
	"database/sql"
	"encoding/json"
	"errors"
	"slices"

	"pwnmesh/internal/board/internal/sqlstore"
	"pwnmesh/internal/board/model"
)

// Bound the transport envelope, not the retained immutable snapshot.
const MaxCurationInputBytes = 256 << 10

// CurationJobBoundary uses the registered server-owned snapshot. Registration
// checks its metadata against storage; model output cannot select the boundary.
func CurationJobBoundary(raw json.RawMessage) (string, int64, error) {
	var job model.CurationJobBinding
	if json.Unmarshal(raw, &job) != nil || job.Kind != "curate" || job.Graph.Project.OrchestrationVersion != 1 {
		return "", 0, Err(422, "invalid registered curation input")
	}
	ref := job.InputSnapshot
	if ref == nil || job.State != nil || ref.Version != 1 || len(ref.ID) != 64 || len(ref.StateVersion) != 64 || ref.ProjectID != job.Graph.Project.ID || ref.Generation != job.Graph.Project.Generation || ref.Revision < 0 || len(job.Graph.Facts)+len(job.Graph.Intents)+len(job.Graph.Hints) != 0 || len(job.InputView) > DefaultContextViewBytes || !json.Valid(job.InputView) {
		return "", 0, Err(422, "invalid curation snapshot binding")
	}
	return ref.StateVersion, ref.Revision, nil
}

func (t *Tx) ClaimCurator(project, worker, trigger string) (Reason, error) {
	g, err := t.Load(project)
	if err != nil {
		return Reason{}, err
	}
	if err = g.RequireActive(); err != nil {
		return Reason{}, err
	}
	if g.Project.OrchestrationVersion != 1 || !required(worker, 256) || !required(trigger, 4096) {
		return Reason{}, Err(422, "curator requires version 1, worker and trigger")
	}
	if revoked, err := t.RunRevoked(project, worker); err != nil {
		return Reason{}, err
	} else if revoked {
		return Reason{}, Err(409, "Execution was revoked")
	}
	if current := g.Project.Curator; current != nil {
		if current.Worker != worker {
			return Reason{}, Err(409, "Another execution owns curation")
		}
		return *current, nil
	}
	lease := Reason{Worker: worker, Trigger: trigger, StartedAt: t.Now, Heartbeat: t.Now}
	g.Project.Curator = &lease
	return lease, t.saveOrchestration(g.Project)
}

func (t *Tx) HeartbeatCurator(project, worker string) error {
	g, err := t.Load(project)
	if err != nil {
		return err
	}
	if err = g.RequireActive(); err != nil {
		return err
	}
	if err = t.CheckExecution(g, ExecutionFence{Run: worker, Lease: "curate"}); err != nil {
		return err
	}
	g.Project.Curator.Heartbeat = t.Now
	return t.saveOrchestration(g.Project)
}

func (t *Tx) ReleaseCurator(project, worker string) error {
	// Conditional release is safe after a successful execution revoked its run.
	return sqlstore.ReleaseCuratorLease(t.transactionQueries, project, worker)
}

func controlKind(kind string) bool { return kind == "reason" || kind == "curate" }

func (t *Tx) curationNeeded(s State) (bool, error) {
	if s.Graph.Project.OrchestrationVersion != 1 {
		return false, nil
	}
	if s.PendingCurationRequest() != nil && !s.CurationRequestNeedsEvidence() {
		return true, nil
	}
	if len(s.PendingCurationCandidateIDs()) > 0 {
		return true, nil
	}
	// Ordinary tasks may never move the curation cursor. Do not rescan their
	// complete event history unless there is a review or conclusion to revisit.
	reviews := []Dispute{}
	unsupported := []string{}
	for _, dispute := range s.Disputes {
		if dispute.Status == "resolved" {
			if s.ValidateFactSources(dispute.ReviewFactIDs, true) != nil {
				unsupported = append(unsupported, dispute.ReviewFactIDs...)
			}
		} else if len(dispute.ReviewStepIDs) > 0 {
			reviews = append(reviews, dispute)
		}
	}
	for _, finding := range s.Findings {
		if finding.Status != "candidate" && !finding.SupportValid {
			unsupported = append(unsupported, finding.Sources...)
		}
	}
	if len(reviews) == 0 && len(unsupported) == 0 {
		return false, nil
	}
	// A review fact is usable only after its independent execution succeeds.
	// Completion remains durable even if an earlier optional scan saw the fact
	// while that execution was running. Normal producer completion is irrelevant.
	// Version 1 records corrective relations inside the atomic curation event.
	// A scan without relations only acknowledges its input and must not wake
	// another scan solely because an unsupported conclusion remains retained.
	completed, curators := map[string]bool{}, map[string]bool{}
	relations := map[FactRelation]bool{}
	err := sqlstore.VisitCurationEvents(t.transactionQueries, s.Graph.Project.ID, s.Curation.ThroughRevision, func(event sqlstore.CurationEvent) error {
		switch event.Op {
		case "step_completed":
			completed[event.ID] = true
		case "curate":
			curators[event.RunID] = true
		case "fact_relation":
			var relation FactRelation
			if err := json.Unmarshal([]byte(event.Result), &relation); err != nil {
				return err
			}
			relations[relation] = true
		}
		return nil
	})
	if err != nil {
		return false, err
	}
	newRelation := func(relation FactRelation) bool {
		return curators[relation.RunID] || relations[relation]
	}
	if len(unsupported) > 0 && slices.ContainsFunc(s.FactRelations, newRelation) {
		// Canonical edges retain their original author, so a duplicate proposal
		// cannot count as a new correction. Reuse the support projection without
		// those new edges to test their actual impact, including Step dependencies
		// while preserving independent observations from the same producer.
		d, revision, decision, err := t.stateData(s.Graph.Project.ID)
		if err != nil {
			return false, err
		}
		d.FactRelations = slices.DeleteFunc(d.FactRelations, newRelation)
		before, err := t.projectState(s.Graph, d, revision, decision)
		if err != nil {
			return false, err
		}
		for _, source := range unsupported {
			if s.ValidateFactSources([]string{source}, true) != nil && before.ValidateFactSources([]string{source}, true) == nil {
				return true, nil
			}
		}
	}
	for _, dispute := range reviews {
		for _, fact := range s.FactRecords {
			if completed[fact.SourceStepID] && t.validateReviewFacts(s, dispute, []string{fact.ID}) == nil {
				return true, nil
			}
		}
	}
	return false, nil
}

func CurationRetryKey(s State) string { return "curate:" + DecisionStateVersion(s) }

// Receipt reads remain available after the live lease ends. The HTTP layer
// checks that the caller possesses the registered immutable run identity.
func (t *Tx) CurationReceipt(project, run string) (StateActionResult, error) {
	response, err := sqlstore.CurationResponse(t.transactionQueries, project, run)
	if errors.Is(err, sql.ErrNoRows) {
		return StateActionResult{}, Err(404, "Curation receipt not found")
	}
	if err != nil {
		return StateActionResult{}, err
	}
	var result StateActionResult
	err = json.Unmarshal([]byte(response), &result)
	return result, err
}
