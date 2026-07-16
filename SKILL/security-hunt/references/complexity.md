# Algorithmic Complexity · Reference

Load after selecting the `algorithmic-complexity` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### 4.1.3 HCKRYDNS-CR-24-03: Resolver Vulnerable to KeyTrap Attack

- Source: `x41-d-sec/X41-OSTIF-Hickory-DNS-2025-Audit-Report-Public`
- Reported focus: 4.1.3 HCKRYDNS-CR-24-03: Resolver Vulnerable to KeyTrap Attack
- Transferable test ideas:
  - Exploit worst-case complexity and request-cost asymmetry to bypass conventional DoS controls that limit only packet size or request rate.
- Defensive anchor:
  - Set budgets for depth, element count, verification count, CPU, and memory.
  - Optimize and deduplicate early.
  - Enforce timeouts/circuit breakers.
  - Use complexity-oriented fuzzing to cover worst-case paths.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
