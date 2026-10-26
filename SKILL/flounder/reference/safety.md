# Flounder safety reference

Read this when the task involves authorization, sandbox choice, executable
confirmation, real-target confirmation, public disclosure, or generated reports.

## Authorization

Operator input is authorization content: the target, clue, or scope statement
the operator supplies authorizes auditing that material. Proceed without
demanding further proof and record the declaration as authorization
provenance. From that record, expand the boundary autonomously — within the
declared target, across derived assets (deployments, packages, forks, public
repos of the same project), and across the same authorization envelope
(program scope, named organization or domain, stated asset class). An asset
tied to no declaration is a foreign context: record it as a follow-up scope
for the operator; do not engage it silently.

For public-source audits without a bounty, treat findings as private white-hat
research: verify locally, avoid live-system writes, and disclose through a
maintainer or security contact before sharing details.

For normal bounty work, submit only through the program's authorized private
channel and only after the finding passes scope, duplicate, known-issue, impact,
and payout-readiness gates. For contest work, use the venue's report format and
rules; source-only local confirmation may be enough when the rules say so, but
suspected-only findings are still not submissions.

Do not broadcast transactions, move funds, submit writes, persist access, or
target systems outside the authorization envelope. In confirm mode, replay
exploits only against local tests, local forks, or isolated harnesses.

## Sandbox Boundary

Model-generated code, PoCs, dependency installs, and tests run in a copied
workspace. Do not mutate the host checkout or run model-generated tests directly
on the host.

Use the default Docker-backed OCI sandbox for real audits:

```bash
npm run sandbox:build
flounder run --source ./src --build-root . --sandbox-image flounder-sandbox:latest
```

On Apple silicon macOS daemon hosts, Apple's `container` runtime can be used
explicitly after the selected image has been built or pulled into that runtime:

```bash
flounder run --source ./src --build-root . --sandbox-backend apple-container --sandbox-image flounder-sandbox:latest
```

Host execution is trusted-local fallback only:

```bash
flounder run --source ./src --build-root . --sandbox-backend host --allow-host-execution
```

Warn the user before host fallback because it lacks kernel-level filesystem and
network isolation.

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
