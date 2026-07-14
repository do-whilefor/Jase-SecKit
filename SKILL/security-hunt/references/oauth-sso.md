# OAuth/SSO · Reference

Load after selecting the `oauth-sso-lifecycle` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### cure53/Pomerium-Cure53-042021 · POM-01-001 WP1: JWT leak via Open Redirect in programmatic access
- Knowledge value: 10/10; authentication bypass / protocol-behavior exploitation / cross-component attack chain.
- Chain: The attacker creates a programmatic-login URL that returns to a malicious site → an authenticated victim opens it → Pomerium completes authentication and appends a JWT to the malicious return URL → the attacker obtains the JWT, queries the victim’s identity, or impersonates the victim in integrations with weak audience checks.
- Bypass: The authentication proxy accepts an arbitrary return URL and places a bearer JWT in the redirect URL; downstream integrations may amplify impact by validating only issuer and not audience.
- Defensive anchor: Use exact preregistered return-URL allowlists; deliver tokens only over protected backend channels; validate `iss`, `aud`, `nonce`, purpose, and one-time state; validate every `/.pomerium/` parameter consistently and add regressions.

### cure53/pentest-report fxa · FXA-01-007 Reusable Authorization Code on OAuth Server
- Knowledge value: 9/10; authentication bypass / state confusion / cross-component attack chain.
- Chain: The attacker prepares or intercepts authentication context → induces the victim to complete a callback or reuse an authorization result → the server binds an attacker-controlled identity or code to the victim session → account takeover or token disclosure.
- Bypass: `state`, `nonce`, PKCE, callback port, provider identity, or account resolution is not strongly bound to the original session, so a valid result is attributed to the wrong subject.
- Defensive anchor: Validate and consume `state`/`nonce` exactly once; enable PKCE; require exact redirect-URI matching; use provider+subject as a joint unique identifier; rotate the session after login and prevent unsafe automatic account merging.

### sakurity/Sakurity - Peatio · 1. Connecting attacker’s weibo account to victim’s peatio account
- Knowledge value: 8/10; authentication bypass / state confusion / business logic.
- Chain: The attacker obtains a normal session or controllable identifier → manipulates a binding or recovery flow → the server associates an attacker-controlled factor with the victim account → login or sensitive action.
- Bypass: The flow validates existence but not ownership, purpose, session, or current state.
- Defensive anchor: Require reauthentication, strict token binding, object-level authorization, and old-factor confirmation for rebinding.

### hackmanit/Penetration-Test-Report-KeeWeb-by-Hackmanit · 6.4 M01 Use of an Embedded User-Agent for User Authentication
- Knowledge value: 7/10; authentication bypass / protocol-behavior exploitation / cross-component attack chain.
- Chain: The attacker controls or influences an embedded authentication context or message sender → reads, replaces, or injects the authorization result → the application binds the token to an attacker-chosen session/account → account takeover or token disclosure.
- Bypass: An embedded user agent shares control with the host, or weak postMessage source/target validation lets a valid authorization result cross into the wrong browser context.
- Defensive anchor: Use the system browser and claimed HTTPS/app-link callbacks; require PKCE, state, and nonce; prohibit embedded login; strictly validate postMessage origin, source, and message structure.

## HackerOne Case Index

### 55140 · OAuth/SSO callback and credential-lifecycle misbinding
- Knowledge value: 9/10; authentication bypass / state confusion / race condition.
- Chain: `GET /api/me?access_token=ACCESS_TOKEN_VALUE` → OAuth/SSO callback and credential-lifecycle misbinding, combined with a TOCTOU/concurrent-state failure → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Reuse, replace, or combine intermediate OAuth/SSO credentials, state, callbacks, or identity state across contexts so the validated object differs from the final login/authorization object; combine with a race.
- Defensive anchor: At final consumption, jointly validate the initiating session, subject, client, redirect URI, tenant, purpose, state/nonce, and one-time lifecycle; invalidate old credentials immediately after account switching, unlinking, revocation, or password changes; add race-focused cross-component regressions.

### 110293 · OAuth/SSO callback and credential-lifecycle misbinding
- Knowledge value: 9/10; authentication bypass / state confusion / path traversal.
- Chain: `https://` → OAuth/SSO callback and credential-lifecycle misbinding → security controls and the final execution point disagree about subject, object, state, or input semantics → account takeover.
- Bypass: Reuse, replace, or combine intermediate credentials, state, callbacks, or identity state across contexts so the validated object differs from the final login or authorization object.
- Defensive anchor: Validate all binding dimensions at the final consumer and invalidate old credentials immediately after relevant account-state changes.

### 172137 · OAuth/SSO callback and credential-lifecycle misbinding
- Knowledge value: 9/10; authentication bypass / state confusion / subdomain takeover.
- Chain: `https://*.ubnt.com` → OAuth/SSO callback and credential-lifecycle misbinding, combined with a subdomain-control and Cookie/SSO trust-boundary mismatch → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Combine cross-context credential or callback reuse with control of a trusted subdomain or overly broad Cookie/SSO trust.
- Defensive anchor: Validate all OAuth/SSO binding dimensions at the final consumer; immediately revoke stale credentials; add negative tests for subdomain control and Cookie/SSO trust boundaries.
