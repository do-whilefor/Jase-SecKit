# Terminal Escapes · Reference

Load after selecting the `terminal-control-sequence` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### TEL-Q321-5 Injectable Terminal Escape Sequences And Newlines In Request Reason

- Source: `doyensec/Doyensec Gravitational Teleport FeaturesTesting Q32021`
- Reported focus: TEL-Q321-5 Injectable Terminal Escape Sequences And Newlines In Request Reason
- Transferable test ideas:
  - Different components interpret the same bytes differently: the Web form treats them as text while the terminal
    treats them as display-control instructions, crossing a content boundary and manipulating trusted UI.
- Defensive anchor:
  - Reject control characters and use a printable-character allowlist.
  - Escape safely before terminal output.
  - Limit log/approval field length.
  - Base high-risk approval on unforgeable structured IDs and require secondary confirmation.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
