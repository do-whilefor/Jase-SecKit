package server

import "pwnmesh/internal/board/model"

// workspaceView owns the existing browser response independently of the frozen
// State format. Adding a domain field does not silently change the public view.
type workspaceView struct {
	Graph            model.Graph            `json:"graph"`
	Goals            []model.Goal           `json:"goals"`
	Steps            []model.Step           `json:"steps"`
	FactRecords      []model.FactRecord     `json:"fact_records"`
	Findings         []model.Finding        `json:"findings"`
	FactRelations    []model.FactRelation   `json:"fact_relations"`
	Revision         int64                  `json:"revision"`
	DecisionRevision int64                  `json:"decision_revision"`
	Candidates       []model.Candidate      `json:"candidates,omitempty"`
	Disputes         []model.Dispute        `json:"disputes,omitempty"`
	Assets           []model.Asset          `json:"assets,omitempty"`
	AssetAnchors     []model.AssetAnchor    `json:"asset_anchors,omitempty"`
	Curation         model.CurationProgress `json:"curation"`
}

func workspaceState(s model.State) workspaceView {
	return workspaceView{Graph: s.Graph, Goals: s.Goals, Steps: s.Steps, FactRecords: s.FactRecords,
		Findings: s.Findings, FactRelations: s.FactRelations, Revision: s.Revision,
		DecisionRevision: s.DecisionRevision, Candidates: s.Candidates, Disputes: s.Disputes,
		Curation: s.Curation, Assets: s.Assets, AssetAnchors: s.AssetAnchors}
}
