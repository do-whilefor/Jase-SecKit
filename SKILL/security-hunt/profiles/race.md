---
id: toctou-state-boundary
group: state
reference: ../references/race.md
---

# Races & TOCTOU

**Use for:** check-then-use flows, balance/quota deduction, one-time tokens, file objects, asynchronous jobs, and artifact publication.

**Misalignment to find:** Checks and use, reservation and commit, read and write, or multiple concurrent transactions are not bound to the same object version and atomic state.

## Baseline

- A security decision must be bound to the same object and version used by the final action.
- Look for concurrent replacement, duplicate submission, timing windows, lock granularity, asynchronous reordering, or stale cache state.
- Focus on locally valid checks that violate a global invariant when combined.
- Record object version, transaction boundary, lock, idempotency key, and final state.

## Validation Order

1. Establish a single-request baseline.
2. Use a synchronization gate to trigger identical or complementary operations concurrently.
3. Vary thread count, connection, identity, object, and commit order.
4. Read back balances, counts, object contents, permissions, and external side effects.

## Variant Axes

- Whether the checked object and used object are the same version
- Atomicity across reservation, deduction, commit, and rollback
- Concurrency, timing, lock granularity, isolation level, and idempotency key
- Files, permissions, balances, inventory, jobs, and temporary tokens

## Combination Paths

- `workflow`: Business State Machines
- `fs-identity`: File-Object Identity
- `tokens`: Token Lifecycle
