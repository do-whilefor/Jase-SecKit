# Shared Protocol State · Reference

Load after selecting the `protocol-cache-state` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### cure53/pentest-report CoreDNS · DNS-01-003 Cache: DNS Cache poisoning via malicious Response
- Knowledge value: 8/10; protocol-behavior exploitation / cross-component attack chain.
- Chain: The attacker induces or forges a crafted DNS response → the resolver incorrectly accepts and caches malicious records → later clients hit the poisoned cache → they are redirected to attacker-controlled services.
- Bypass: Weak query/response association, name rewriting, additional records, or incomplete cache-key semantics lets records unrelated to the original query inherit trusted cache state.
- Defensive anchor: Strictly match query ID, source endpoint, question section, and name semantics; minimize caching of additional records; randomize source ports and IDs and use DNSSEC; test cache consistency across rewrite/forwarding plugins.
