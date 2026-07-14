# Algorithmic Complexity · Reference

Load after selecting the `algorithmic-complexity` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### x41-d-sec/X41-OSTIF-Hickory-DNS-2025-Audit-Report-Public · 4.1.3 HCKRYDNS-CR-24-03: Resolver Vulnerable to KeyTrap Attack
- Knowledge value: 8/10; protocol-behavior exploitation / other.
- Chain: The attacker sends a small crafted input → parsing or validation enters a quadratic, exponential, or otherwise extremely expensive path → one request saturates CPU/memory → the service becomes unavailable.
- Bypass: Exploit worst-case complexity and request-cost asymmetry to bypass conventional DoS controls that limit only packet size or request rate.
- Defensive anchor: Set budgets for depth, element count, verification count, CPU, and memory; optimize and deduplicate early; enforce timeouts/circuit breakers; use complexity-oriented fuzzing to cover worst-case paths.
