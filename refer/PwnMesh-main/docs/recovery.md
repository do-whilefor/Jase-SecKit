# PwnMesh recovery

Recovery preserves execution identity and authority. Retrying does not authorize
duplicate side effects or restore a revoked lease.

## Recovery behavior

| Operation | Behavior |
| --- | --- |
| Infrastructure interruption | `protocol.ErrInterrupted` permits bounded recovery of the same run |
| Ordinary cancellation | Stops the attempt without granting same-run recovery |
| Pause / Continue | Grants retry only to eligible attempts affected by the pause |
| Explicit execution retry | Checks the grant, generation, eligibility and authority |
| Result delivery retry | Sends the retained result without rerunning models or tools |
| Project restart | Archives the round, increments generation and revokes old runs; preserves human inputs, counters and workspace files |
| Project termination | Stops unfinished work and retains history; another round requires explicit restart |

Same-run recovery allows two resumptions after the initial attempt. Original
deadlines and consumed repair, continuation and recovery allowances remain in force.
Compaction and recovery retain an artifact/command index, but its entries describe
historical receipts, not current file checks or fresh test results.

## Evidence and authority

- Save identity and proposed transitions before their effects. Session replacement
  is atomic; a later directory-sync failure still leaves durability uncertain.
- Pi's JSONL file is synced before its byte/hash/leaf checkpoint is committed.
  Recovery verifies that prefix and branches from its saved leaf; later entries
  cannot authorize replay. Keep the file with `session.json` in backups; neither
  Go history nor the original task prompt has a separate persisted copy.
- Failed model and summary attempts remain in Pi's original history. Native
  context edits exclude them from later requests and prevent partial tool replay.
- Verify journal offsets and checksums. Complete crash-tail records stay append-only
  and excluded from evidence across checkpoints; reported model usage remains
  observable. Archive and sync an incomplete tail before truncation. Acceptance
  reads only the identity-bound transcript or verified committed prefix.
- Execute receipts bind the run/input to session and artifact hashes, checked again
  on read. A changed repair target cannot reuse success. Deterministic acceptance
  failure is terminal; uncertain callbacks retain the existing recovery path.
- Decide and Curate check authoritative server commit receipts before planning
  again. Discarding a draft does not erase a commit or restore consumed budget.
- Require current acceptance receipts and graph/node definition digests; never
  reconstruct missing bindings. See [supported formats](formats.md).
- A child Agent's terminal receipt may reconcile a running graph node after
  identity, committed final message and output/artifact hashes are verified,
  without model or tool calls. Commands, unfinished Agents and missing terminal
  receipts cannot use this path. Cancellation stops recovery callbacks.
- Receipt imports re-verify their sources without replay. Graph checkpoint reads
  reject symlinks, special files, trailing JSON and detected changes during reading.

## Restore and cleanup

1. Stop Server and Dispatcher. Retain a consistent SQLite backup and matching
   workspace, journals, evidence and receipts. If backing up a live database, use
   SQLite backup tooling; copying its main file during WAL writes is unsafe.
2. Check [format compatibility](formats.md) before starting. Preserve installation
   identity, stored JSON and workspace paths; do not edit checkpoints to bypass checks.
3. Let Dispatcher reconcile generations and registered executions before new work.
   Investigate validation errors using original artifacts. Do not delete receipts
   or lease tombstones to force recovery.

SQLite retains inputs, snapshots, execution inputs and archived rounds until project
deletion; ended executions may still reference snapshots. Scheduling projections
are rebuildable. Workspace files survive restart and require separate backups and
cleanup under [container ownership rules](../container/README.md). Request staging
is temporary; deleting database rows does not necessarily shrink the SQLite file.
