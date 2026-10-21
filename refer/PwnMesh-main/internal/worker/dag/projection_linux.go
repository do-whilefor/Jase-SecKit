//go:build linux

package dag

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"

	"pwnmesh/internal/workergraph"
)

// Retained-byte verification timings are not new task observations. Keep
// semantic identities, execution outcomes and accepted bytes in the digest.
type nodeObservation struct {
	ID, Kind, Status, DefinitionSHA256, InputSHA256 string
	Attempt                                         int
	Output                                          workergraph.Output
	Error, Reason                                   string
}

func observeNode(node workergraph.NodeState) nodeObservation {
	return nodeObservation{node.ID, node.Kind, node.Status, node.DefinitionSHA256, node.InputSHA256, node.Attempt, node.Output, node.Error, node.Reason}
}

func observationDigest(value any) string {
	raw, _ := json.Marshal(value)
	digest := sha256.Sum256(raw)
	return hex.EncodeToString(digest[:])
}

func graphProgress(checkpoint workergraph.Checkpoint, executed int, failure string, evidenceErrors map[string]string) Progress {
	nodes := make([]nodeObservation, 0, len(checkpoint.Nodes))
	for _, node := range checkpoint.Nodes {
		nodes = append(nodes, observeNode(node))
	}
	digest := observationDigest(struct {
		Status, Definition, Input, Error string
		Nodes                            []nodeObservation
		EvidenceErrors                   map[string]string
	}{checkpoint.Status, checkpoint.DefinitionSHA256, checkpoint.InputSHA256, failure, nodes, evidenceErrors})
	return Progress{Version: 1, StateSHA256: digest, ExecutedNodes: executed}
}

// Append responses expose only new/changed outcomes. Omission is explicit;
// the complete retained receipt remains available through checkpoint_path.
func commandGraphDelta(before, after []workergraph.NodeState) ([]workergraph.NodeState, int, int) {
	previous := make(map[string]string, len(before))
	for _, node := range before {
		previous[node.ID] = observationDigest(observeNode(node))
	}
	visible := []workergraph.NodeState{}
	unchanged, omitted, size := 0, 0, 0
	for _, node := range after {
		if previous[node.ID] == observationDigest(observeNode(node)) {
			unchanged++
			continue
		}
		raw, _ := json.Marshal(commandGraphViews([]workergraph.NodeState{node})[0])
		if len(visible) >= 16 || size+len(raw) > 64<<10 {
			omitted++
			continue
		}
		visible, size = append(visible, node), size+len(raw)
	}
	return visible, unchanged, omitted
}
