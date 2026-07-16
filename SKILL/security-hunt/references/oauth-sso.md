# OAuth/SSO · Reference

Load after selecting the `oauth-sso-lifecycle` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### POM-01-001 WP1: JWT leak via Open Redirect in programmatic access

- Source: `cure53/Pomerium-Cure53-042021`
- Reported focus: POM-01-001 WP1: JWT leak via Open Redirect in programmatic access
- Transferable test ideas:
  - The authentication proxy accepts an arbitrary return URL and places a bearer JWT in the redirect URL.
  - Downstream integrations may amplify impact by validating only issuer and not audience.
- Defensive anchor:
  - Use exact preregistered return-URL allowlists.
  - Deliver tokens only over protected backend channels.
  - Validate `iss`, `aud`, `nonce`, purpose, and one-time state.
  - Validate every `/.pomerium/` parameter consistently and add regressions.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.

### FXA-01-007 Reusable Authorization Code on OAuth Server

- Source: `cure53/pentest-report fxa`
- Reported focus: FXA-01-007 Reusable Authorization Code on OAuth Server
- Transferable test ideas:
  - `state`, `nonce`, PKCE, callback port, provider identity, or account resolution is not strongly bound to the
    original session, so a valid result is attributed to the wrong subject.
- Defensive anchor:
  - Validate and consume `state`/`nonce` exactly once.
  - Enable PKCE.
  - Require exact redirect-URI matching.
  - Use provider+subject as a joint unique identifier.
  - Rotate the session after login and prevent unsafe automatic account merging.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.

### 1. Connecting attacker’s weibo account to victim’s peatio account

- Source: `sakurity/Sakurity - Peatio`
- Reported focus: 1. Connecting attacker’s weibo account to victim’s peatio account
- Transferable test ideas:
  - The flow validates existence but not ownership, purpose, session, or current state.
- Defensive anchor:
  - Require reauthentication, strict token binding, object-level authorization, and old-factor confirmation for rebinding.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.

### 6.4 M01 Use of an Embedded User-Agent for User Authentication

- Source: `hackmanit/Penetration-Test-Report-KeeWeb-by-Hackmanit`
- Reported focus: 6.4 M01 Use of an Embedded User-Agent for User Authentication
- Transferable test ideas:
  - An embedded user agent shares control with the host, or weak postMessage source/target validation lets a valid authorization result cross into the wrong browser context.
- Defensive anchor:
  - Use the system browser and claimed HTTPS/app-link callbacks.
  - Require PKCE, state, and nonce.
  - Prohibit embedded login.
  - Strictly validate postMessage origin, source, and message structure.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
