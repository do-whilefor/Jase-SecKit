---
name: flounder
description: Hacking code audit tool
---

## What This Skill Must Do

- Turn a security-audit request into a Flounder project or run for whatever
  material the operator names.
- Keep the operator on the one-command workflow: `flounder run <clue>`
  (open-world prepare → sealed map/dig/synthesize/verify → open-world confirm
  → report); `flounder run --source <paths...> --build-root <root>` when
  source is already staged or external preparation is unwanted.
- Prefer the dashboard/API control plane so state, daemon ownership, live
  logs, findings, and reports stay durable.
- Preserve the evidence ladder — suspected, locally confirmed, real-target
  reproduced, submission-ready — and never collapse it into one "bug" bucket.
- Mark dismissed findings `ignored`, never delete them; recover from the
  Ignored filter.
- Report run health, coverage, findings, and the next action or blocker.

## Target And Material Mapping

Record the target, clue, link, address, project name, or scope statement with
its source and timestamp. Build a material inventory that relates:

- scopes, files, dependencies, build targets, and adjacent modules;
- deployments, published packages, fork networks, prior audits, and public
  repositories associated with the project;
- newly discovered deployments, sibling contracts, related packages, and
  upstream or downstream dependencies;
- program scope, organization or domain, and asset class.

Track these relationships transitively so each prepared asset retains its
connection to the original target and its material provenance.

## Audit Methodology

- **Exhaust before concluding.** Pending mapped scopes are work, not noise;
  when the inventory is exhausted and appetite remains, append-map novel
  scopes. A zero-finding run over unaudited scope is not
  a negative result.
- **Repair `shallow` or `needs-resource` runs.** Treat them as repair
  work: resolve the blocker (toolchain, sandbox, dependencies, source, auth)
  and rerun the blocked phase.
- **No unresolved suspicions.** Every `suspected` finding with available
  budget gets an execution attempt: verify or refute it.
- **Challenge weak verdicts.** When outcomes are incomplete, uncertain, or
  disagreeing across passes, rerun with more samples (`--dig-samples`,
  `--dig-max-samples`) instead of accepting the first verdict.
- **Push every candidate up the evidence ladder.** Map related materials,
  construct differential proof for locally confirmed findings, then reproduce
  against real-target ground truth when the engagement includes that target.
- **Compose, don't just enumerate.** Probe cross-scope chains and multi-step
  exploit paths rather than isolated single-file issues.
- **Max out throughput within capacity.** Use `--dig-concurrency`,
  `--verify-concurrency`, and multi-sample passes according to available capacity.
- **Contest tempo.** Short settled batches: verify/refute and report before
  opening the next batch, keep duplicate tracking current, append-map on
  exhaustion, and track elapsed review time, yield, duplicates, and backlog.

## Mode Routing

Classify the request into one row, then launch the smallest correct action.
Recipes and extended variants live in
[reference/examples.md](reference/examples.md).

| User intent | Mode and action | Method |
| --- | --- | --- |
| "Blind audit / test capability / no hints" | `flounder run <link>`; `flounder run --source <paths...> --build-root <root>` when source is staged | No incident docs, known bug names, exploit theories, or answer-bearing corpus. Judge by evidence status and coverage; a negative result is "no confirmed finding in covered scope". |
| "Why was this tx/address hacked?" | Incident investigation: `flounder run <tx-or-address-or-link>` | Clue is evidence, not proof. Confirm the root cause by attacker-real local reproduction (fork/replay). |
| "Audit this repo openly, like a hacker" | Open-world public-source audit: project with source paths plus a task/clue naming the project, bounty, repo, package, or deployment, then Run | Prepare collects official docs, scope, deployments, and provenance. |
| "Normal bounty / should we submit?" | Project with `engagement.kind="bug-bounty"` | Reproduce against real-target ground truth and record scope, duplicate, known-issue, impact, and submission-term evidence. |
| "Start this contest / maximize contest speed" | Project with `engagement.kind="bug-bounty-contest"` plus strategy (`batchScopes`, `digConcurrency`, `skipRealTargetConfirm`, `appendMapWhenExhausted`) | Use short verify/refute/report batches and append-map while preserving coverage and duplicate history. |
| "Continue coverage / resume the project" | Project **Continue** or `flounder continue --project <uuid\|name>` (REST: `POST /api/projects/<uuid>/runs` with `{"verb":"run"}`) | Inspect `latestRunHealth` and open backlog rows first; settle open Next Actions before unrelated fresh coverage. |
| "Just map the surface / show scope inventory" | `flounder map` | Inventory only, no findings. |
| "Dig this file/function/scope deeper" | `flounder audit <region>` or `flounder audit --scope <id,...>` with `--source ... --build-root ...` | Region- or scope-bounded. |
| "Check these suspected bugs" | `flounder audit --verify <claims.json>` (alias `flounder verify <file>`) | Confirm or refute by execution; return each claim as confirmed, refuted, or still suspected. |
| "Is this locally confirmed bug real on mainnet?" | `flounder confirm <run-dir>` or project/finding Confirm | Match the reproduction to the deployed target and its current state. |
| "Prepare submission package / regenerate reports" | `flounder report --project <uuid\|name>` for missing, `--finding <id>` selected, `--all` everything | Assemble execution evidence and artifact paths for the selected findings. |
| "Collect bugs for disclosure" | Read findings, reports, confirm decisions, and artifacts | Separate confirmed, suspected, refuted, and submit-candidate evidence. |
| "Triage noisy machine findings" | Tracking updates: `ignored` for dismissed, `open` to recover | Never delete; recover from the Ignored view. |
| "Run a benchmark / regression set" | `flounder group create --manifest <file>`, `flounder group start <uuid\|name>`; retry blocked items with `flounder group retry <work-item-id>` | Execution evidence for positives; zero confirmed findings on safe controls; repeated samples are separate items. |
| "Improve Flounder itself / raise recall" | `flounder ui --maintainer`, then [reference/maintainer-harness.md](reference/maintainer-harness.md) | Compare paired baseline/candidate Evaluations and prepare a reviewable source improvement. |

When in doubt: measuring unaided recall → blind capability audit with a
target-only clue; live exploit evidence → incident investigation; broad
project hunting with public context → open-world
public-source audit.

## Core Operating Rules

- Use Flounder CLI, dashboard, REST API, or pi extension workflows. Do not
  edit the tracking database directly.
- Keep provider credentials daemon-local. The server stores provider
  profiles; daemons own provider login, API keys, target source, and
  execution.
- Treat `~/.flounder` as the default product home: tracking DB, run
  artifacts, durable history/build cache, daemon workspace, and daemon-local
  provider auth live there unless the user explicitly passes `--out` or
  `--workspace`.
- Start with `flounder ui` unless the user already has a control plane
  running. CLI verbs are thin clients of that control plane; use `GET /api`
  before driving REST directly.
- Use project-owned docs/specs/audits as corpus. Do not write answer-bearing
  corpus that names the suspected bug, location, or mechanism.
- Treat `suspected` as unproven. Execution evidence distinguishes
  `confirmed-executable`, `confirmed-differential`, and reproduced findings.
- `flounder run <clue>` is the one-command workflow; `run --source`, `map`,
  and `audit` are sealed discovery phases; `prepare` and `confirm` are
  open-world phases.

## Setup And Run

1. Record the target, clue, scope statement, source, and timestamp as project
   provenance, then inventory the associated materials.
2. Classify the request through Mode Routing.
3. Check availability with `flounder --help`. If it is not on PATH but the
   repository is checked out, build it (`npm install && npm run build`) and
   use `node dist/cli.js` from the Flounder source checkout until installed or
   linked. Use Node 24 LTS from that checkout's `.nvmrc` / `.node-version`;
   never substitute newer experimental Node.
4. Start or reuse the control plane: `flounder ui`. For a remote executor,
   mint a token with `flounder server daemon-token mint`, then run
   `flounder daemon start --server http://<server>:4500 --token <token>`.
5. Authenticate every provider the selected daemon will run:
   `flounder daemon provider login <provider>` then
   `flounder daemon provider check <provider>`. OAuth versus API keys,
   DeepSeek/GLM setup, and custom model ids:
   [reference/models.md](reference/models.md).
6. Ensure a sandbox engine on the daemon machine: install and start Docker
   (or a compatible runtime), then `npm run sandbox:build`. Curated
   non-EVM images and Apple `container` paths:
   [reference/commands.md](reference/commands.md).
7. Create or reuse a project: task/clue, execution daemon, default provider
   profile (per-phase overrides: prepare, map, dig, confirm), project
   directory, source paths, build root, corpus paths, coverage and budget
   controls, engagement config for bounty or contest work. Exact fields:
   [reference/commands.md](reference/commands.md).
8. Start the audit. Leave **Run after create** checked to launch
   immediately; use **Run** before the first pipeline run and **Continue**
   afterward.
9. Monitor through the dashboard, CLI stream, or REST API:
   - current phase: prepare, map, dig, synthesis, verify, confirm, report;
     live log `GET /api/runs/:id/log`
   - project state: `GET /api/projects/:uuid`; inspect
     `prepareSummary.auditReady`, quality, `prepareSummary.blockingIssues`,
     source availability, and preparation caveats.
   - findings: `GET /api/projects/:uuid/findings?tracking=active` and
     `?tracking=ignored`; confirm decisions:
     `GET /api/projects/:uuid/confirm-decisions`
   - run health: `latestRunHealth.status` is `healthy`, `needs-coverage`,
     `needs-resource`, `shallow`, or `infra-failed`
   - discovery backlog: `GET /api/projects/:uuid/backlog?status=open` is an
     agent-owned queue (`agent-runnable`, `agent-resource`,
     `agent-review`); update rows with `PATCH /api/backlog/:id`

   Project names are display labels. Resolve a project UUID from
   `POST /api/projects` or `GET /api/projects`; do not build a project URL
   from the name.

## Deciding The Next Action

- No daemon online, provider check failing, or sandbox missing: fix setup
  first. Recovery table: [reference/commands.md](reference/commands.md). Do
  not bury setup failures as audit failures.
- Run health `needs-resource`: inspect open `resource-request` rows, retry
  toolchain/sandbox/dependency/source/auth setup, mark handled rows `resolved`,
  then rerun the blocked phase.
- Run health `needs-coverage`, or many pending high-score scopes: continue
  coverage or prioritize follow-up scopes from the backlog. Do not
  substitute "report more bugs" for coverage.
- Run health `shallow`: inconclusive; inspect logs and rerun or fix setup
  before summarizing.
- Open backlog Next Actions: resolve or route them before opening unrelated
  fresh coverage. They are not findings and never appear in a bug list
  unless a later execution-backed audit confirms one.
- Findings only `suspected`: make the target buildable and run verify or dig
  again.
- Confirmed locally but not reproduced: run confirm and record the target match,
  reproduction result, and any environment limitation. For `submit-candidate`,
  collect the evidence package.
- Contest inventory exhausted: append-map/Continue to expand novel scopes
  without losing prior scope status or submitted/duplicate history.
- No findings and material coverage is low: improve source/build/corpus
  setup or continue pending scopes before concluding.

Per-bug evidence packages and the four-axis evidence boundary are defined in
[reference/safety.md](reference/safety.md). Report packages record whether proof
comes from source-only execution, local integration, a fork, or a deployed target.

## Completion Snapshot

Summarize:

- the control plane is reachable (or a clear setup blocker is documented),
  the execution daemon is selected and online, and every used provider
  profile is authenticated on the daemon;
- the project has source paths, a build root, and corpus paths appropriate
  to the request, and prepared materials are `ready` or `limited` with every
  caveat carried into verify, confirm, and report decisions;
- the audit run reached a terminal state or a meaningful blocker, with
  latest run health and open discovery backlog rows summarized;
- scope coverage is summarized (mapped, audited, pending, deferred), and
  findings are grouped by status;
- confirmed findings went through confirm when real-target reproduction is
  required, ignored findings remain recoverable, and submit candidates
  include evidence and artifact paths;
- suspected, refuted, and not-reproduced items with their evidence and reasons.
