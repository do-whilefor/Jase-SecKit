# Algorithmic Complexity · Reference


Load on demand after selecting the `algorithmic-complexity` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### x41-d-sec/X41-OSTIF-Hickory-DNS-2025-Audit-Report-Public · 4.1.3 HCKRYDNS-CR-24-03: Resolver Vulnerable to KeyTrap Attack
- Value: 8/10; protocol-behavior exploitation / other.
- Chain: The attacker sends a small crafted input → parsing or validation enters a quadratic, exponential, or otherwise extremely expensive path → one request saturates CPU/memory → the service becomes unavailable.
- Bypass: Exploit worst-case complexity and request-cost asymmetry to bypass conventional DoS controls that limit only packet size or request rate.
- Defensive anchor: Set budgets for depth, element count, verification count, CPU, and memory; optimize and deduplicate early; enforce timeouts/circuit breakers; use complexity-oriented fuzzing to cover worst-case paths.


## Source Coverage

- Full reports: 4.
- HackerOne reports: 0.
- Full report IDs:
  - x41-d-sec/X41-OSTIF-Hickory-DNS-2025-Audit-Report-Public
  - x41-d-sec/X41-OSTIF-simplejson-CodeRview-2023-04-18
  - cure53/pentest-report pcre
  - x41-d-sec/X41-TUF-Audit-2022-Final-Report-PUBLIC

