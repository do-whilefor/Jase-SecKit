# Offline Verifiers · Reference

Load after selecting the `offline-verifier-exposure` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### 2. IPMI v2.0 Password Hash Disclosure

- Source: `singlepointofcontact/SPoC Penetration-Test`
- Reported focus: 2. IPMI v2.0 Password Hash Disclosure
- Transferable test ideas:
  - The protocol reveals a password proof that can be checked offline before authentication, bypassing online rate limits and lockout policy.
- Defensive anchor:
  - Upgrade or disable the affected protocol.
  - Use strong unique passwords and network isolation.
  - Prefer PAKE or certificate authentication resistant to offline guessing.
  - Monitor anomalous handshakes.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
