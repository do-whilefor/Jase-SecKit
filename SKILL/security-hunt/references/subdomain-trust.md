# Subdomain Trust · Reference

Load after selecting the `subdomain-cookie-sso-trust` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## HackerOne Case Index

### 1018790 · Subdomain-control and Cookie/SSO trust-boundary mismatch
- Knowledge value: 9/10; subdomain takeover / cross-component attack chain / authorization bypass.
- Chain: `PUT /v2/account` → subdomain-control and Cookie/SSO trust-boundary mismatch → security controls and the final execution point disagree about subject, object, state, or input semantics → access to or impact on another user’s data/state.
- Bypass: Take control of a legacy subdomain or cloud resource, then exploit the main application’s Cookie, Origin, SSO, CSP, or redirect trust in that subdomain.
- Defensive anchor: Continuously remove dangling DNS/cloud bindings; do not issue parent-domain cookies to low-trust subdomains; explicitly enumerate trusted Origins and callbacks; separate static, user-content, and third-party hosting domains from authentication domains.
