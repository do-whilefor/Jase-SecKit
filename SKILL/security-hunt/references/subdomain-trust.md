# Subdomain Trust · Reference

Load after selecting the `subdomain-cookie-sso-trust` Profile and forming a current-target hypothesis.

## Use Rule

- Use these sources to expand subdomain-control, cookie-scope, origin, and SSO trust hypotheses.
- Do not equate a subdomain takeover with account impact without proving the browser or identity trust path.
- Verify the final cookie, callback, session, message, or privileged action independently.

## Curated Sources

### OWASP Subdomain Takeover Prevention Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/Subdomain_Takeover_Prevention_Cheat_Sheet.html
- Transferable test ideas:
  - Inventory dangling DNS records, abandoned cloud resources, delegated zones, third-party hosting, and expired ownership bindings.
  - After proving control, separately test whether the parent application trusts the subdomain through cookies, CORS, postMessage, CSP, SSO, or redirects.
- Defensive anchor:
  - Remove stale records, verify resource ownership continuously, and minimize inherited trust across subdomains.

### OWASP Session Management Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- Transferable test ideas:
  - Review cookie `Domain`, `Path`, `Secure`, `HttpOnly`, and `SameSite` attributes across sibling applications.
  - Test whether a less-trusted subdomain can set, shadow, overwrite, or receive session-related cookies.
- Defensive anchor:
  - Prefer host-only cookies and separate high-trust applications from broadly delegated subdomain namespaces.
