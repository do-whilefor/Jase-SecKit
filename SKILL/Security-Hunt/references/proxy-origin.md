# Proxies & Origins · Reference

Load after selecting the `host-origin-proxy-trust` Profile and forming a current-target hypothesis.

## Use Rule

- Use these sources to expand host, scheme, origin, client-IP, and forwarded-metadata hypotheses.
- Record the value produced by each proxy and the value consumed by the application.
- Verify the final link, redirect, tenant, authorization decision, cache entry, or callback independently.

## Curated Sources

### OWASP WSTG · Testing for Host Header Injection

- Source URL: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/07-Input_Validation_Testing/17-Testing_for_Host_Header_Injection
- Transferable test ideas:
  - Vary `Host`, forwarded host, forwarded scheme, origin, absolute-form targets, and conflicting proxy metadata.
  - Test password-reset links, redirects, SSO callbacks, tenant routing, cache keys, and trusted-client decisions.
  - Compare direct-backend and normal-proxy paths where both are in scope.
- Defensive anchor:
  - Configure trusted proxies explicitly and accept forwarded metadata only from those hops.
  - Use configured canonical external origins for security-sensitive links and callbacks.
