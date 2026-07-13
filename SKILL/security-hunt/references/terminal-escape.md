# Terminal Escapes · Reference


Load on demand after selecting the `terminal-control-sequence` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### doyensec/Doyensec Gravitational Teleport FeaturesTesting Q32021 · TEL-Q321-5 Injectable Terminal Escape Sequences And Newlines In Request Reason
- Value: 10/10; protocol-behavior exploitation / cross-component attack chain.
- Chain: A low-privilege user injects ANSI/VT control characters into a request reason → the backend stores them verbatim and displays them in an administrator CLI → the terminal executes the control sequences and forges approval tables or identifiers → the operator approves the wrong request.
- Bypass: Different components interpret the same bytes differently: the Web form treats them as text while the terminal treats them as display-control instructions, crossing a content boundary and manipulating trusted UI.
- Defensive anchor: Reject control characters and use a printable-character allowlist; escape safely before terminal output; limit log/approval field length; base high-risk approval on unforgeable structured IDs and require secondary confirmation.


## Source Coverage

- Full reports: 1.
- HackerOne reports: 0.
- Full report IDs:
  - doyensec/Doyensec Gravitational Teleport FeaturesTesting Q32021

