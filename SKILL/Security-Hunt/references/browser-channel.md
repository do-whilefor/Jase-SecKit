# Cross-Origin Channels · Reference

Load after selecting the `cross-origin-message-channel` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### FVP-02-014 General: Cross-site WebSocket hijacking

- Source: `cure53/pentest-report-mozilla-vpn-apps-clients-03-2021`
- Source topic: FVP-02-014 General: Cross-site WebSocket hijacking
- Transferable test ideas:
  - WebSockets do not automatically inherit traditional CSRF protections.
  - Without Origin or handshake-token validation, the victim’s authenticated state is reused.
- Defensive anchor:
  - Strictly allowlist Origin.
  - Use one-time, session-bound handshake tokens.
  - Do not authenticate solely with cookies.
  - Authorize every message at object level and restrict local control interfaces.
