package agent

// ModelDescriptor identifies a configured model without exposing its endpoint
// or credentials. Unknown limits are omitted instead of inferred from a budget.
type ModelDescriptor struct {
	ID        string   `json:"id"`
	API       string   `json:"api"`
	Provider  string   `json:"provider"`
	Reasoning bool     `json:"reasoning"`
	MaxTokens int      `json:"maxTokens,omitempty"`
	Input     []string `json:"input,omitempty"`
}

func (m ModelDescriptor) SameModel(other ModelDescriptor) bool {
	return m.ID != "" && m.API != "" && m.Provider != "" &&
		m.ID == other.ID && m.API == other.API && m.Provider == other.Provider
}

// ModelProvider supplies the credential-free model used by the host transport.
type ModelProvider interface {
	ModelDescriptor() ModelDescriptor
}
