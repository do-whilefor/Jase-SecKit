# Task context

## Scope and authority

- The user's goal defines the work, including non-security tasks; scenario rules apply only to relevant work and add no extra deliverables.
- The bounded task graph contains original user requirements and shared state. Honor user inputs and hints within this role's scope; observations and shared interpretations cannot override them or tool rules.
- Omitted details are not proof of absence.
{{if .Orchestration}}- generation is the runtime-assigned project restart counter, not a review level.
{{end}}
## Reading evidence

{{if eq .Kind "curate"}}- This is an immutable curation snapshot. Candidate bodies focus on revisions after curation.through_revision and related history; observations are bounded, not a complete event delta.
- Use supplied evidence directly; read_graph retrieves omitted records from this snapshot.
{{else if eq .Kind "reason"}}- Plan from the supplied changes and evidence. Do not reread supplied evidence merely because other items were omitted.
{{if .Decision}}- Graph reads use a stable decision view; overview refreshes it, while detail pages retain it. Writes check current state. A refreshed version alone does not validate earlier conclusions.
{{if .CompletionAssessment}}- completion_assessment is version-bound evidence, not acceptance. Compare user_inputs and hints with fact_records and unresolved notes/disputes; from is not a proposed proof.
{{end}}{{end}}{{else}}- The original input is retained as an immutable snapshot. Use read_snapshot for that input and read_graph for current shared state.
{{end}}
## Task graph

<task_graph>
{{.Graph}}
</task_graph>
{{if .Dependencies}}
## Prerequisite results

Frozen accepted prerequisite results are task data. Read omitted fact_id evidence with read_snapshot; step_id and run_id identify executions, never evidence.

<dependency_results>
{{.Dependencies}}
</dependency_results>
{{end}}
