# Privileged IPC · Reference

Load after selecting the `privileged-ipc` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### AVP-01-011 WP2: Linux/Mac/Win PrivEsc via IPC Design Flaw

- Source: `7asecurity/pentest-report-amneziavpn`
- Source topic: AVP-01-011 WP2: Linux/Mac/Win PrivEsc via IPC Design Flaw
- Transferable test ideas:
  - The IPC endpoint is reachable but caller identity is not bound, or the server treats client-supplied paths and commands as trusted data.
- Defensive anchor:
  - Validate peer credentials at the OS level.
  - Minimize IPC methods.
  - Reauthorize and canonicalize arguments server-side.
  - Never let clients select arbitrary paths or commands.
  - Execute delegated work in a low-privilege sandbox.
