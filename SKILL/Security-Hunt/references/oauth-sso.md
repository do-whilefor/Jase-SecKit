# OAuth/SSO · Reference

Load after selecting the `oauth-sso-lifecycle` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### POM-01-001 WP1: JWT leak via Open Redirect in programmatic access

- Source URL: https://cure53.de/pentest-report_pomerium.pdf
- Source locator: report pp. 7-8, POM-01-001.
- Reported boundary:
  - Cure53 reports that programmatic access accepted an arbitrary
    `pomerium_redirect_uri`. An already-authenticated user was redirected to
    that URI with a valid JWT attached.
- Transferable test ideas:
  - Model redirect selection and capability delivery as one decision. A secure
    login step does not help if its output capability crosses to an
    attacker-selected origin.
  - Compare interactive and no-prompt states, programmatic and browser entry
    points, and every parameter that can select the final destination.
- Impact closure:
  - Do not stop at an open redirect. Prove token validity, audience, effective
    privileges, affected applications, victim interaction, and replay lifetime.
- Defensive anchor:
  - Use exact preregistered return-URL allowlists.
  - Never attach bearer material to a user-controlled redirect target.
  - Validate `iss`, `aud`, `nonce`, purpose, and one-time state.
  - Validate every `/.pomerium/` parameter consistently and add regressions.

### FXA-01-007 Reusable Authorization Code on OAuth Server

- Source: `cure53/pentest-report fxa`
- Source topic: FXA-01-007 Reusable Authorization Code on OAuth Server
- Transferable test ideas:
  - `state`, `nonce`, PKCE, callback port, provider identity, or account resolution is not strongly bound to the
    original session, so a valid result is attributed to the wrong subject.
- Defensive anchor:
  - Validate and consume `state`/`nonce` exactly once.
  - Enable PKCE.
  - Require exact redirect-URI matching.
  - Use provider+subject as a joint unique identifier.
  - Rotate the session after login and prevent unsafe automatic account merging.

### 1. Connecting attacker’s weibo account to victim’s peatio account

- Source: `sakurity/Sakurity - Peatio`
- Source topic: 1. Connecting attacker’s weibo account to victim’s peatio account
- Transferable test ideas:
  - The flow validates existence but not ownership, purpose, session, or current state.
- Defensive anchor:
  - Require reauthentication, strict token binding, object-level authorization, and old-factor confirmation for rebinding.

### 6.4 M01 Use of an Embedded User-Agent for User Authentication

- Source: `hackmanit/Penetration-Test-Report-KeeWeb-by-Hackmanit`
- Source topic: 6.4 M01 Use of an Embedded User-Agent for User Authentication
- Transferable test ideas:
  - An embedded user agent shares control with the host, or weak postMessage source/target validation lets a valid authorization result cross into the wrong browser context.
- Defensive anchor:
  - Use the system browser and claimed HTTPS/app-link callbacks.
  - Require PKCE, state, and nonce.
  - Prohibit embedded login.
  - Strictly validate postMessage origin, source, and message structure.
