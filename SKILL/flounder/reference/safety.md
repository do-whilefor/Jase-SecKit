# Flounder evidence reference

Read this for executable confirmation, real-target reproduction, evidence
packages, corpus selection, and report composition.

## Evidence Ladder

Do not present model suspicions as bugs. Keep these states distinct:

- `suspected`: plausible but not execution-proven, or downgraded by refutation.
- `confirmed-executable`: a cited local confirmation command triggered the bug.
- `confirmed-differential`: the exploit ran and the minimal fix blocked it.
- `reproduced`: confirm reproduced the finding against real-world ground truth.
- `not-reproduced` or `refuted`: the claim failed under attacker-real execution.
- `submit-candidate`: reproduced and scoped, with a collected submission package.

Findings should cite command evidence, PoC/test paths, differential results,
refutation or appeal outcomes, confirm decisions, report paths, and remaining
uncertainties.

## Collecting The Bug Package

For every bug candidate, collect:

- project and run id
- title, location, scope id, and status
- why the property matters
- exact command evidence or `command_id`
- PoC files or test path
- differential result, if any
- refutation or appeal result, if any
- confirm decision and its reason, such as reproduced, not-reproduced,
  submit-candidate, or drop
- report path and artifact paths
- scope match, duplicate/known-issue evidence, impact bounds, and remaining
  uncertainties

Do not present a list of model suspicions as bugs. Separate confirmed findings,
suspected findings, refuted findings, and reproduced submit candidates.
Describe the reproduction context and the engagement's evidence requirements
alongside each finding.

## Corpus Hygiene

Use project-owned official specs, docs, whitepapers, prior audits, design notes,
or strictly factual incident briefs as corpus. Corpus is context, not an answer.

Do not write answer-bearing materials that include the suspected bug, exact
location, mechanism, exploit recipe, historical incident name, transaction hash,
or report title when measuring blind recall. For incident investigation, keep the
clue factual and let Flounder derive the mechanism.

## Report Composition

Use repository-relative paths or explicit placeholders in generated reports.
Link evidence to the affected scope and describe each artifact's role in the
reproduction.

## Evidence Boundary And Submission Advice

Keep four axes separate: mandatory program compliance, the technical evidence
boundary, submission advice, and reward/duplicate adjudication risk. A
`reproduced` row must record whether execution was source-only local,
local integration, a local fork, or the real published target. Record the
engagement's accepted evidence context, including pinned source-only proof where
applicable. An unknown private duplicate or award amount is not itself a
failed technical confirmation or a failed mandatory submission term.

Attacker reachability, the claimed end-to-end effect, and impact bounds still
require evidence. Privileged access alone proves neither exploitability nor
safety. Preserve current-state/control evidence and distinguish a conditional
mechanism from a currently reproduced attack. Keep submission advice separate
from technical confirmation and reward or duplicate adjudication.
