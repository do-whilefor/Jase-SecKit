package model

import (
	"slices"
	"unicode/utf8"
)

// UserInputFacts includes original requirements and legacy reopen feedback.
func (s State) UserInputFacts() ([]Fact, map[string]bool) {
	ids := map[string]bool{"origin": true, "goal": true}
	for _, step := range s.Steps {
		if s.ExternalFeedbackStep(step) {
			ids[*step.Result] = true
		}
	}
	inputs := []Fact{}
	for _, fact := range s.Graph.Facts {
		if ids[fact.ID] {
			inputs = append(inputs, fact)
		}
	}
	return inputs, ids
}

// ExternalFeedbackStep identifies human input recorded as a synthetic concluded Intent.
func (s State) ExternalFeedbackStep(step Step) bool {
	if step.Description != "external_feedback" || step.Result == nil {
		return false
	}
	return slices.ContainsFunc(s.FactRecords, func(fact FactRecord) bool {
		return fact.ID == *step.Result && fact.Legacy && fact.SourceStepID == ""
	})
}

// FactProducers uses explicit provenance without inferring missing bindings.
func FactProducers(facts map[string]FactRecord, steps map[string]Step) map[string]string {
	producers := make(map[string]string)
	for id, fact := range facts {
		if id == "origin" || id == "goal" || fact.SourceStepID == "" {
			continue
		}
		if _, exists := steps[fact.SourceStepID]; exists {
			producers[id] = fact.SourceStepID
		}
	}
	return producers
}

// ContextExcerpt returns a literal UTF-8 prefix for deterministic reading views.
func ContextExcerpt(text string, maxBytes int) (string, bool) {
	if len(text) <= maxBytes {
		return text, false
	}
	end := maxBytes
	for end > 0 && !utf8.RuneStart(text[end]) {
		end--
	}
	return text[:end], true
}
