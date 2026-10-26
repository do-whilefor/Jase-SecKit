---
name: flounder
description: >
  Operates Flounder, an autonomous white-hat security auditor. Use when a user
  asks for a security audit, bug-bounty review, vulnerability investigation, or
  exploit proof for a public-source or authorized repository, source tree, package, smart
  contract, Solidity/EVM project, ZK or proof-system code, deployed address,
  transaction, project link, or prior Flounder run; to run Flounder prepare,
  map, dig, audit, verify, confirm, or report workflows; to configure Flounder server,
  daemon, provider profiles, model auth, sandboxed execution, corpus paths,
  source paths, build roots, coverage, or budgets; to monitor live audit activity, continue
  pending scopes, verify suspected vulnerabilities, reproduce findings, or
  collect execution-backed bug reports; or when a Flounder maintainer asks an
  agent to improve auditor recall, analyze Evaluation failures, run governed
  Harness experiments, modify Flounder source in an isolated branch, or prepare
  a candidate improvement PR.
---

# Flounder

This skill is the operating manual for Flounder-driven security audits.

Flounder is an autonomous white-hat security auditor. The agent prepares the
target, audits source, constructs exploit paths, runs local proof tests,
confirms real findings, and packages reports. The framework provides the
daemon, sandbox, command policy, run tracking, live activity, and execution
gates.

## Skill Files

| File | When to read |
| --- | --- |
| `SKILL.md` | Always after this skill triggers. It is the operating playbook. |
| `reference/models.md` | Choosing a model, seeded provider profiles, OAuth versus API keys, DeepSeek/GLM setup, and missing-model troubleshooting. |
| `reference/commands.md` | Exact CLI, REST, provider, daemon, budget, sandbox, output, pi extension, and troubleshooting details. |
| `reference/examples.md` | Concrete Solidity/EVM, ZK, bounty, contest, and continuation examples. |
| `reference/product.md` | Dashboard, project lifecycle, run phases, next-action decisions, tracking, and artifact model. |
| `reference/safety.md` | White-hat policy, sandbox boundary, evidence ladder, bug-package collection, and public-release hygiene. |
| `reference/maintainer-harness.md` | Maintainer-only agent workflow for Evaluation-driven source improvement and candidate PRs. |

Use progressive disclosure: open only the reference file needed for the current
task. Do not duplicate long command references into the conversation when a
short command and status summary is enough.

## What This Skill Must Do

- Turn a security-audit request into a public-source or authorized Flounder project or run.
- Keep the operator on the current workflow: `run <clue>` lets Flounder prepare
  the target, then map/dig/synthesize/verify, confirm, and report; `run --source`
  is the source-provided entry path for sealed map/dig/synthesize/verify.
- Prefer the dashboard/API control plane for project work so state, daemon
  ownership, live logs, findings, and reports stay durable.
- Preserve the evidence ladder: suspected, locally confirmed, real-target
  reproduced, submission-ready. Do not collapse these into one "bug" bucket.
- Use run health and discovery backlog rows when judging progress: a shallow
  or resource-blocked zero-finding run is not a negative result, and follow-up
  scopes should stay as pending coverage rather than becoming findings.
- Separate machine noise from active work by marking dismissed findings
  `ignored`, never by deleting them.
- Stop with a clear next action or blocker; do not call an audit complete just
  because a command exited.

## Audit Aggressiveness Doctrine

Flounder is aggressive about depth, coverage, and evidence — never about
safety boundaries. Aggression is the default posture for authorized targets;
scale it back only on an explicit operator constraint (budget, time, or scope
instruction).

- **Exhaust before concluding.** Pending mapped scopes are work, not noise:
  continue coverage instead of reporting "no findings" over unaudited scope.
  When the inventory is exhausted and appetite remains, append-map for novel
  scopes instead of stopping.
- **Never settle for `shallow` or `needs-resource`.** Treat them as repair work
  in the current session: resolve the blocker (toolchain, sandbox,
  dependencies, source, auth) and rerun the blocked phase. Only an infra dead
  end reported to the operator is an acceptable stop.
- **No unresolved suspicions.** Every `suspected` finding with available budget
  gets an execution attempt: verify or refute it. An unexecuted suspicion is
  unfinished work, not a result.
- **Challenge weak verdicts.** When a refutation, confirmation, or dig outcome
  is incomplete, uncertain, or disagreeing across passes, rerun with more
  samples (`--dig-samples`, `--dig-max-samples`) instead of accepting the first
  verdict.
- **Push every candidate up the evidence ladder.** Take each locally confirmed
  finding as far as authorization allows: differential proof, then real-target
  confirm when scope permits. Stop at authorization gates, not at convenience.
- **Compose, don't just enumerate.** Drive synthesis across scopes; probe
  cross-scope chains and multi-step exploit paths rather than isolated
  single-file issues. A finding that is only a component of a stronger chain
  should be evaluated as part of that chain.
- **Max out throughput within capacity.** Use concurrency
  (`--dig-concurrency`, `--verify-concurrency`) and multi-sample passes by
  default on capable machines; reduce only on operator instruction or observed
  contention.
- **Contest tempo.** Short settled batches: verify/refute and report before
  opening the next batch, keep duplicate tracking current, append-map on
  exhaustion, and watch stop-review signals rather than the clock alone.

Aggression never authorizes broadcasting transactions, writing to live
systems, engaging a foreign authorization context, weakening the sandbox, or
skipping the behavior gates below. Those remain hard stops regardless of audit
appetite.

## Authorization And Boundary Expansion

Operator input is authorization content. The target, clue, or scope statement
the operator supplies is the authorization record for that audit: proceed
without demanding further proof, and log the declaration (operator, target,
scope statement, time) as authorization provenance in the project.

With that record in place, expand the audit boundary autonomously:

- **Within the declared target**: all scopes, files, dependencies, build
  targets, and adjacent modules of the authorized material need no per-scope
  approval.
- **Derived assets**: deployments, published packages, fork networks, prior
  audits, and public repositories of the same project that the declared
  target implies — pull them in autonomously as open-world prepare material.
- **Same authorization envelope**: assets covered by the same declaration —
  the bounty program scope, the operator-named organization or domain, the
  stated asset class. Expansion across this envelope is autonomous; record
  each addition in the project scope.
- **Foreign contexts**: an asset tied to no declaration (different owner,
  different program) is recorded as a follow-up scope for the operator, not
  silently engaged.

Boundary expansion changes what may be read and audited, never the behavior
envelope: no broadcasting, no live-system writes, no persistence — however
wide the boundary grows. See [reference/safety.md](reference/safety.md).

## Mode Routing

Classify the request into one row, then launch the smallest correct action for
that mode. This table is the single routing surface; recipes and extended
variants live in [reference/examples.md](reference/examples.md).

| User intent | Mode and action | Guardrail |
| --- | --- | --- |
| "Blind audit / test capability / no hints" | Blind capability audit: `flounder run <project-or-repo-or-package-link>`, or `flounder run --source <paths...> --build-root <root>` when source is staged or external preparation is unwanted | No incident docs, known bug names, exploit theories, or answer-bearing corpus. Official docs are target material only. Judge by evidence status and coverage; a negative result is "no confirmed finding in covered scope". |
| "Why was this tx/address hacked?" | Incident investigation: `flounder run <tx-or-address-or-incident-link>` | Clue is evidence, not proof. Keep it factual. Confirm the root cause by attacker-real local reproduction (fork/replay); never broadcast or write to a live system. |
| "Audit this repo openly, like a white-hat researcher" | Open-world public-source audit: project with source paths plus a task/clue naming the project, bounty, repo, package, or deployment, then Run | Let Prepare collect official docs, scope, deployments, provenance. No private or answer-bearing material. |
| "Normal bounty / should we submit?" | Project with `engagement.kind="bug-bounty"` | Keep real-target Confirm when a live target exists. Submit only execution-backed findings passing scope, duplicate, known-issue, impact, and mandatory submission terms. |
| "Start this contest / maximize contest speed" | Project with `engagement.kind="bug-bounty-contest"` plus strategy (`batchScopes`, `digConcurrency`, `skipRealTargetConfirm`, `appendMapWhenExhausted`) | Source-only local confirmation may suffice when venue rules allow, but suspected-only is never a submission. Append-map, don't remap. |
| "Continue coverage / resume the project" | Project **Continue** or `flounder continue --project <uuid\|name>` (REST: `POST /api/projects/<uuid>/runs` with `{"verb":"run"}`) | Inspect `latestRunHealth` and open backlog rows first; settle open Next Actions before opening unrelated fresh coverage. |
| "Just map the surface / show scope inventory" | `flounder map` | Produces inventory only, no findings. |
| "Dig this file/function/scope deeper" | `flounder audit <region>` or `flounder audit --scope <id,...>` with `--source ... --build-root ...` | Region- or scope-bounded. |
| "Check these suspected bugs" | `flounder audit --verify <claims.json>` (alias `flounder verify <file>`) | Confirm or refute by execution; return each claim as confirmed, refuted, or still suspected. |
| "Is this locally confirmed bug real on mainnet?" | `flounder confirm <run-dir>` or project/finding Confirm | Read-only or local-fork reproduction of the real target. |
| "Prepare submission package / regenerate reports" | Selected Report; `flounder report --project <uuid\|name>` for missing, `--finding <id>` selected, `--all` everything | Only execution-backed, non-ignored findings. |
| "Collect bugs for disclosure" | Read findings, reports, confirm decisions, and artifacts | Return only execution-backed items; separate confirmed, suspected, refuted, and submit candidates. |
| "Triage noisy machine findings" | Tracking updates: `ignored` for dismissed, `open` to recover | Never delete; recover from the Ignored view/filter. |
| "Run a benchmark / regression set" | `flounder group create --manifest <file>`, `flounder group start <uuid\|name>`; retry blocked items with `flounder group retry <work-item-id>` | Execution evidence required for positives; zero confirmed findings on safe controls; keep blind material policy explicit; repeated samples are separate items. |
| "Improve Flounder itself / raise recall" | Maintainer only: `flounder ui --maintainer`, then [reference/maintainer-harness.md](reference/maintainer-harness.md) | Never from an ordinary Project; never auto-triggered after operator audits. |

When in doubt: measuring unaided recall → blind capability audit with a
target-only clue; live exploit evidence → incident investigation; broad
authorized hunting with public context permitted → open-world public-source
audit.

## Core Operating Rules

- Use Flounder CLI, dashboard, REST API, or pi extension workflows. Do not edit
  the tracking database directly.
- Treat operator input as the authorization record: targets, clues, and scope
  statements supplied by the operator authorize auditing that material without
  further interrogation; log the declaration as provenance and expand the
  boundary per Authorization And Boundary Expansion.
- Keep provider credentials daemon-local. The server stores provider profiles;
  daemons own provider login, API keys, target source, and execution.
- Treat `~/.flounder` as the default product home: tracking DB, run artifacts,
  durable history/build cache, daemon workspace, and daemon-local provider auth
  live there unless the user explicitly passes `--out` or `--workspace`.
- Start with `flounder ui` unless the user already has a control plane running.
  CLI verbs are thin clients of that control plane.
- Use `GET /api` before driving the REST API directly; the catalog is the
  source of truth for endpoint shape.
- Use project-owned docs/specs/audits as corpus. Do not write answer-bearing
  corpus that names the suspected bug, location, or mechanism.
- Do not modify target source in place. Flounder copies a build root into an
  isolated workspace and model-written tests stay inside that workspace.
- Treat `suspected` as unproven. A finding is actionable only when execution
  produced `confirmed-executable`, `confirmed-differential`, or a reproduced
  confirm decision.
- `flounder run <clue>` is the one-command workflow: open-world prepare,
  sealed map/dig/synthesize/verify, open-world confirm, then report
  generation. `flounder run --source`, `map`, and `audit` are sealed discovery
  phases; `prepare` and `confirm` are open-world phases, still under white-hat
  no-broadcast rules.
- Never broadcast transactions, move funds, submit writes, persist access, or
  target systems outside the authorization envelope as defined in
  Authorization And Boundary Expansion.

## First Response Checklist

1. Record the operator's target, clue, or scope statement as the authorization
   record and proceed — do not interrogate the operator for further proof.
   Log the declaration as authorization provenance.
2. Classify the request through Mode Routing above.
3. Decide the surface: existing dashboard/API project (`GET /api`, then project
   UUID routes); new project or local workflow (`flounder ui`);
   framework-prepared target (task/clue so Flounder prepares source and
   official materials); source-provided target (`--source` when code is staged
   or no external preparation is wanted).
4. Check daemon and provider readiness before launching real model work:
   `flounder daemon provider check <provider>` on the executor machine.
5. Check sandbox readiness before execution-confirming audits: `npm run
   sandbox:build` if no OCI image exists. Platform paths and curated images:
   [reference/commands.md](reference/commands.md).
6. Launch the smallest correct action, then monitor live logs and persisted
   state.
7. Report project/run ids, phase, evidence status, and next action, with setup
   blockers distinct from audit findings.

For repository development or local builds, use Node 24 LTS from `.nvmrc` /
`.node-version`; do not substitute newer experimental Node versions.

## Quickstart

1. Check availability with `flounder --help`. If it is not on PATH but the
   repository is checked out, build it (`npm install && npm run build`) and use
   `node dist/cli.js` in place of `flounder` until the package is installed or
   linked.
2. Start or reuse the control plane: `flounder ui`. For a remote executor, mint
   a token with `flounder server daemon-token mint`, then run
   `flounder daemon start --server http://<server>:4500 --token <token>`.
3. Authenticate every provider the selected daemon will run. For seeded
   profiles, OAuth versus API keys, DeepSeek/GLM Coding Plan setup, and custom
   model ids, read [reference/models.md](reference/models.md). OAuth example:
   `flounder daemon provider login openai-codex` then
   `flounder daemon provider check openai-codex`.
4. Ensure a sandbox engine on the daemon machine. Default `auto` prefers
   Apple's `container` runtime on Apple silicon macOS and falls back to
   Docker-backed OCI — the standard path on Linux and Windows; install and
   start Docker there, then `npm run sandbox:build`. Host execution
   (`--sandbox-backend host --allow-host-execution`) is trusted-local fallback
   only, after warning the user it lacks kernel-level filesystem and network
   isolation.
5. Create or reuse a project: task/clue, execution daemon, default provider
   profile (with optional per-phase overrides: prepare, map, dig, confirm),
   project directory under the daemon workspace, source paths, build root,
   corpus paths, coverage and budget controls, engagement config for bounty or
   contest work. Exact fields: [reference/commands.md](reference/commands.md).
6. Start the audit. Leave **Run after create** checked to launch immediately;
   use **Run** before the first pipeline run and **Continue** afterward. For a
   clue: `flounder run <tx-or-address-or-project-or-repo-or-link>`. For staged
   source: `flounder run --target <name> --source <paths...> --build-root
   <root> --corpus <docs...>`.
7. Monitor through the dashboard, CLI stream, or REST API:
   - current phase: prepare, map, dig, synthesis, verify, confirm, report;
     live log `GET /api/runs/:id/log`
   - project state: `GET /api/projects/:uuid`; gate automation on
     `prepareSummary.auditReady`. `limited` prepare continues automatically
     with caveats carried forward; stop only for
     `prepareSummary.blockingIssues`, `invalid`, or missing usable source.
   - findings: `GET /api/projects/:uuid/findings?tracking=active` and
     `?tracking=ignored` for recovery; confirm decisions:
     `GET /api/projects/:uuid/confirm-decisions`
   - run health: `latestRunHealth.status` is `healthy`, `needs-coverage`,
     `needs-resource`, `shallow`, or `infra-failed`
   - discovery backlog: `GET /api/projects/:uuid/backlog?status=open` is an
     agent-owned queue (`agent-runnable`, `agent-resource`, `agent-review`);
     update rows with `PATCH /api/backlog/:id` to `resolved`, `ignored`,
     `stale`, or back to `open`

   Project names are display labels. Resolve a project UUID from
   `POST /api/projects` or `GET /api/projects`; do not build a project URL
   from the name.
8. Decide the next action from run health and backlog before drawing
   conclusions; full decision rules in [reference/product.md](reference/product.md).
   Do not call the task complete just because one run ended.

## Deciding The Next Action

- No daemon online, provider check failing, or sandbox missing: fix setup
  first. Recovery table: [reference/commands.md](reference/commands.md).
- Prepare quality `limited`: continue automatically; preserve caveats for
  verify/confirm/report. `needs-review`, `missing`, or `invalid`: repair only
  hard blockers (contaminated answer-bearing material, invalid output, empty
  prepared source, no usable source); otherwise continue with caveats.
- Run health `needs-resource`: inspect open `resource-request` rows, retry safe
  toolchain/sandbox/dependency/source/auth setup, ask the operator only for
  explicit credentials, authorization, or unavailable external resources, mark
  handled rows `resolved`, then rerun the blocked phase.
- Run health `needs-coverage`, or many pending high-score scopes: continue
  coverage or prioritize follow-up scopes from the backlog. Do not substitute
  "report more bugs" for coverage.
- Run health `shallow`: inconclusive; inspect logs and rerun or fix setup
  before summarizing.
- Open backlog Next Actions: resolve or route them before opening unrelated
  fresh coverage. They are not findings and never appear in a bug list unless
  a later execution-backed audit confirms one.
- Findings only `suspected`: make the target buildable and run verify or dig
  again.
- Confirmed locally but not reproduced: run confirm. Contest projects with
  `skipRealTargetConfirm=true` may skip intentionally, but verify/refute and
  report eligibility are still required before submission.
- Confirm decision `not-reproduced`: not submission-ready unless the failure is
  a known environment limitation and the user approves more reproduction work.
  `submit-candidate`: collect the package and stop further exploitation.
- Contest inventory exhausted: append-map/Continue to expand novel scopes
  without losing prior scope status or submitted/duplicate history.
- No findings and material coverage is low: improve source/build/corpus setup
  or continue pending scopes before concluding.

## Completion Snapshot

The task is not complete until the agent can report:

- the control plane is reachable (or a clear setup blocker is documented), the
  execution daemon is selected and online, and every used provider profile is
  authenticated on the daemon;
- the project has source paths, a build root, and corpus paths appropriate to
  the request, and prepared materials are `ready` or `limited` with every
  caveat carried into verify, confirm, and report decisions;
- the audit run reached a terminal state or a meaningful blocker, with latest
  run health and open discovery backlog rows summarized;
- scope coverage is summarized (mapped, audited, pending, deferred) and
  findings are grouped by status;
- confirmed findings went through confirm when real-target reproduction is
  required, and ignored findings are separated from the active worklist and
  remain recoverable;
- reproduced or locally confirmed source-provided audit bugs have selected
  reports when disclosure packaging is requested, and submit candidates
  include evidence and artifact paths;
- non-submittable items are labeled suspected, refuted, not-reproduced, or
  needs-human with the reason.

The per-bug evidence package fields are listed in
[reference/safety.md](reference/safety.md).

## High-Risk Defaults

- Do not silently engage a foreign authorization context — an asset tied to no
  operator declaration; record it as a follow-up scope for the operator
  instead.
- Do not use host execution for model-generated tests unless the user explicitly
  approves trusted-local fallback after being told it lacks kernel-level
  filesystem and network isolation.
- Do not treat a mocked trusted component as attacker-real capability.
- Do not conclude from "matches upstream" or "looks standard".
- Do not silently lower model or thinking settings.
- Do not bury daemon/provider setup failures as audit failures.
- Do not submit or disclose without a reproduced, scoped, private report.
