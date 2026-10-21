package model

import "encoding/json"

// JobInputBinding is the immutable input shared by Board and wire consumers.
// Decoders use narrow views so unrelated Job fields remain opaque.
// These views never replace or re-encode the persisted Job.
type JobInputBinding struct {
	Graph         Graph          `json:"graph"`
	State         *State         `json:"state,omitempty"`
	InputSnapshot *InputSnapshot `json:"input_snapshot,omitempty"`
}

func (j JobInputBinding) StateVersion() string {
	if j.InputSnapshot != nil {
		return j.InputSnapshot.StateVersion
	}
	return ""
}

func (j JobInputBinding) Revision() int64 {
	if j.InputSnapshot != nil {
		return j.InputSnapshot.Revision
	}
	return 0
}

type DecisionBinding struct {
	Version         int    `json:"version"`
	StateVersion    string `json:"state_version"`
	ClosureProtocol int    `json:"closure_protocol,omitempty"`
}

type DecisionJobBinding struct {
	JobInputBinding
	Kind     string           `json:"kind"`
	Decision *DecisionBinding `json:"decision"`
}

type CurationJobBinding struct {
	JobInputBinding
	Kind      string          `json:"kind"`
	InputView json.RawMessage `json:"input_view"`
}

// JobProtocolFields retains presence, including null, before scalar decoding.
type JobProtocolFields struct {
	GraphRPC              json.RawMessage `json:"graph_rpc"`
	ResultContractVersion json.RawMessage `json:"result_contract_version"`
}

type DecisionProtocol struct {
	Version int `json:"version"`
}

// JobProtocolBinding deliberately does not decode graph data or full decisions.
// Registration separately validates the complete immutable input.
type JobProtocolBinding struct {
	Kind                  string `json:"kind"`
	GraphRPC              bool   `json:"graph_rpc"`
	ResultContractVersion int    `json:"result_contract_version"`
	Graph                 struct {
		Project struct {
			OrchestrationVersion int `json:"orchestration_version"`
		} `json:"project"`
	} `json:"graph"`
	Decision *DecisionProtocol `json:"decision"`
}
