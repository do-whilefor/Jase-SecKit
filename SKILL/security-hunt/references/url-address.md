# URLs & Addresses · Reference

Load after selecting the `ssrf-url-address` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### TEL-Q121-7. Server-Side Request Forgery via OpenID Connect

- Source: `doyensec/Doyensec Gravitational Teleport CloudTesting Q12021`
- Reported focus: TEL-Q121-7. Server-Side Request Forgery via OpenID Connect
- Transferable test ideas:
  - URL parsing, redirects, DNS rebinding, or unauthenticated internal services let external input acquire the server’s network identity.
- Defensive anchor:
  - Use destination allowlists.
  - Validate IP addresses after every resolution and redirect.
  - Block private, loopback, link-local, and metadata ranges.
  - Restrict schemes and ports.
  - Enforce outbound network isolation.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
