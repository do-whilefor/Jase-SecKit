package protocol

import (
	"errors"
	"strings"
	"unicode/utf8"

	"pwnmesh/internal/board/model"
)

const MaxRelatedGraphBytes = 16 << 10

// Related reads are bounded discovery projections, never completion authority.
// Further detail uses the original IDs under this same state version.
type RelatedGraphContext struct {
	*model.RelatedContext
	Section      string `json:"section"`
	StateVersion string `json:"state_version"`
	Revision     int64  `json:"revision"`
	Generation   int64  `json:"generation"`
}

func validateRelatedRead(r GraphRequest) error {
	if r.Section != "related" {
		if r.StepID != "" || r.Query != "" || r.Assessment != nil {
			return errors.New("step_id, query and assessment require a related read")
		}
		return nil
	}
	if r.Op != "" && r.Op != "read_graph" && r.Op != "read_snapshot" {
		return errors.New("related requires a graph read")
	}
	if r.Offset != 0 || r.ByteOffset != nil || r.RecordVersion != "" || r.AssetNeighborhood {
		return errors.New("related reads use bounded seeds; refine the query or read returned fact IDs for details")
	}
	if len(r.Query) > 1024 || !utf8.ValidString(r.Query) || r.Query != "" && strings.TrimSpace(r.Query) == "" {
		return errors.New("related query must be nonempty UTF-8 text of at most 1024 bytes")
	}
	if len(r.StepID) > 256 || strings.TrimSpace(r.StepID) != r.StepID {
		return errors.New("invalid related step_id")
	}
	if r.Assessment != nil && (!model.Required(r.Assessment.Claim, 16384) || !model.Required(r.Assessment.Scope, 4096)) {
		return errors.New("related assessment requires a canonical claim and scope")
	}
	if r.StepID == "" && r.Query == "" && r.Assessment == nil && len(r.IDs)+len(r.AssetIDs) == 0 {
		return errors.New("related requires step_id, query, assessment, fact ids or asset_ids")
	}
	return nil
}

func relatedGraphContext(s model.State, r GraphRequest, version string) (*RelatedGraphContext, error) {
	related, err := model.BuildRelatedContext(s, model.RelatedQuery{
		StepID: r.StepID, Query: r.Query, Assessment: r.Assessment, IDs: r.IDs, AssetIDs: r.AssetIDs, Limit: r.Limit,
	}, MaxRelatedGraphBytes-256)
	if err != nil {
		return nil, err
	}
	return &RelatedGraphContext{related, "related", version, s.Revision, s.Graph.Project.Generation}, nil
}
