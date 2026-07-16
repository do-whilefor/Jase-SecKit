# Protocol Field Injection · Reference

Load after selecting the `protocol-field-injection` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### CRL-01-001 Malicious server can inject cookies for other servers

- Source: `cure53/pentest-report Curl`
- Reported focus: CRL-01-001 Malicious server can inject cookies for other servers
- Transferable test ideas:
  - Exploit differences in delimiter, line-break, escaping, or persisted-format semantics so data becomes a control instruction in a later stage.
- Defensive anchor:
  - Use structured protocol libraries.
  - Strictly validate and encode fields.
  - Reject control characters and ambiguous delimiters.
  - Add round-trip consistency tests for persistence and reparsing paths.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
