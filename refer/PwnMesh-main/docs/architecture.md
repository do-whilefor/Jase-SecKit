# PwnMesh architecture

PwnMesh is a Linux application with three commands: `serve`, `dispatch` and
`worker`. Server owns authoritative SQLite state. Dispatcher schedules work
through Server and launches Docker Workers. Workers retain journals, artifacts
and acceptance receipts in their workspace.

```text
Browser -> Server -> execution / Board -> private sqlstore -> SQLite
              ^
Dispatcher ---+  prepare, register, heartbeat, settle
    |
    +-> Docker -> Worker -> Pi Agent -> tools / workspace evidence
           |         |
           +---------+-> graph bridge -> Server
           +-----------> model bridge -> configured provider
```

## Component boundaries

| Location | Responsibility |
| --- | --- |
| `cmd/`, `internal/config/`, `internal/modelconfig/` | Process wiring and configuration |
| `internal/server/` | HTTP handling and transaction selection |
| `internal/execution/` | Preparation, registration, settlement and recovery |
| `internal/board/` | Business validation and transactional operations |
| `internal/board/model/` | Storage-free state and shared execution values |
| `internal/board/internal/sqlstore/` | SQLite schema, queries and persistence |
| `internal/board/internal/projection/` | Pure dependency and evidence projections |
| `internal/protocol/` | Job/result contracts and identity binding |
| `internal/controlclient/`, `internal/graphgateway/` | Typed Server access and registered Worker graph requests |
| `internal/launchbridge/` | Transport-independent model and graph RPC lifecycles |
| `internal/dispatcher/` | Selection, capacity, recovery ordering and model readiness |
| `internal/dispatchrun/` | Execution, leases, settlement, cancellation and cleanup |
| `internal/docker/` | Container transport and workspace management |
| `internal/worker/`, `internal/worker/dag/`, `internal/workergraph/` | Execution phases, tools, local dependencies and evidence acceptance |
| `runtime/pi/` | Vendored Pi Agent, SessionManager and context compaction source |
| `internal/agent/`, `internal/provider/`, `internal/modelrpc/` | Pi host adapter, provider client and bridge contract |
| `internal/modelwire/`, `internal/modelauth/` | Request encoding and authentication policy |

Execution clients use `board/model`; Board composes domain operations over its
private store. Server selects transactions without running SQL. Pure projections
neither query storage nor mutate their inputs.

Dispatcher reads immutable run identities and consumes completion events.
The execution manager owns live tasks and cleanup state, without accessing
scheduling policy. Each launch keeps its assigned model environment and budget.

Server owns saved model settings and OAuth refresh credentials. Dispatcher reads
runtime settings through `modelcontrol`, authenticated by `PWNMESH_CONTROL_TOKEN`
and its active ownership lease; refresh tokens never leave Server. Use HTTPS
outside a trusted local network. `model_settings_source: file` explicitly retains
local configuration. Compose Dispatcher mounts neither data nor auth.

## State and authority

`Store.Do` wraps checks, mutations, revisions and receipts in one immediate write
transaction. Execution use cases receive the caller's `board.Tx`; Store owns
commit and rollback. Composed operations use savepoints, and cleanup failures
must propagate so partial writes cannot commit.

`Store.View` provides consistent, read-only snapshots. File-backed stores use WAL
readers; private in-memory stores enforce the same read-only contract. Reads can
account for expired leases without reserving the writer. Reads that pin decision
state and decision previews use write transactions.

Board enforces generation and lease fences, authorization, idempotency, retry
eligibility and completion rules. Caches and scheduling projections are disposable
and never replace those checks. Restart archives the round and revokes old work
atomically before resetting current state. History and retained inputs survive.
See [formats](formats.md) for supported schemas and compatibility boundaries.

## Roles and evidence

- **Decide** plans Steps and commits control changes in a versioned decision batch.
- **Execute** runs a registered Step, publishes Facts/Candidates and verifies
  retained evidence before acceptance.
- **Curate** uses immutable input to reconcile Candidates, Findings and corrections.

A model response alone cannot establish success: Execute requires accepted
evidence; successful Decide and Curate mutations require server commit receipts.
A local DAG coordinates work and files; finishing it does not publish a shared
Fact or complete a Step.

Facts are immutable observations. Explicit `derived_from` edges and accepted Step
prerequisites determine support. Corrections invalidate dependent evidence and
results, while independent observations remain independent. Assets and discovery
links help locate records; they do not establish evidence, permissions or coverage.
Role actions, curation requests and wire identities are defined in
[protocol](protocol.md).

## Bridges and isolation

The model bridge keeps provider endpoints and credentials in Dispatcher. Worker
requests cannot select either, and credential checks reject provider credentials
in Worker jobs and tool environments. Worker and Provider share credential-free request
encoding so input sizing and upstream transport use the same contract.
Credential-free model descriptors identify response origins; signed reasoning
replays only when the model, API and endpoint identity match.

The graph bridge binds requests to the launched Job, validates role operations
and forwards them through Dispatcher to Server. Server still checks execution
authority and versions. Bridge deadlines and cancellation remain bound to the
launch; a bridge never grants independent authority to a Worker.

DAG path declarations coordinate cooperating nodes. Conflicting paths require
ordering, and shared workspace declarations must fit the Step's `write_paths`.
These declarations do not restrict arbitrary shell access or resolve filesystem
aliases; they are not a filesystem sandbox.

## Execution and recovery

Dispatcher reconciles registered executions before admitting new work and stops
Workers before releasing dispatcher ownership. Pi SessionManager retains native
`pi-session.jsonl` transcripts. Go records a committed byte/hash/leaf checkpoint
with execution policy; durable transitions precede side effects. Pi owns replay
and compaction. Go rebuilds transient history and the original task prompt from Pi.
Recovery verifies committed journals and receipts before further model/tool calls.
Saved results can be delivered again without replaying work.

Local DAG reuse verifies source identity and retained artifacts. It does not
re-observe a mutable target or authorize replay of uncertain effects. See
[recovery](recovery.md) for interruption, retry and restore rules.

## Instructions and browser

Model instructions are split between shared request rules, Worker role/scenario
prompts and field-local tool schemas. Session code owns phase transitions;
Pi receives request policy through hooks without knowing Worker phases.
Providers supply exact request sizing and a separate summary allowance.
Selected tools contribute deduplicated guidance that disappears when tools are
disabled. Structured tool details remain in Pi receipts, outside model messages.
Investigation skills load on demand.

Vue 3, TypeScript and Vite build `web/dist`, which Go embeds. Node also runs the
Pi kernel in Workers. Browser resources own accepted reads, caches and polling. Client
checks and display projections never replace server authority. Public model
settings expose selected operator fields, while saved credentials remain under
server settings coordination. `httpui` mounts optional assets at process startup;
the API does not import Web. See [development](development.md) for checks.
