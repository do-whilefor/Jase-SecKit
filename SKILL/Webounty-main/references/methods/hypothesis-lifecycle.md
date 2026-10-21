# Conditional hypothesis closure and report corrections

## Use and prerequisites
Use when deciding whether to close a negative branch, reopen an old result,
or reconcile a report with later contrary evidence. Identify the narrow claim,
its conditions, the actual experiment and observer, current source revisions,
normal controls, remaining gaps, and the proposed meaning of “closed.”

## Discriminating review
Recover original observations before accepting a historical takeaway. Separate
three cases: a valid test refuted the specific claim; the observer or normal
baseline failed; or a necessary input was unavailable. Only the first supports
a tested negative under those conditions. Do not turn absent 200 responses,
404 routes, rejected malformed input, or empty output into whole-class safety.
Track the tested identity, object, input shape, deployment, credential generation,
and business outcome. Missing dimensions stay unknown rather than inheriting
another page's conditions.

For a correction, retain the original observation and historical interpretation,
link the contrary result and normal control, and invalidate only conclusions
that actually depended on the corrected claim. Ensure impact text, vector
rationale, capability chain, and summary agree. Different pages repeating one
event add no corroboration; separate captures in the same JSONL file must not
be collapsed merely because they share a container.

For retesting, use `patch-differential` to check the original failure and normal
business behavior under current conditions. A broken downstream consumer does
not erase separately observed issuance capability; use `capability-consumer`
to locate the actual cut in the chain.

## Support / refute / uncertain
Support a conditional closure when a valid discriminating test with its controls
refutes the stated claim and unresolved prerequisites do not invalidate that
test. This does not prove all entry points or vulnerability classes safe.
Refute closure when its observer fails, sources are corrected, conditions are
incompatible, or omitted evidence changes the conclusion. Without a valid
observer or required input, retain inconclusive/unknown and the precise gap.
An author's status field is a declaration, not a new experiment.

## Stop and reopen
Store closure reason, tested scope, evidence references, and a concrete reopen
condition. Reopen only the affected branch when deployment, relationship,
input parsing, credential state, consumer compatibility, or relevant evidence
changes. A new narrative or historical vulnerability name alone adds no new
experiment. Method selection cannot authorize a target action.

## Source attribution
Paths are relative to Web-Vulnhunt; reviewed hashes are in `catalog.json`.
- `references/killed-hypotheses.md`, lines 1–11, 61–76, 122–130, 216–224:
  useful negative-work records; “no 200” and signup 422 are narrower observations
  than several historical takeaways imply.
- `references/review-log.md`, lines 1–39 and 105–152: source records revisions
  and later changes; those are historical assertions, not current-run facts.
- `references/report-structure.md`, lines 65–100 and 119–128: contradictory
  oracle/impact wording and unsupported “vendor acknowledgement” inference.
