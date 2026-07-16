# Business State Machines · Reference

Load after selecting the `business-state-machine` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### TOR-02-012 WP3: State Corruption via Refresh Race Condition

- Source: `7asecurity/pentest-report-tor2-RC1.2`
- Reported focus: TOR-02-012 WP3: State Corruption via Refresh Race Condition
- Transferable test ideas:
  - State checks are distributed, versions/idempotency keys are missing, or one-time flags are updated non-atomically, allowing valid steps to be recombined incorrectly.
- Defensive anchor:
  - Use a server-side state machine and transactions.
  - Validate pre-state and version on every transition.
  - Consume one-time tokens atomically.
  - Add concurrency and out-of-order tests.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.

### 6.6 Front running in matchOrders()

- Source: `consensys/0x-v3-audit-2019-09`
- Reported focus: 6.6 Front running in matchOrders()
- Transferable test ideas:
  - State is updated after an external call, transactions can be reordered, proofs omit critical variables, or business invariants are not enforced on-chain.
- Defensive anchor:
  - Use checks-effects-interactions and reentrancy guards.
  - Encode critical invariants as assertions/property tests.
  - Add nonces, commit-reveal, and slippage bounds.
  - Model failures of external contracts and oracles.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.

### Issue E. Parallel Requests Bypass Exponentially Increasing Login Delay

- Source: `leastauthority/LeastAuthority-GlobaLeaks-audit-report`
- Reported focus: Issue E. Parallel Requests Bypass Exponentially Increasing Login Delay
- Transferable test ideas:
  - A failure cost intended to accumulate globally is split across parallel execution paths through read-before-update logic or per-connection state.
- Defensive anchor:
  - Use atomic server-side counters or token buckets.
  - Rate-limit by account, source, and device together.
  - Reserve quota before processing.
  - Regression-test concurrent bursts rather than only serial requests.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
