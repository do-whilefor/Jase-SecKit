# Prototype Pollution · Reference


Load on demand after selecting the `prototype-pollution` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### x41-d-sec/X41-Backstage-Audit-2024-Final-Report-Public · Server-Side Prototype Pollution via Filters Request Parameter
- Value: 10/10; framework-behavior exploitation / cross-component attack chain.
- Chain: The attacker submits nested parameters with special property names → merge/filter code pollutes the global prototype → later query, template, or configuration code inherits malicious values → DoS, injection, or code execution.
- Bypass: JavaScript prototype inheritance performs implicit lookup, allowing security options or object fields that were never set locally to be modified globally.
- Defensive anchor: Use null-prototype objects or Map; recursively reject dangerous keys; update affected dependencies; use own-property checks at security-sensitive reads and freeze critical configuration objects.


## Source Coverage

- Full reports: 1.
- HackerOne reports: 0.
- Full report IDs:
  - x41-d-sec/X41-Backstage-Audit-2024-Final-Report-Public

