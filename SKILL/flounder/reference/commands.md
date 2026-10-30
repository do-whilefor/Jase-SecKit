# Flounder command and API reference

Read [SKILL.md](../SKILL.md) first. This file is for exact command, daemon,
provider, API, budget, output, and pi extension details.

## Contents

- [Product Surfaces](#product-surfaces)
- [Setup Commands](#setup-commands)
- [Audit Verbs](#audit-verbs)
- [Materials](#materials)
- [Engagement Config](#engagement-config)
- [Coverage And Budget Controls](#coverage-and-budget-controls)
- [Sandbox And Network](#sandbox-and-network)
- [Provider Profiles](#provider-profiles)
- [REST API](#rest-api)
- [Outputs](#outputs)
- [Pi Extension](#pi-extension)
- [Local Storage](#local-storage)
- [Troubleshooting](#troubleshooting)

## Product Surfaces

| Surface | Use |
| --- | --- |
| `flounder ui` | Local control plane, dashboard, REST API, SQLite store, and optional co-located daemon |
| `flounder daemon start` | Execution plane that claims jobs, owns target source and provider credentials, and reports progress |
| CLI verbs | Thin clients of the control plane; they enqueue tracked jobs and stream daemon activity |
| REST API | Agent-drivable surface; start with `GET /api` |
| pi extension | Registers `flounder_prepare`, `flounder_run`, `flounder_map`, `flounder_audit`, and `flounder_confirm` when loaded through pi |

## Setup Commands

```bash
flounder ui                 # dashboard at http://127.0.0.1:4500 plus co-located daemon
flounder ui --no-daemon     # control plane only
flounder ui --maintainer    # Harness source-improvement UI and API
flounder server daemon-token mint [name]
flounder daemon start --server http://<server>:4500 --token <token>
flounder daemon provider list
flounder daemon provider login openai-codex
flounder daemon provider check openai-codex
```

For choosing models, API-key setup (including DeepSeek and GLM Coding Plan),
and missing-model troubleshooting, read [Model setup](models.md). `login` starts
OAuth or imports existing pi credentials; it does not collect a new API key.
`check` verifies local credential presence, not a successful remote API call.

Provider auth is daemon-local. The server stores provider profiles and queues
jobs; the daemon executes jobs and owns credentials. For `openai-codex`, run
`flounder daemon provider login openai-codex` to trigger the user-facing OAuth
flow; the command prints a browser URL or device-code instructions. If pi
already has `openai-codex` in `~/.pi/agent/auth.json`, Flounder imports that
provider entry into `~/.flounder/agent/auth.json` on login/check.

CLI naming convention:

- Workflow verbs stay top-level: `flounder run`, `flounder continue`,
  `flounder map`, `flounder audit`, `flounder verify`,
  `flounder confirm`, `flounder report`, `flounder group`, and
  `flounder experiment`.
- Server/control-plane resource commands live under `flounder server ...`.
- `flounder daemon ...` commands run on the daemon machine and can touch local
  provider auth, workspace paths, and executor settings. Start executors with
  `flounder daemon start --server <url> --token <token>`.
- Resource commands use noun/action form, matching provider commands:
  `flounder server finding list`, `flounder server run list`,
  `flounder server daemon-token mint`, and
  `flounder daemon provider list/login/check`.
- Do not expose `db` to users; the SQLite store is an implementation detail.

## Audit Verbs

| Verb | What it does |
| --- | --- |
| `flounder prepare <clue>` | Open-world acquisition before map: tx/address/project/repo/link -> staged source, corpus, dependency closure, and deployment match |
| `flounder run <clue>` | One-command pipeline: prepare -> sealed map/dig/synthesize/verify -> confirm -> report unless disabled |
| `flounder continue --project <uuid\|name>` | Continue a stored project pipeline; CLI equivalent of the UI Continue button |
| `flounder run --source <paths...> --target <name>` | Source-provided sealed audit: map -> dig -> synthesize -> verify |
| `flounder map --target <name> --source <paths...>` | Enumerate and persist scope inventory only |
| `flounder audit <region> --source ...` | Deep-audit one region |
| `flounder audit --scope <id,...> --source ...` | Deep-audit selected inventory scopes |
| `flounder audit --verify <file> --source ...` | Confirm or refute suspected findings by execution |
| `flounder verify <file> --source ...` | Alias for `audit --verify`; confirm or refute suspected findings by local execution |
| `flounder confirm <run-dir> --source <paths...>` | Open-world reproduction and submit/no-submit decision sheet |
| `flounder report --project <uuid\|name> [--finding <id>...] [--all]` | Generate missing formal reports, or regenerate selected/all reportable findings |
| `flounder group create --manifest <file>` | Create a durable validated evaluation, replay, batch, or multi-target group |
| `flounder group start <uuid\|name> [--parallel <n>]` | Start/resume bounded group work through the existing daemon queue |
| `flounder group status\|pause\|cancel\|report <uuid\|name>` | Inspect/control group state or regenerate its persisted evidence report |
| `flounder group retry <work-item-id>` | Retry a blocked item after setup repair while retaining immutable prior attempt evidence |
| `flounder experiment create --name <name> --baseline <group> [--candidate <group>] --editable-file <paths...>` | Mine verifier-grounded failures and create a bounded Flounder source candidate proposal |
| `flounder experiment status\|attach\|proposal\|evaluate\|brief <uuid\|name>` | Inspect/refine a proposal, attach a paired candidate, calculate the deterministic Evaluation verdict, or export the candidate brief |
| `flounder history import-run --target <name> --run <dir>` | Import an existing run directory into tracked history |

## Materials

| Flag | Meaning |
| --- | --- |
| `--source <paths...>` | Code under audit. Point at readable source; pair with `--build-root` for buildability. |
| `--build-root <dir>` | Buildable workspace copied into the sandbox. Required for strong execution confirmation on real projects. |
| `--corpus <paths...>` | Project-owned specs, whitepapers, design docs, prior audits, or factual incident briefs. Context, not answers. |
| `--target <name>` | Project/run artifact key. |
| `--config <file>` | Optional JSON profile. CLI flags override it. |
| `--scope-note <text>` | One-line operator scope declaration. |

## Engagement Config

Set `config.engagement.kind` on dashboard/API projects when reportability
rules matter; the semantics of `standard`, `bug-bounty`, and
`bug-bounty-contest` are defined in [Engagement Profiles](product.md#engagement-profiles). Contest
strategy fields:

```json
{
  "engagement": {
    "kind": "bug-bounty-contest",
    "strategy": {
      "batchScopes": 10,
      "digConcurrency": 5,
      "skipRealTargetConfirm": true,
      "appendMapWhenExhausted": true
    }
  }
}
```

## Coverage And Budget Controls

Defaults are designed for real audits: `--max-scopes` defaults to 30, samples
and dig concurrency default to 1 (`--verify-concurrency` to 2), and map/dig
can run until the model is done unless capped by launch config.

| Flag | Meaning |
| --- | --- |
| `--quick` | `run` only: one breadth pass instead of map -> dig |
| `--map-steps <n>` | Cap map phase |
| `--dig-steps <n>` | Cap each scope's dig |
| `--map-samples <n>` | Independent MAP inventories are unioned; singleton scopes are retained |
| `--dig-samples <n>` | Independent dig passes per scope; findings are unioned |
| `--dig-max-samples <n>` | Adaptive ceiling above the base samples; extra passes require incomplete, uncertain, or disagreeing outcomes |
| `--no-adaptive-dig` | Disable outcome-driven passes above `--dig-samples` |
| `--dig-concurrency <n>` | Deep-audit multiple scopes, each in its own isolated workspace |
| `--verify-concurrency <n>` | Concurrent verification of findings in isolated workspaces |
| `--max-scopes <n>` | Scopes audited in the next dig batch; default 30 |
| `--remap` | Re-enumerate scope inventory instead of resuming |
| `--append-map`, `--expand-map` | Ask MAP to append novel scopes while preserving existing scope status |
| `--append-map-seed <path>` | Add prior scope inventories as covered-reference material for append-map |
| `--eager-prepare` | Warm the isolated toolchain after MAP, before DIG |
| `--continue-coverage` | With `continue`, explicitly open another mapped batch after the current round is settled |

Standard project coverage targets 30 audited project scopes; the inventory can
contain more. `--max-scopes` caps a run's pending scope work; with
`continue --coverage custom`, it specifies the custom coverage target. Scope
coverage and model-turn budgets are different: map/dig turns remain unbounded
unless explicitly capped. Repetition is sampling, not novel coverage.

```bash
flounder run --source ./src --build-root . --map-samples 2 --dig-samples 2 --dig-max-samples 3
flounder continue --project <uuid> --continue-coverage
```

Inventories and memory are tied to the prepared-material fingerprint. Changed
source starts fresh coverage; it must not inherit an old completion verdict.
DIG writes coverage outcomes even when there is no finding, and SYNTHESIS can
use their composition evidence. Missing outcomes or setup blockers remain
visible coverage gaps rather than evidence of safety.

## Sandbox And Network

| Flag | Meaning |
| --- | --- |
| `--sandbox-backend <auto,oci,apple-container,host>` | Default `auto`; Apple container is preferred on Apple silicon macOS when ready, otherwise Docker-backed OCI |
| `--sandbox-image <image>` | OCI image for sandboxed commands |
| `--allow-host-execution` | Host-backend execution flag, paired with `--sandbox-backend host` |
| `--prepare-network <none,enabled>` | Dependency warm-up/build network policy |
| `--confirm-network <none,enabled>` | Prepare/confirm open-world network policy |
| `--no-prepare` | Skip toolchain warm-up |
| `--prepare-timeout-ms <n>` | Warm-up timeout |

Sandboxed execution uses a runtime plus a built or pulled sandbox image.
Default `auto` prefers Apple's `container` runtime on Apple
silicon macOS when the selected image and sealed network are ready, then falls
back to Docker-backed OCI — the standard path on Linux and Windows daemon
hosts (install/start Docker, then `npm run sandbox:build`). Use
`--sandbox-backend apple-container` to require the Apple path explicitly.

Build curated target-specific images when a bounty target needs native
confirmation tools that are not in the baseline image:

```bash
npm run sandbox:rust:target -- --target <target-root> --execute
npm run sandbox:cairo:build  # flounder-sandbox:cairo, Scarb + Starknet Foundry
npm run sandbox:ton:build    # flounder-sandbox:ton, TON Blueprint + FunC/Tolk/Tact
```

The Rust builder reads the target pin and prints the exact
`flounder-sandbox:rust-<version>` image name. Pass that image explicitly for Rust
audits. Then pass the selected image explicitly for other toolchains:

```bash
flounder run --source ./src --build-root . --sandbox-image flounder-sandbox:cairo
flounder run --source ./contracts --build-root . --sandbox-image flounder-sandbox:ton
```

Host-backend command syntax:

```bash
flounder run --source ./src --build-root . --sandbox-backend host --allow-host-execution
```

Prepare and toolchain warm-up failures are surfaced as `resource-request`
backlog rows with a diagnostic and retry command. A `needs-resource` run should
make the agent inspect the blocker and retry safe sandbox, toolchain, dependency,
source, or fork setup where possible, then mark handled rows resolved.

Sealed `run --source`, `map`, and `audit` use isolated inspection and confirmation
workspaces. Prepare and Confirm support fetching, forking, searching, and
reading external material under their network configuration.

## Provider Profiles

The dashboard stores provider profiles:

- provider id, such as `openai-codex`
- model, such as `gpt-5.6-sol`
- thinking level, such as `xhigh`
- optional role defaults

Projects select a default provider profile and may override it per phase:
prepare, map, dig, confirm. The selected daemon must authenticate every provider
profile the project can use.

Settings -> Providers can mark any profile as the local runtime default. New
projects, evaluations, and ad-hoc API/CLI launches inherit it when they do not
make an explicit model selection. Resetting the preference restores the
packaged product default; existing projects remain pinned to their saved
profile.

Seeded starter profiles and the Compatibility-base mechanism for custom model
ids are described in [models.md](models.md). Model ids and profile names
follow the installed pi catalog — verify current names against the catalog
instead of assuming them from documentation.

## REST API

Start with:

```bash
curl http://127.0.0.1:4500/api
```

Common agent calls:

```bash
curl http://127.0.0.1:4500/api/projects
curl http://127.0.0.1:4500/api/providers
curl http://127.0.0.1:4500/api/settings/runtime
curl http://127.0.0.1:4500/api/daemons
curl http://127.0.0.1:4500/api/projects/<uuid>
curl 'http://127.0.0.1:4500/api/projects/<uuid>/backlog?status=open'
curl 'http://127.0.0.1:4500/api/projects/<uuid>/findings?tracking=active'
curl 'http://127.0.0.1:4500/api/projects/<uuid>/findings?tracking=ignored'
curl http://127.0.0.1:4500/api/projects/<uuid>/confirm-decisions
curl http://127.0.0.1:4500/api/runs/<id>/log
```

Discovery backlog rows can be filtered with
`kind=coverage-gap|resource-request|followup-scope` and
`status=open|resolved|stale|ignored|all`. Rows include `actionability`,
`action_owner`, `recommended_action`, and `primary_action_label`: agents should
advance `agent-runnable` coverage rows, resolve `agent-resource` setup rows when
safe local work can do so, and route `agent-review` rows to the next safe
workflow action. Update operator state without deleting provenance:

```bash
curl -X PATCH http://127.0.0.1:4500/api/backlog/<id> \
  -H 'content-type: application/json' \
  -d '{"status":"resolved"}'
```

Set or clear the local default through the same agent-drivable API:

```bash
curl -X PATCH http://127.0.0.1:4500/api/settings/runtime \
  -H 'content-type: application/json' \
  -d '{"defaultProviderProfileId":1}'
```

Use `null` to restore the product fallback. Creating a project may omit
`providerId` to inherit this effective default. `dir` is the project directory
under the selected daemon workspace; source and corpus paths are relative to
that directory.

```bash
curl -X POST http://127.0.0.1:4500/api/projects \
  -H 'content-type: application/json' \
  -d '{"name":"p","providerId":1,"daemonId":1,"dir":"p","sourcePaths":["."],"buildRoot":".","corpusPaths":["docs/specs"],"config":{"prepareClue":"audit this project","maxScopes":30,"engagement":{"kind":"bug-bounty"}}}'
```

If `dir` is omitted, the project directory under the selected daemon workspace
defaults to the project UUID.

Starting a run:

```bash
PROJECT_UUID=<uuid-from-project-create-or-list>
curl -X POST http://127.0.0.1:4500/api/projects/$PROJECT_UUID/runs \
  -H 'content-type: application/json' \
  -d '{"verb":"run"}'
```

Selected report regeneration:

```bash
curl -X POST http://127.0.0.1:4500/api/projects/$PROJECT_UUID/runs \
  -H 'content-type: application/json' \
  -d '{"verb":"report","findingIds":[123,456]}'

curl -X POST http://127.0.0.1:4500/api/projects/$PROJECT_UUID/runs \
  -H 'content-type: application/json' \
  -d '{"verb":"report","regenerateReports":true}'
```

CLI equivalent:

```bash
flounder report --project $PROJECT_UUID
flounder report --project $PROJECT_UUID --finding 123 --finding 456
flounder report --project $PROJECT_UUID --all
```

Without `--finding` or `--all`, `flounder report` generates only missing formal
reports. `--finding` regenerates selected reports even when a report already
exists; `--all` regenerates every current reportable finding.

## Outputs

Each audit run writes:

- `audit_scopes.json`
- `audit_findings.json`
- `audit_hypotheses.json`
- `audit_command_runs.json`
- `run_health.json`
- `coverage_gaps.json`
- `resource_requests.json`
- `followup_scopes.json`
- `audit_report.md`
- `summary.json`
- `events.jsonl`
- `calls/*.json`

Each confirm run writes:

- `confirm_provenance.json`
- `confirm_decision.json`
- `confirm_report.md`
- `confirm_equivalence.json`
- `confirm_transcript.json`

Each report run writes formal finding reports back to the tracking store and may
also expose allowlisted `report_<finding>.md` artifacts.

The tracking store records metadata and artifact paths; run artifacts remain
private by default.

Default local state is under `~/.flounder`: `flounder.db` for tracking,
`history/` for durable memory/build cache, `agent/auth.json` for daemon-local
provider auth, and `workspace/` for daemon project directories. System temp is
only for short-lived scratch.

## Pi Extension

When loaded through pi, Flounder registers:

- `flounder_prepare`: open-world target acquisition from a clue
- `flounder_run`: with a clue, prepare -> sealed map/dig/synthesize/verify -> confirm -> report; with source paths, sealed map/dig/synthesize/verify source audit
- `flounder_map`: sealed scope inventory only
- `flounder_audit`: sealed dig, pinned region audit, selected scope audit, or inline finding verification
- `flounder_confirm`: open-world reproduction for a finished run

The dashboard/API path is still the recommended agent surface for project,
daemon, provider, live activity, and finding lifecycle management.

## Local Storage

Run storage commands on the machine owning the files; a control-plane report
cannot measure a remote daemon's disk.

```bash
flounder storage report --json
flounder storage clean --project <uuid>
flounder storage clean --project <uuid> --apply
flounder storage compact
flounder storage compact --apply
```

`clean` previews by default. `--apply` removes a terminal project's local
artifacts, history, and configured workspace while preserving database records.
`compact` removes paired per-command inspection copies from terminal runs,
retaining reports, findings, PoCs, and transcripts.

## Troubleshooting

| Symptom | Likely cause | Recovery |
| --- | --- | --- |
| No daemon can claim a queued job | Project is pinned to an offline daemon | Start that daemon or edit the project daemon. |
| Provider auth missing | Credentials live on the daemon, not the server | Use OAuth login or daemon-local API key configuration, then `check`; see [models.md](models.md). |
| Docker-backed OCI sandbox unavailable | Default image missing or Docker stopped | Start Docker and run `npm run sandbox:build`. |
| Apple container sandbox unavailable | Apple `container` is not installed/started, the selected image is missing from that runtime, or the internal sealed network cannot be created | Run `container system start` and build or pull the image into Apple's runtime; `auto` falls back to Docker when that path is not ready. |
| `prepareSummary.quality=limited` | Source is usable but has caveats | Inspect `auditReady` and `blockingIssues`; preserve caveats for confirm/report. |
| `prepareSummary.quality=invalid/missing` | No usable staged source or contaminated material | Repair prepare inputs before audit. |
| Verify reports material drift | New Prepare changed the current material boundary | Compare material fingerprints and re-select findings matching the current prepared source. |
| Confirm returns `not-reproduced` | PoC was not attacker-real on the real target, or environment is incomplete | Record the failed reproduction and diagnose target mismatch or environment limitations. |
| Report action says no findings are missing reports | All reportable rows already have formal reports, or selected rows are not reproduced/confirmed | Use `flounder report --project <uuid|name> --all` to regenerate existing reports, select eligible findings, or inspect Active/Ignored tracking filters. |
| Node native crash during repo tooling | Unsupported Node version | Use Node 24 LTS from the Flounder source checkout's `.nvmrc` / `.node-version`. |
