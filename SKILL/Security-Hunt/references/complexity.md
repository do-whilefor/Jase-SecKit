# Algorithmic Complexity · Reference

Load after selecting the `algorithmic-complexity` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### 4.1.3 HCKRYDNS-CR-24-03: Resolver Vulnerable to KeyTrap Attack

- Source URL: https://pentestreports.com/files/reports/x41-d-sec/X41-OSTIF-Hickory-DNS-2025-Audit-Report-Public.pdf
- Source locator: p. 19, HCKRYDNS-CR-24-03.
- Reported boundary:
  - X41 reports that attacker-chosen colliding DNSKEY and RRSIG candidates could
    drive many key/signature verification pairs without a verification-attempt
    budget, consuming resolver CPU.
- Transferable test ideas:
  - Measure input bytes, candidate keys, signatures, verification attempts,
    cryptographic time, total CPU, latency, and memory on the same graph.
  - Build a scaling curve for one message before adding concurrency, retries,
    cache misses, delegations, or upstream fan-out.
- Impact closure:
  - Prove attacker cost versus server work, reproducible saturation or latency,
    affected request classes, concurrency needed, and recovery behavior. A slow
    malformed packet or theoretical asymptote is not enough.
- Defensive anchor:
  - Set per-message and per-client budgets for candidate pairs, verification
    attempts, depth, CPU, wall time, and memory.
  - Deduplicate candidates before expensive verification.
  - Enforce timeouts/circuit breakers.
  - Use complexity-oriented fuzzing to cover worst-case paths.
