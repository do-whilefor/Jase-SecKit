# OAuth/SSO · Reference


Load on demand after selecting the `oauth-sso-lifecycle` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### cure53/Pomerium-Cure53-042021 · POM-01-001 WP1: JWT leak via Open Redirect in programmatic access
- Value: 10/10; authentication bypass / protocol-behavior exploitation / cross-component attack chain.
- Chain: The attacker creates a programmatic-login URL that returns to a malicious site → an authenticated victim opens it → Pomerium completes authentication and appends a JWT to the malicious return URL → the attacker obtains the JWT, queries the victim’s identity, or impersonates the victim in integrations with weak audience checks.
- Bypass: The authentication proxy accepts an arbitrary return URL and places a bearer JWT in the redirect URL; downstream integrations may amplify impact by validating only issuer and not audience.
- Defensive anchor: Use exact preregistered return-URL allowlists; deliver tokens only over protected backend channels; validate `iss`, `aud`, `nonce`, purpose, and one-time state; validate every `/.pomerium/` parameter consistently and add regressions.

### cure53/pentest-report fxa · FXA-01-007 Reusable Authorization Code on OAuth Server
- Value: 9/10; authentication bypass / state confusion / cross-component attack chain.
- Chain: The attacker prepares or intercepts authentication context → induces the victim to complete a callback or reuse an authorization result → the server binds an attacker-controlled identity or code to the victim session → account takeover or token disclosure.
- Bypass: `state`, `nonce`, PKCE, callback port, provider identity, or account resolution is not strongly bound to the original session, so a valid result is attributed to the wrong subject.
- Defensive anchor: Validate and consume `state`/`nonce` exactly once; enable PKCE; require exact redirect-URI matching; use provider+subject as a joint unique identifier; rotate the session after login and prevent unsafe automatic account merging.

### sakurity/Sakurity - Peatio · 1. Connecting attacker’s weibo account to victim’s peatio account
- Value: 8/10; authentication bypass / state confusion / business logic.
- Chain: The attacker obtains a normal session or controllable identifier → manipulates a binding or recovery flow → the server associates an attacker-controlled factor with the victim account → login or sensitive action.
- Bypass: The flow validates existence but not ownership, purpose, session, or current state.
- Defensive anchor: Require reauthentication, strict token binding, object-level authorization, and old-factor confirmation for rebinding.

### hackmanit/Penetration-Test-Report-KeeWeb-by-Hackmanit · 6.4 M01 Use of an Embedded User-Agent for User Authentication
- Value: 7/10; authentication bypass / protocol-behavior exploitation / cross-component attack chain.
- Chain: The attacker controls or influences an embedded authentication context or message sender → reads, replaces, or injects the authorization result → the application binds the token to an attacker-chosen session/account → account takeover or token disclosure.
- Bypass: An embedded user agent shares control with the host, or weak postMessage source/target validation lets a valid authorization result cross into the wrong browser context.
- Defensive anchor: Use the system browser and claimed HTTPS/app-link callbacks; require PKCE, state, and nonce; prohibit embedded login; strictly validate postMessage origin, source, and message structure.


## HackerOne Case Index


### 55140 · OAuth/SSO callback and credential-lifecycle misbinding
- Value: 9/10; authentication bypass / state confusion / race condition.
- Chain: `GET /api/me?access_token=ACCESS_TOKEN_VALUE` → OAuth/SSO callback and credential-lifecycle misbinding, combined with a TOCTOU/concurrent-state failure → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Reuse, replace, or combine intermediate OAuth/SSO credentials, state, callbacks, or identity state across contexts so the validated object differs from the final login/authorization object; combine with a race.
- Defensive anchor: At final consumption, jointly validate the initiating session, subject, client, redirect URI, tenant, purpose, state/nonce, and one-time lifecycle; invalidate old credentials immediately after account switching, unlinking, revocation, or password changes; add race-focused cross-component regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 110293 · OAuth/SSO callback and credential-lifecycle misbinding
- Value: 9/10; authentication bypass / state confusion / path traversal.
- Chain: `https://` → OAuth/SSO callback and credential-lifecycle misbinding → security controls and the final execution point disagree about subject, object, state, or input semantics → account takeover.
- Bypass: Reuse, replace, or combine intermediate credentials, state, callbacks, or identity state across contexts so the validated object differs from the final login or authorization object.
- Defensive anchor: Validate all binding dimensions at the final consumer and invalidate old credentials immediately after relevant account-state changes.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 172137 · OAuth/SSO callback and credential-lifecycle misbinding
- Value: 9/10; authentication bypass / state confusion / subdomain takeover.
- Chain: `https://*.ubnt.com` → OAuth/SSO callback and credential-lifecycle misbinding, combined with a subdomain-control and Cookie/SSO trust-boundary mismatch → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Combine cross-context credential or callback reuse with control of a trusted subdomain or overly broad Cookie/SSO trust.
- Defensive anchor: Validate all OAuth/SSO binding dimensions at the final consumer; immediately revoke stale credentials; add negative tests for subdomain control and Cookie/SSO trust boundaries.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 6.
- HackerOne reports: 69.
- Full report IDs:
  - cure53/Pomerium-Cure53-042021
  - cure53/pentest-report fxa
  - sakurity/Sakurity - Peatio
  - hackmanit/Penetration-Test-Report-KeeWeb-by-Hackmanit
  - x41-d-sec/X41-Backstage-Audit-2022-Final-Report-PUBLIC
  - hackmanit/Penetration-Test-Report-WAYF-Identity-Provider-SAML-and-OpenID-Connect-by-Hackmanit
- HackerOne report IDs:
  - 1256777, 143240, 136582, 1049375, 335599, 2147132, 812064, 1327742, 1861974, 215381, 138270, 143220, 170552, 2101076, 519418, 850022, 1692788, 100667
  - 976603, 110293, 211477, 736391, 405100, 1045644, 895202, 1104077, 1165540, 131202, 1363672, 702987, 1533976, 565883, 172137, 384962, 292783, 44425
  - 50157, 6017, 317476, 1178239, 55140, 3596, 99435, 84709, 219205, 314126, 2559, 356284, 171398, 1285226, 703759, 1820953, 791775, 145392
  - 1923672, 734936, 244958, 72793, 129712, 152586, 292825, 1700734, 176308, 99708, 922456, 2037902, 716292, 57603, 194721

