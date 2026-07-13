# Subdomain Trust · Reference


Load on demand after selecting the `subdomain-cookie-sso-trust` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## HackerOne Case Index


### 1018790 · Subdomain-control and Cookie/SSO trust-boundary mismatch
- Value: 9/10; subdomain takeover / cross-component attack chain / authorization bypass.
- Chain: `PUT /v2/account` → subdomain-control and Cookie/SSO trust-boundary mismatch → security controls and the final execution point disagree about subject, object, state, or input semantics → access to or impact on another user’s data/state.
- Bypass: Take control of a legacy subdomain or cloud resource, then exploit the main application’s Cookie, Origin, SSO, CSP, or redirect trust in that subdomain.
- Defensive anchor: Continuously remove dangling DNS/cloud bindings; do not issue parent-domain cookies to low-trust subdomains; explicitly enumerate trusted Origins and callbacks; separate static, user-content, and third-party hosting domains from authentication domains.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 0.
- HackerOne reports: 2.
- HackerOne report IDs:
  - 335330, 1018790

