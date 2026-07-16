# State & Races

## Goal

Reconstruct the real state machine and verify that the server enforces preconditions, unique transition paths, counts, versions, ordering, and atomicity.

## Primary Boundary

Use this module as primary when the failure concerns legal transitions, ordering, replay, counts, versions, atomicity,
or enforcement of a mandatory policy. For tokens, use `identity/tokens` when the issue is subject, purpose, audience,
session, or lifecycle binding; use `race` when the issue is concurrent use, one-time consumption, or transaction
atomicity.

## Loading Order

1. Read `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md` first.
2. Load the Profiles needed for the concrete hypothesis; keep plausible adjacent and combination paths queued, and add
   them whenever evidence, gaps, or downstream consumers require it.
3. Establish a baseline before reading matching References for additional variants. Progressive loading limits context use, not testing breadth or depth.

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| Account lifecycle; orders/payments/refunds; invitations/approvals/bindings | `workflow` | Business State Machines |
| Check-then-use; balance/quota deduction; one-time tokens | `race` | Races & TOCTOU |
| Forced VPN/Tor egress; TLS/certificate validation; zero-trust proxies | `policy-bypass` | Mandatory Policy Bypass |

Profile paths are `${CLAUDE_SKILL_DIR}/profiles/<name>.md`; Reference paths are `${CLAUDE_SKILL_DIR}/references/<name>.md`.

## Workflow

1. List state nodes, legal edges, terminal states, rollback paths, and asynchronous callbacks.
2. For each edge, test skipping, reordering, replay, legacy endpoints, failure retries, and concurrency.
3. Where checks and use are separated, record object versions, locks, idempotency keys, and transaction boundaries.
4. Read back final state, balance, inventory, permissions, or policy-enforcement results to rule out response-only artifacts.

## Do Not Stop Here

- Following only the UI sequence instead of calling server-side actions directly.
- Running a race once without recording concurrency, success rate, and timing window.
- Calling a business anomaly a vulnerability without identifying the broken security or economic boundary.

## Output

Record each round with the complete status, blackboard, evidence, impact-validation, severity-gate, blind-spot, and
closure rules in `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md`; do not replace them with a reduced local schema.
