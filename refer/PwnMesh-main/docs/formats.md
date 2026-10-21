# Supported PwnMesh formats

Current formats are accepted without automatic migration of retired protocols.
See [protocol](protocol.md) for execution contracts and [recovery](recovery.md)
for restore procedures.

## Accepted inputs

| Boundary | Requirement |
| --- | --- |
| Database | Empty for initialization, or complete schema `4`, four-entry ledger and execution metadata `1` |
| Configuration | `PWNMESH_*` only; retired worker `type`, `runtime.execution` and `runtime.prompt_group` selectors are rejected |
| Project | Orchestration version `1` for execution and state changes |
| Execution | Fixed `worker_type: pi`, registered snapshot Job, live graph bridge, result contract `2`, Decide context `2`; roles `reason`, `explore`, `curate` |
| Recovery environment | Digest version `2` binds provider, container and configured tool settings; provider tokens are excluded |
| Worker session | Schema `4` only, including child sessions; identity, budget and canonical Pi checkpoint must match |
| Pi conversation | Native JSONL schema `3` only; context checkpoint `2` binds file, committed prefix hash and leaf; no inline import |
| Acceptance | Schema `1` in `acceptance.json`; an old `graph.json` alone cannot authorize recovery |
| Worker graph | Schema `1` with matching graph/node digests and complete reuse provenance |
| Evidence | Validated `.pwnmesh/runs/.../evidence/` references; no `.xloom` fallback |
| Tools | One structured result callback; `edit` requires an `edits` array |

HTTP timeouts must be JSON integers of at least `5`; strings, decimals and
exponent notation are rejected. Retired project protocols remain readable for
history but cannot authorize execution or evidence publication.

## Compatibility boundaries

- Execution and recovery require server-owned snapshots and matching environment
  identities. Inline Jobs and old Go conversation imports are unsupported.
- Current receipts take precedence over old graph files, subject to identity and
  evidence checks. Missing identity, evidence or receipts must never be invented
  or used to replay an old run. Unsupported files remain untouched.
- A committed curation receipt requires an atomically succeeded execution;
  inconsistent pending receipts cannot settle or replay.
- Preserve `pi-session.jsonl` with Worker session schema `4` and context checkpoint `2`.
  Go history and the original task prompt are rebuilt from Pi, never saved separately.
- Nonempty unversioned databases, old/future schemas, mixed namespaces, incomplete
  ledgers and unsupported execution metadata are rejected unchanged. Reopening
  preserves ledger timestamps and requires the current scheduling trigger.
- Graph errors require typed `Failure`; error text cannot grant recovery. Signed
  reasoning replays only with a known matching model origin.
- Preserve Job/State JSON order, tags and omission rules because they bind input
  hashes. Schema `4` rejects old inline state collections and header aliases.

## Changing binaries

Stop Server and Dispatcher. Back up SQLite consistently with its workspace,
journals, evidence and receipts; copying only an active WAL database file is
insufficient. Preserve installation identity and a pre-upgrade backup. Older data
needs a compatible release or migration tool; rollback to a binary without schema
`4` or Worker session schema `4` support requires a matching compatible backup.
