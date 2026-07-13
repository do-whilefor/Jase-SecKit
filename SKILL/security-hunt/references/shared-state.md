# Shared Protocol State · Reference


Load on demand after selecting the `protocol-cache-state` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### cure53/pentest-report CoreDNS · DNS-01-003 Cache: DNS Cache poisoning via malicious Response
- Value: 8/10; protocol-behavior exploitation / cross-component attack chain.
- Chain: The attacker induces or forges a crafted DNS response → the resolver incorrectly accepts and caches malicious records → later clients hit the poisoned cache → they are redirected to attacker-controlled services.
- Bypass: Weak query/response association, name rewriting, additional records, or incomplete cache-key semantics lets records unrelated to the original query inherit trusted cache state.
- Defensive anchor: Strictly match query ID, source endpoint, question section, and name semantics; minimize caching of additional records; randomize source ports and IDs and use DNSSEC; test cache consistency across rewrite/forwarding plugins.


## Source Coverage

- Full reports: 1.
- HackerOne reports: 0.
- Full report IDs:
  - cure53/pentest-report CoreDNS

