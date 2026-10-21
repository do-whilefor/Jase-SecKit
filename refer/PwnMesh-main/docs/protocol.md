# PwnMesh protocol

[Wire types](../internal/protocol/types.go): `Job` inputs, `Result` outcomes;
roles Decide=`reason`, Execute=`explore`, Curate=`curate`.
See [architecture](architecture.md) for component ownership.

## Versions and identity

| Boundary | Contract |
| --- | --- |
| Project | `orchestration_version: 1` |
| Execution | `result_contract_version: 2`, `graph_rpc: true` for all roles |
| Decide context | Version `2` |
| Immutable input | Version `1`, bound to project, generation and state digest |
| Agent checkpoint | Version `2`, bound to the canonical Pi session |

Unsupported protocols cannot execute, resume, apply or retry.
See [supported formats](formats.md) for storage, session and receipt versions,
compatibility and upgrade requirements.

## Registration, authority and settlement

1. Server registers immutable input bound to project, run, kind, backend,
   namespace and lease (`backend@run_id`). Dispatcher enforces ownership/capacity;
   Docker binds transport and graph/model bridges to that launch.
2. Workers use bounded inputs and operations under the registered authority.
   Digests, revisions and expected versions reject stale inputs.
3. Execute verifies retained evidence before acceptance. Decide/Curate use
   authoritative server commit receipts. Checks, mutations and receipts are atomic.
4. Saved results can be redelivered without replaying model/tools. Settlement
   checks generation, lease and idempotency; restart increments generation and
   revocation tombstones fence late workers. See [recovery](recovery.md).

Step management and project completion use decision batches; Step completion
uses the registered result contract. Retired direct intent/completion routes
return `404`. Reads and discovery hints never grant write authority.

## Graph reads and errors

- Graph RPC is limited to 128 KiB; pages reserve 1 KiB for the envelope.
  Requests validate IDs, digests, offsets and operations against the Job.
- Preserve section, IDs and asset filters while paging. Fragmented records use
  `record_offset`, `next_byte_offset`, `state_version` and `record_version`;
  concatenate all fragments before parsing. See [paging](../internal/protocol/graph.go).
- Execute `read_updates` follows registered dependencies and corrections.
  Beyond 1000 events, `rebased: true` returns the current dependency closure.
  Advance the bound cursor only after saving a complete response with its
  transcript. Missing data or limits leave it pending; Job permissions do not change.
- HTTP errors carry `detail` and authoritative `code`; bridge errors carry
  `failure: {code, status, detail}`. Use codes such as
  `state_changed`, `dependency_invalidated`, `recovery_exhausted` and fallback
  `request_failed`, with HTTP status checks. Never infer errors from display text.

## Observations and curation

Facts and HTTP replay share optional `context` labels: `identity`, `session`,
`target_version`, `configuration` (nonblank strings, at most 256 characters each).
These are caller assertions, never credentials or verified identity. Omitted
conditions remain unknown; derivations do not inherit them. Fact context is
immutable, persisted, versioned and searchable alongside `scope` and `observed_at`.

Facts may declare immutable `derived_from`: at most 32 unique, nonempty existing
effective observation Fact IDs, each at most 256 bytes. `origin`, forward references
and `null` are rejected. Omit it for independent observations. Derivations affect
support validity, traversal and completion; corrections do not rewrite frozen inputs.

Step-add may bind `assessment: {claim, scope}`. Candidates from that Step must use
that identity; express opposing judgments with `status`, not a negated claim.
Steps without an assessment allow free-form Candidates.

An unreviewed pending curation request requires `request_review` with `disposition`,
`checked_sources` containing every requested Fact exactly once, and nonempty `reason`.
The server binds its revision. `resolved` or justified `no_change` can acknowledge
without invented findings; all pending groups must be covered to clear the request.
`needs_review` retains the request and completion blocker, including across unrelated
commits. Decide can reopen the question while retaining its original source IDs.
Dispute review revisions fence old evidence and bound new attempts. See
[request validation](../internal/board/curation_request.go) and [disputes](../internal/board/disputes.go).

## Assets and related context

`asset_ids` matches exact normalized identities. `asset_neighborhood: true` requires
that filter and includes known syntax-derived ancestors/descendants, never siblings
or DNS inference. It creates no assets. Read-only `ancestor_ids` exposes containment.
Anchors with `discovery_step_id` record discovery through a Step's target; they do
not prove observed scope, support or permission. Explicit result assets take priority.

Facts may publish `asset_relations: [{kind, source, target}]`: `resolves_to` links
DNS hosts to IP hosts; `redirects_to` links distinct endpoints. Anchoring is atomic
within the Fact's 32-asset limit; corrected relations remain historical.

`read_graph` / `read_snapshot` with `section: related` accepts Step, Fact, asset,
query or `assessment: {claim, scope}` seeds. It returns bounded records, retrieval
paths and omissions under one state version. Refine seeds or read returned IDs;
offset/byte paging and `asset_neighborhood` do not apply. Discovery paths and prior
attempts are context, not proof, completion or a stale decision's required reread.
A failed attempt is not a negative observation. See [selectors](../internal/protocol/related.go).

`read_worker_trace` lets Execute, Decide and Curate discover/read registered Explore tool
results, including attempts without a published Fact. Reads require a live role
lease and the same project, generation and workspace. Curate sees only executions
with a terminal event at or before its input revision; journal bytes are checked
against their own committed prefix, not frozen with the graph snapshot. Trace
reads never refresh decision versions or grant Fact authority. Cross-run command/path
labels, prompts and nested-agent journals are excluded; tool results are redacted.

## Local DAG and evidence

Every `run_graph` node declares `resources`; `[]` asserts independent effects.
Equal keys conflict; path-shaped keys and `path:NAME` also check normalized
parent/child overlap. Conflicting nodes require explicit ordering, and shared
workspace outputs must fit the Step's `write_paths`. Declarations coordinate
effects; they do not sandbox shell access. Ordinary artifacts stay node-private.

`append:true` submits additions; identical retries are accepted, changed definitions
rejected. Bounded responses expose omissions and `checkpoint_path` for the full
receipt. Retained outputs are verified. `verified_at` means byte verification;
`execution_started_at` / `execution_finished_at` preserve the original execution
window, including reuse. Neither verification nor reuse establishes target freshness.
Interrupted graphs permit reuse only of verified successful dependency closures
independent of unresolved nodes and resources; imported nodes prevent recursive reuse.
See [DAG implementation](../internal/worker/dag/) and [recovery](recovery.md).

## Metrics and serialization

`Result.metrics` reports observed work for all roles. Optional `model_timing`
separates queue and provider time; parallel durations are sums, not wall time.
`usage_scope: run_and_children` includes original child sessions once; `child_usage`
is already included. Missing scope means parent-only; missing observations remain
unknown or partial. Same-run cumulative metrics replace earlier values, never add
on redelivery. Final results supersede `usage_snapshot`; metrics are not a billing
ledger or proof of committed actions. See [metrics types](../internal/protocol/metrics.go).

Preserve JSON field order, tags, omissions and null/empty distinctions for identity
hashes. Do not normalize stored Job/Result bytes during upgrades. Representation
changes require versioned migration and identity tests.
