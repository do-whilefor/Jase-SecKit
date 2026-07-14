# Protocol Field Injection · Reference

Load after selecting the `protocol-field-injection` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### cure53/pentest-report Curl · CRL-01-001 Malicious server can inject cookies for other servers
- Knowledge value: 10/10; protocol-behavior exploitation / cross-component attack chain.
- Chain: A malicious endpoint or filename creates a special protocol field → a client or intermediary accepts it as data and persists/forwards it → a later parser interprets it as control syntax → cross-domain cookies, commands, files, or a malicious content type are injected.
- Bypass: Exploit differences in delimiter, line-break, escaping, or persisted-format semantics so data becomes a control instruction in a later stage.
- Defensive anchor: Use structured protocol libraries; strictly validate and encode fields; reject control characters and ambiguous delimiters; add round-trip consistency tests for persistence and reparsing paths.
