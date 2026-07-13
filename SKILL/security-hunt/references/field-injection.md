# Protocol Field Injection · Reference


Load on demand after selecting the `protocol-field-injection` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### cure53/pentest-report Curl · CRL-01-001 Malicious server can inject cookies for other servers
- Value: 10/10; protocol-behavior exploitation / cross-component attack chain.
- Chain: A malicious endpoint or filename creates a special protocol field → a client or intermediary accepts it as data and persists/forwards it → a later parser interprets it as control syntax → cross-domain cookies, commands, files, or a malicious content type are injected.
- Bypass: Exploit differences in delimiter, line-break, escaping, or persisted-format semantics so data becomes a control instruction in a later stage.
- Defensive anchor: Use structured protocol libraries; strictly validate and encode fields; reject control characters and ambiguous delimiters; add round-trip consistency tests for persistence and reparsing paths.


## Source Coverage

- Full reports: 4.
- HackerOne reports: 0.
- Full report IDs:
  - cure53/pentest-report casebox-1
  - cure53/pentest-report Curl
  - cure53/pentest-report libssh
  - cure53/pentest-report SC4

