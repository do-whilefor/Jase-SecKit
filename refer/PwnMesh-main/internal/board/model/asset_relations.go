package model

import (
	"bytes"
	"encoding/json"
	"net/netip"
	"slices"
	"strings"
)

const MaxAssetRelations = 32

// AssetRelationSpec uses ordinary asset identities so a new observation can
// publish both endpoints atomically without guessing their canonical IDs.
type AssetRelationSpec struct {
	Kind   string    `json:"kind"`
	Source AssetSpec `json:"source"`
	Target AssetSpec `json:"target"`
}

// AssetRelation is an immutable producer assertion backed by its owning Fact's
// original evidence. It never asserts equivalence, permission or causation.
type AssetRelation struct {
	Kind          string `json:"kind"`
	SourceAssetID string `json:"source_asset_id"`
	TargetAssetID string `json:"target_asset_id"`
}

type AssetEdge struct {
	AssetRelation
	SourceFactID string `json:"source_fact_id"`
	Scope        string `json:"scope"`
	ObservedAt   string `json:"observed_at"`
	Status       string `json:"status"`
	SupportValid bool   `json:"support_valid"`
}

func ParseAssetRelations(raw json.RawMessage) ([]AssetRelationSpec, error) {
	if len(raw) == 0 {
		return nil, nil
	}
	var specs []AssetRelationSpec
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if !json.Valid(raw) || bytes.Equal(bytes.TrimSpace(raw), []byte("null")) || d.Decode(&specs) != nil || len(specs) > MaxAssetRelations {
		return nil, Err(422, "asset_relations requires at most 32 typed source/target asset pairs")
	}
	if _, _, err := NormalizeFactAssets(nil, specs); err != nil {
		return nil, err
	}
	return specs, nil
}

// NormalizeFactAssets applies one total identity budget to explicit anchors and
// relation endpoints. The caller persists both in the existing Fact transaction.
func NormalizeFactAssets(specs []AssetSpec, assertions []AssetRelationSpec) ([]Asset, []AssetRelation, error) {
	if len(specs) > MaxActionAssets || len(assertions) > MaxAssetRelations {
		return nil, nil, Err(422, "a fact may reference at most 32 assets and 32 asset relations")
	}
	var assets []Asset
	for _, spec := range specs {
		asset, err := NormalizeAsset(spec)
		if err != nil {
			return nil, nil, err
		}
		assets = append(assets, asset)
	}
	var relations []AssetRelation
	for _, spec := range assertions {
		source, err := NormalizeAsset(spec.Source)
		if err != nil {
			return nil, nil, err
		}
		target, err := NormalizeAsset(spec.Target)
		if err != nil {
			return nil, nil, err
		}
		if !validAssetRelation(spec.Kind, source, target) {
			return nil, nil, Err(422, "resolves_to requires a DNS host and IP host; redirects_to requires distinct endpoints")
		}
		assets = append(assets, source, target)
		relations = append(relations, AssetRelation{Kind: spec.Kind, SourceAssetID: source.ID, TargetAssetID: target.ID})
	}
	slices.SortFunc(assets, func(a, b Asset) int { return strings.Compare(a.ID, b.ID) })
	assets = slices.CompactFunc(assets, func(a, b Asset) bool { return a.ID == b.ID })
	if len(assets) > MaxActionAssets {
		return nil, nil, Err(422, "a fact may reference at most 32 distinct assets including relation endpoints")
	}
	slices.SortFunc(relations, compareAssetRelations)
	return assets, slices.Compact(relations), nil
}

func validAssetRelation(kind string, source, target Asset) bool {
	if source.ID == "" || target.ID == "" || source.ID == target.ID {
		return false
	}
	switch kind {
	case "resolves_to":
		_, sourceErr := netip.ParseAddr(source.Value)
		_, targetErr := netip.ParseAddr(target.Value)
		return source.Kind == "host" && target.Kind == "host" && sourceErr != nil && targetErr == nil
	case "redirects_to":
		return source.Kind == "endpoint" && target.Kind == "endpoint"
	}
	return false
}

func compareAssetRelations(a, b AssetRelation) int {
	if c := strings.Compare(a.Kind, b.Kind); c != 0 {
		return c
	}
	if c := strings.Compare(a.SourceAssetID, b.SourceAssetID); c != 0 {
		return c
	}
	return strings.Compare(a.TargetAssetID, b.TargetAssetID)
}

// AssetEdges retains corrected assertions with support_valid=false. Consumers
// may show their history, but must not traverse them as current support.
func (s State) AssetEdges() []AssetEdge {
	assets := make(map[string]Asset, len(s.Assets))
	for _, asset := range s.Assets {
		assets[asset.ID] = asset
	}
	anchors := map[string]map[string]bool{}
	for _, anchor := range s.AssetAnchors {
		if anchor.NodeKind == "fact" && anchor.DiscoveryStepID == "" {
			if anchors[anchor.NodeID] == nil {
				anchors[anchor.NodeID] = map[string]bool{}
			}
			anchors[anchor.NodeID][anchor.AssetID] = true
		}
	}
	var edges []AssetEdge
	for _, fact := range s.FactRecords {
		for _, relation := range fact.AssetRelations {
			if !anchors[fact.ID][relation.SourceAssetID] || !anchors[fact.ID][relation.TargetAssetID] || !validAssetRelation(relation.Kind, assets[relation.SourceAssetID], assets[relation.TargetAssetID]) {
				continue
			}
			edges = append(edges, AssetEdge{AssetRelation: relation, SourceFactID: fact.ID, Scope: fact.Scope, ObservedAt: fact.ObservedAt, Status: fact.Status,
				SupportValid: fact.Status == "valid" && !fact.SupportInvalid && !fact.Legacy && fact.RunID != "" && len(fact.Evidence) > 0})
		}
	}
	slices.SortFunc(edges, func(a, b AssetEdge) int {
		if c := compareAssetRelations(a.AssetRelation, b.AssetRelation); c != 0 {
			return c
		}
		return strings.Compare(a.SourceFactID, b.SourceFactID)
	})
	return edges
}
