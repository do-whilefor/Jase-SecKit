package worker

import (
	"encoding/json"
	"errors"
	"fmt"
)

// Phase guidance describes an already selected transition. Session code owns
// role selection, tool policy, durable allowances and frozen recovery inputs.
const decisionContinuationPrompt = `# Continue decision

This Decide has no committed receipt. The original deadline still applies.

- Use native tool calls for read_graph, assess_root when available, and graph_action; XML/JSON text is not executed.
- Then commit the draft; an empty plan requires a valid open or running Step.
- For truncated tool calls, reissue complete arguments.
- If unable to proceed, return accepted:false with a reason.`

const curationContinuationPrompt = `# Continue curation

This curation has no committed receipt. The original input boundary and deadline still apply.

- Read the supplied evidence and submit graph_action curate using native tool calls; XML/JSON text is not executed.
- If unable to proceed, return accepted:false with a reason.`

const executionContinuationPrompt = `# Continue execution

Continue this same execution under the original task deadline. Tools are enabled.

- Before more tools, identify this batch's new observation, excluded explanation or unblocked prerequisite from retained evidence.
- If none, state the changed method or condition that makes another attempt useful; without one, report incomplete with the blocker and revisit condition.
- Tool success alone is not gained knowledge.
- Use completed only when the assigned task is finished.`

const decisionRecoveryPrompt = `# Decision recovery

The uncommitted decision draft was discarded on recovery.

- Read the current overview and affected facts, then restage the whole plan.
- Old $aliases, draft receipts and completion_assessment reuse are invalid.
- Completion now requires preview and review of completion_review in a subsequent model turn before commit; ordinary plans can commit directly.`

func progressCorrectionInstruction(control bool) string {
	fallback := "If unable to proceed, report incomplete with the blocker."
	if control {
		fallback = "If unable to proceed, return accepted:false with a reason."
	}
	return `Recent tools have repeated unchanged observations or kept failing.

## Reassess progress

- Reassess the blocker and change the approach; do not repeat the same unsuccessful call or unchanged read without a reason to expect new information.
- ` + fallback + `
- The original task and budgets still apply.`
}

func repairInstruction(j Job, concluding bool, attempt int, problem *outputFailure) (string, error) {
	if problem == nil {
		return "", errors.New("result repair requires a failure reason")
	}
	reason, _ := json.Marshal(problem.Error())
	fallback := "If no supported factual result is available, return {\"accepted\":false,\"reason\":\"...\"}."
	if j.Kind != "reason" {
		fallback = "An unfinished accepted task must report incomplete with remaining work and its blocker, not completed or rejected merely to satisfy JSON formatting."
		if !concluding {
			fallback += " If further execution can finish the task, report continue; the runtime will restore tools in this same run under the original deadline."
		}
	}
	instruction := fmt.Sprintf(`# Result-format repair %d/%d

Continue in the same session. All tools are disabled.

## Failure

The previous response cannot be submitted: %s.

## Replacement

- Replace it with one complete JSON object using the original task contract and current phase restrictions; do not append a suffix or include the earlier JSON.
- Use only existing evidence and require the contract's proof for completion; never force accepted:true.
- %s`, attempt, maxOutputRepairs, reason, fallback)
	if problem.Reason == "output_truncated" {
		instruction += "\n- Rewrite the truncated response more briefly; a parseable prefix is not a complete answer."
	}
	return instruction + "\n", nil
}
