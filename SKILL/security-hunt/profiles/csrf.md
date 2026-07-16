---
id: cross-site-request-forgery
group: channels
reference: ../references/csrf.md
---

# Cross-Site Request Forgery

**Use for:** cookie-authenticated HTTP actions, form submissions, state-changing GET requests, login/logout flows, account linking, sensitive settings, and browser-triggered APIs.

**Misalignment to find:** The server treats ambient browser credentials as proof that the user intentionally initiated
the request from an authorized origin and interaction context.

## Baseline

- Cookies and other ambient credentials may be attached to cross-site requests automatically.
- Every state-changing action must distinguish intended same-site requests from attacker-triggered cross-site requests.
- SameSite cookies are one layer, not a complete substitute for action-specific request validation.
- Record the authentication mechanism, cookie attributes, request method, content type, Origin/Referer behavior, token binding, and final side effect.

## Validation Order

1. Identify state-changing endpoints and determine which browser request forms can reach them.
2. Test cross-site forms, simple requests, navigations, redirects, method overrides, alternate content types, and login/account-linking flows.
3. Vary Origin, Referer, CSRF token presence, token/session pairing, cookie SameSite mode, and top-level versus embedded navigation.
4. Verify the final state change through a clean read and confirm the affected user and action.

## Variant Axes

- Request form: form, fetch/XHR, image/navigation, iframe, redirect chain, multipart, text/plain
- Credential: session cookie, remember-me cookie, client certificate, browser-managed authentication
- Validation: token, Origin, Referer, custom header, SameSite, reauthentication, user confirmation
- Action: login, logout, account binding, email change, password change, payment, role or permission change

## Combination Paths

- `browser-channel`: Cross-Origin Channels
- `auth-state`: Authentication State
- `oauth-sso`: OAuth/SSO
- `workflow`: Business State Machines
