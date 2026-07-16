# Mandatory Policy Bypass · Reference

Load after selecting the `mandatory-policy-alternate-path` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### MM-01-002 Extension: Phishing Detector can be bypassed

- Source: `cure53/pentest-report metamask`
- Reported focus: MM-01-002 Extension: Phishing Detector can be bypassed
- Transferable test ideas:
  - Platform helpers, protocol downgrade, redirects, races, or bypass clients make a secure default path differ from universal policy enforcement.
- Defensive anchor:
  - Centralize non-bypassable egress and certificate policy.
  - Disable plaintext and alternate paths.
  - Test every URL scheme, redirect, and subprocess end to end.
  - Generate audit records at a trusted server-side boundary.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.

### SMS-02-007 Possible Remote Code Execution via MitM in WebView

- Source: `cure53/pentest-report smartsheriff-2`
- Reported focus: SMS-02-007 Possible Remote Code Execution via MitM in WebView
- Transferable test ideas:
  - Missing endpoint authentication at the transport layer lets a downstream executor inherit a false assumption that the content came from a trusted source.
- Defensive anchor:
  - Require HTTPS/TLS with correct certificate validation.
  - Additionally verify executable content with signatures or hashes.
  - Separate download and execution privileges.
  - Never fall back to plaintext after failure.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
