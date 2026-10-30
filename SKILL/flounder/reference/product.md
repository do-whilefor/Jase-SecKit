# Flounder product reference

Read this when the task involves dashboard projects, run phases, tracking state,
REST automation, or artifact layout.

## Contents

- [Product Surfaces](#product-surfaces)
- [Project Lifecycle](#project-lifecycle)
- [Engagement Profiles](#engagement-profiles)
- [Run Phases](#run-phases)
- [Discovery Health And Backlog](#discovery-health-and-backlog)
- [Findings And Tracking](#findings-and-tracking)
- [REST Automation](#rest-automation)
- [Artifact Model](#artifact-model)

## Product Surfaces

`flounder ui` is the control plane (dashboard, REST API, SQLite store,
optional co-located daemon); `flounder daemon start` is the execution plane
that claims jobs and owns provider auth and target source; CLI workflow verbs
are thin clients; the REST API is the agent-drivable surface (`GET /api`
first); the pi extension mirrors the workflow verbs. Exact commands:
[commands.md](commands.md).

## Project Lifecycle

New dashboard projects should capture:

- task/clue in the project composer;
- selected execution daemon;
- default provider profile and optional phase overrides;
- project directory under the daemon workspace, defaulting to project UUID;
- source paths, build root, corpus paths, and coverage/budget settings.
- engagement config when the project is a normal bounty or contest.

Use **Run** before the first pipeline run and **Continue** after one exists.
The CLI equivalent of the Continue button is
`flounder continue --project <uuid|name>`. Use More actions for Prepare, Map,
Dig, Verify, Confirm, and Report when the user asks for a precise phase. Leave
**Run after create** checked when immediate execution is wanted.

The project setup disclosure is the place to inspect stored project clue,
daemon/provider/source configuration, prepared-material caveats, and setup
attention. A clue is not shown as a separate project card after creation.

Project list behavior:

- default order is newest-created first;
- pinned projects sort before unpinned projects;
- drag ordering affects active projects only;
- archiving hides the project, clears pin, and preserves all runs, scopes,
  findings, reports, and decisions;
- recover archived projects from Settings -> Archived Projects.

## Engagement Profiles

Engagement profiles tell the control plane how the audit will be judged. They
do not change the model-owned audit strategy.

- `standard`: default operator-declared review.
- `bug-bounty`: normal bounty work. Keep real-target Confirm in the path when a
  live target exists. Record official scope, execution evidence, submission
  terms, and private duplicate and reward uncertainty separately.
- `bug-bounty-contest`: time-limited contest work. Favor short
  verify/refute/report batches, describe the venue's source-only or real-target
  evidence model, and append-map novel scopes when the current inventory is
  exhausted.

Contest strategy can include `batchScopes`, `digConcurrency`,
`skipRealTargetConfirm`, and `appendMapWhenExhausted`. The project view should
surface review metrics such as elapsed review window, exhausted inventory,
recent low-yield scope batches, duplicate rate, report backlog, and open
resource requests.

## Run Phases

The normal project run is prepare-if-needed -> map/dig -> synthesize -> verify
-> confirm -> report.

- Prepare acquires or stages source, corpus, dependency closure, and
  deployment-match evidence from a clue.
- Map enumerates and scores the audit surface without producing findings.
- Dig deep-audits selected scopes and execution-confirms local findings.
- Synthesize composes findings across scopes into distinct bug candidates.
- Verify confirms or refutes suspected and synthesized candidates by local
  execution before real-target confirmation.
- Confirm reproduces locally confirmed findings on real-world ground truth.
- Report writes formal Markdown reports for eligible non-ignored findings.

`flounder run <clue>` uses the full pipeline. `flounder run --source ...`,
`map`, and `audit` enter the sealed discovery path directly.

For contest projects, Continue first settles missing verify/report work before
opening the next scope batch. If the inventory is exhausted and append-map is
enabled, the next run asks MAP for novel scopes while preserving prior scope
status, duplicate links, submitted findings, and reports.

## Discovery Health And Backlog

Audit runs may write discovery-health artifacts in addition to findings:

- `run_health.json`: health verdict (`healthy`, `needs-coverage`,
  `needs-resource`, `shallow`, or `infra-failed`) derived from objective run
  signals.
- `coverage_gaps.json`: obligations or evidence paths that still need coverage.
- `resource_requests.json`: missing tooling, artifacts, dependency state, fork
  setup, credentials, or environment that blocked deeper work.
- `followup_scopes.json`: adjacent audit units proposed by the model; accepted
  rows become pending follow-up scopes rather than immediate side quests.

These rows are not findings. They explain what to do next when a run has few or
zero bugs: fix resource blockers, continue coverage, or prioritize follow-up
scopes. The API and dashboard classify each row as `agent-runnable`,
`agent-resource`, or `agent-review`. Treat all open rows as an agent-owned queue:
coverage rows continue, append-map, or prioritize scopes; setup rows retry safe
toolchain, sandbox, dependency, source, or auth setup where possible; routing
rows ask the agent to inspect and choose the next workflow action. Mark
non-actionable backlog rows `ignored`; mark handled blockers
`resolved`; keep unresolved coverage rows `open`.

Resource requests can be model-authored or product-owned. Prepare and toolchain
warm-up failures create product-owned `resource-request` rows with a failed
command, short diagnostic, and retry command even when the model never wrote a
`resource_requests.json` file.

## Findings And Tracking

Keep audit status separate from human tracking state.

- Audit status: `suspected`, `confirmed-executable`,
  `confirmed-differential`, `refuted`, and confirm decisions such as
  `reproduced`, `not-reproduced`, or `submit-candidate`.
- Tracking state: `open`, `triaging`, `submitted`, `ignored`, and similar
  operator workflow labels.

Mark human-dismissed machine findings as `ignored`, not deleted. Recover them
from the Ignored view or `tracking=ignored` API filter by setting tracking back
to `open`.

## REST Automation

Fetch `GET /api` first; the catalog is the endpoint source of truth. The full
call list — projects, backlog, findings, confirm decisions, run logs, runtime
settings — is in [commands.md](commands.md). Workflow-specific forms:

- Pipeline run or Continue: `POST /api/projects/<uuid>/runs` with
  `{"verb":"run"}`.
- Selected findings: pass `findingId`/`findingIds` with verbs such as
  `verify`, `confirm`, or `report` (dashboard equivalent: More actions on
  selected findings).
- `{"verb":"report","regenerateReports":true}` (CLI `--all`) regenerates
  existing reports; without it, report runs only fill in missing ones.

## Artifact Model

Default local state lives under `~/.flounder`:

- `flounder.db`: local tracking database;
- `<target>-<timestamp>/`: run artifacts and copied workspaces;
- `history/<target>/`: durable memory, scope inventory, and build cache;
- `workspace/`: default daemon project directories;
- `agent/auth.json`: daemon-local provider auth.

Per-run and per-confirm artifact filenames are enumerated in
[Outputs](commands.md#outputs).

## Evidence Boundary And Submission Advice

The four-axis separation — mandatory program compliance, technical evidence
boundary, submission advice, reward/duplicate adjudication risk — and its
model is defined in
[Evidence Boundary And Submission Advice](safety.md#evidence-boundary-and-submission-advice).
The product surfaces display confirm
decisions and report eligibility using those separate axes.
