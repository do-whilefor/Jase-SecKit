# Terminal Escapes · Reference

Load after selecting the `terminal-control-sequence` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### TEL-Q321-5 Injectable Terminal Escape Sequences And Newlines In Request Reason

- Source URL: https://doyensec.com/resources/teleport-features-audit-q3-2021.pdf
- Source locator: pp. 16-17, TEL-Q321-5.
- Reported boundary:
  - Doyensec reports that user-controlled access-request reasons accepted
    newlines and terminal escape sequences that were later printed by a
    terminal client, making stored text active in an operator-facing renderer.
- Transferable test ideas:
  - Preserve five distinct observations: submitted bytes, stored bytes,
    emitted bytes, terminal-emulator state, and the final visible screen.
  - Test cursor movement, erasure, hyperlinks, title changes, bracketed-paste
    interactions, newlines, truncation, and alternate terminal clients
    separately rather than treating all ANSI input as one payload class.
- Impact closure:
  - Distinguish raw control-byte acceptance, visual deception, changed operator
    approval, and active terminal-side effects. Prove only the highest stage
    that a clean reproduction and observable action support.
- Defensive anchor:
  - Reject control characters and use a printable-character allowlist.
  - Escape safely before terminal output.
  - Limit log/approval field length.
  - Base high-risk approval on unforgeable structured IDs and require secondary confirmation.
