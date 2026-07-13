# Races & TOCTOU · Reference


Load on demand after selecting the `toctou-state-boundary` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## HackerOne Case Index


### 187134 · TOCTOU/concurrent-state boundary failure
- Value: 9/10; race condition / business logic / framework-behavior exploitation.
- Chain: `http://127.0.0.1:8000/memspy` → TOCTOU/concurrent-state boundary failure, combined with memory-safety or low-level runtime behavior → the corresponding trust boundary is crossed → access to internal services or cloud metadata.
- Bypass: Concurrently trigger a non-atomic “check condition → perform action → update state” window, or mutate the same business object through different endpoints; combine with low-level runtime behavior to extend the chain.
- Defensive anchor: Place condition checks and state updates in one atomic transaction; use unique constraints, conditional updates, row locks, or idempotency keys; validate the invariant from the final ledger/balance/object count rather than HTTP 200 counts; add low-level cross-component regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 759247 · TOCTOU/concurrent-state boundary failure
- Value: 8/10; race condition / business logic / state confusion.
- Chain: `POST /fi/redeem` → TOCTOU/concurrent-state boundary failure → security controls and the final execution point disagree about subject, object, state, or input semantics → billing, redemption, or quota constraints are bypassed.
- Bypass: Concurrently trigger the non-atomic check/action/update window or mutate the same object through multiple endpoints.
- Defensive anchor: Make checks and updates atomic; use unique constraints, conditional updates, row locks, or idempotency keys; verify the final ledger, balance, or object count instead of response counts.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 0.
- HackerOne reports: 8.
- HackerOne report IDs:
  - 1350444, 1826141, 73248, 1087188, 974892, 768110, 187134, 759247

