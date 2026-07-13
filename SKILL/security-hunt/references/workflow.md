# Business State Machines · Reference


Load on demand after selecting the `business-state-machine` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### 7asecurity/pentest-report-tor2-RC1.2 · TOR-02-012 WP3: State Corruption via Refresh Race Condition
- Value: 9/10; state confusion / business logic.
- Chain: The attacker prepares a valid object/session → skips, replays, or concurrently triggers workflow steps → the server accepts an impossible state combination → limits are bypassed, actions are duplicated, or data consistency breaks.
- Bypass: State checks are distributed, versions/idempotency keys are missing, or one-time flags are updated non-atomically, allowing valid steps to be recombined incorrectly.
- Defensive anchor: Use a server-side state machine and transactions; validate pre-state and version on every transition; consume one-time tokens atomically; add concurrency and out-of-order tests.

### consensys/0x-v3-audit-2019-09 · 6.6 Front running in matchOrders() Medium Won't Fix
- Value: 9/10; business logic / state confusion.
- Chain: The attacker prepares a specific on-chain state or external contract → uses reentrancy, front-running, replay, missing constraints, or pricing errors to change execution order or input → duplicate withdrawal, incorrect minting, bypassed isolation period, or improper asset gain.
- Bypass: State is updated after an external call, transactions can be reordered, proofs omit critical variables, or business invariants are not enforced on-chain.
- Defensive anchor: Use checks-effects-interactions and reentrancy guards; encode critical invariants as assertions/property tests; add nonces, commit-reveal, and slippage bounds; model failures of external contracts and oracles.

### leastauthority/LeastAuthority-GlobaLeaks-audit-report · Issue E. Parallel Requests Bypass Exponentially Increasing Login Delay
- Value: 9/10; race condition / business logic / state confusion.
- Chain: The attacker sends many login attempts concurrently → each request reads the same or not-yet-updated failure state → the increasing delay does not serialize → online guessing is much faster than designed.
- Bypass: A failure cost intended to accumulate globally is split across parallel execution paths through read-before-update logic or per-connection state.
- Defensive anchor: Use atomic server-side counters or token buckets; rate-limit by account, source, and device together; reserve quota before processing; regression-test concurrent bursts rather than only serial requests.


## HackerOne Case Index


### 138869 · Business state-machine/precondition bypass
- Value: 8/10; business logic / state confusion / authorization bypass.
- Chain: `https://newsroom.uber.com/xmlrpc.php` → business state-machine/precondition bypass → security controls and the final execution point disagree about subject, object, state, or input semantics → arbitrary code or command execution.
- Bypass: Skip prerequisite steps, call later endpoints directly, replay stale requests, or modify state fields so a sensitive action completes without payment, verification, approval, or another required condition.
- Defensive anchor: Define an explicit server-side transition table; atomically validate current state, subject, object, and preconditions for every action; use non-replayable idempotency tokens; enforce final-state invariants with database constraints.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 6.
- HackerOne reports: 12.
- Full report IDs:
  - 7asecurity/pentest-report-tor2-RC1.2
  - consensys/0x-v3-audit-2019-09
  - leastauthority/LeastAuthority-GlobaLeaks-audit-report
  - x41-d-sec/X41-Audit-Thetanuts-2021-11-Public-Report
  - consensys/dandelion-audit-2019-12
  - consensys/orchid-audit-2019-10
- HackerOne report IDs:
  - 1034346, 351519, 893305, 894949, 895722, 138869, 889886, 894170, 761726, 893395, 894863, 689314

