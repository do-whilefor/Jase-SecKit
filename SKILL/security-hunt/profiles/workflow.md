---
id: business-state-machine
group: state
reference: ../references/workflow.md
---

# Business State Machines

**Use for:** account lifecycles, orders/payments/refunds, invitations/approvals/bindings, quotas/rate limits/rewards, on-chain state, and asynchronous jobs.

**Misalignment to find:** The server validates only local fields or one request without enforcing legal preconditions, unique transition paths, counts, ordering, concurrency, and rollback semantics.

## Baseline

- Security depends on state transitions rather than one parameter.
- Look for step skipping, reordering, replay, concurrency, alternate entry points, rollback, or duplicate counting that breaks an invariant.
- Focus on locally valid endpoint calls that create an invalid global state.
- Record state, subject, object, version, count, and irreversible side effects.

## Validation Order

1. Build a state graph and list the subject, preconditions, and uniqueness requirement for every edge.
2. For every edge, test skipping, repetition, reordering, concurrency, stale tokens, and alternate entry points.
3. When multiple endpoints can mutate the same object, compare their checks and transaction boundaries.
4. Read back final state, balance, permissions, or external side effects.

## Variant Axes

- State nodes, legal preconditions, and terminal states
- Action order, count, uniqueness, rollback, and compensation
- Object, subject, amount, quota, inventory, approver, and tenant
- Skipping, replay, legacy endpoints, concurrency, failure retry, asynchronous callback

## Combination Paths

- `race`: Races & TOCTOU
- `tokens`: Token Lifecycle
- `policy-bypass`: Mandatory Policy Bypass
