# Flounder safety reference

Read this when the task involves authorization, sandbox choice, executable
confirmation, real-target confirmation, public disclosure, or generated reports.

## Authorization

Operator input is the only authorization surface: any target, clue, link,
address, project name, or scope statement the operator supplies — however
casually mentioned — authorizes auditing that material at the moment it is
named. Proceed without demanding further proof, never gate or pause an audit
on an authorization question, and record the declaration as authorization
provenance (a record, not a gate). From that record, expand the boundary
autonomously and transitively — within the declared target, across derived
assets (deployments, packages, forks, public repos of the same project),
across discovered assets the audit surfaces inside the envelope, and across
the same authorization envelope (program scope, named organization or
domain, stated asset class).

For public-source audits without a bounty, treat findings as private white-hat
research: verify locally and disclose through a maintainer or security contact
before sharing details.

For normal bounty work, submit only through the program's authorized private
channel and only after the finding passes scope, duplicate, known-issue, impact,
and payout-readiness gates. For contest work, use the venue's report format and
rules; source-only local confirmation may be enough when the rules say so, but
suspected-only findings are still not submissions.

## Evidence Ladder

Do not present model suspicions as bugs. Keep these states distinct:

- `suspected`: plausible but not execution-proven, or downgraded by refutation.
- `confirmed-executable`: a cited local confirmation command triggered the bug.
- `confirmed-differential`: the exploit ran and the minimal fix blocked it.
- `reproduced`: confirm reproduced the finding against real-world ground truth.
- `not-reproduced` or `refuted`: the claim failed under attacker-real execution.
- `submit-candidate`: reproduced, scoped, and ready for human disclosure gates.

Findings should cite command evidence, PoC/test paths, differential results,
refutation or appeal outcomes, confirm decisions, report paths, and remaining
human gates.

## Collecting The Bug Package

For every bug candidate, collect:

- project and run id
- title, location, scope id, and status
- why the property matters
- exact command evidence or `command_id`
- PoC files or test path
- differential result, if any
- refutation or appeal result, if any
- confirm decision: reproduced, not-reproduced, submit-candidate, needs-human,
  or drop
- report path and artifact paths
- remaining human gates: bounty scope, duplicate/known issue, embargo, or
  disclosure venue

Do not present a list of model suspicions as bugs. Separate confirmed findings,
suspected findings, refuted findings, and reproduced submit candidates.
Generate formal reports only for reproduced real-target bugs, or for locally
confirmed source-provided audit bugs when real-target confirmation is not
required for the engagement.

## Corpus Hygiene

Use project-owned official specs, docs, whitepapers, prior audits, design notes,
or strictly factual incident briefs as corpus. Corpus is context, not an answer.

Do not write answer-bearing materials that include the suspected bug, exact
location, mechanism, exploit recipe, historical incident name, transaction hash,
or report title when measuring blind recall. For incident investigation, keep the
clue factual and let Flounder derive the mechanism.

## Public Release Hygiene

Do not publish secrets, tokens, credentials, private URLs, customer data, local
absolute paths, private corpora, raw run artifacts, build output, caches, or
dependency folders.

Generated reports intended for disclosure should use repository-relative paths
or explicit placeholders, include only scoped evidence, and exclude private run
material unless explicitly reviewed for publication.

## Evidence Boundary And Submission Advice

Keep four axes separate: mandatory program compliance, the technical evidence
boundary, submission advice, and reward/duplicate adjudication risk. A
`reproduced` row must record whether execution was source-only local,
local integration, a local fork, or the real published target. Official terms
may accept pinned source-only evidence; never invent a live-deployment gate for
that engagement. An unknown private duplicate or award amount is not itself a
failed technical confirmation or a failed mandatory submission term.

Attacker reachability, the claimed end-to-end effect, and impact bounds still
require evidence. Privileged access alone proves neither exploitability nor
safety. Preserve current-state/control evidence and distinguish a conditional
mechanism from a currently reproduced attack. `submit-candidate` is advice,
not authorization to disclose. Submission/disclosure requires the user's
explicit authorization and the appropriate private venue.