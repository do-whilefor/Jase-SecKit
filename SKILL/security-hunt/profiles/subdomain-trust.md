---
id: subdomain-cookie-sso-trust
group: identity
reference: ../references/subdomain-trust.md
---

# Subdomain Trust

**Use for:** multi-subdomain organizations, broad-domain cookies, SSO callbacks, CORS allowlists, and third-party hosting/custom domains.

**Misalignment to find:** An organization treats subdomains under one parent as a single trust domain, while subdomain takeover, third-party hosting, or broad-domain Cookie/SSO behavior lets a low-trust subdomain affect a high-trust application.

## Baseline

- A DNS administration boundary is not the same as a browser trust boundary.
- Look for controllable subdomains, Domain cookies, same-site requests, broad origin/redirect allowlists, and shared SSO.
- Focus on low-trust subdomains inheriting capabilities of the high-trust domain.
- Record DNS control, Cookie Domain, SameSite, origin, redirect_uri, and SSO audience.

## Validation Order

1. Map every subdomain and its controlling party.
2. Mark broad-domain cookies, CORS, SSO, and callback trust.
3. From controllable or third-party subdomains, test cookie injection, messaging, callbacks, and same-site requests.
4. Prove impact through state changes in the high-trust application.

## Variant Axes

- Subdomain control: takeover, third-party hosting, user content, legacy applications
- Cookie: Domain, Path, prefix, overwrite order, SameSite
- SSO: callback allowlist, shared login state, parent-domain redirects, tickets
- Write, read, and navigation capabilities between low- and high-trust applications

## Combination Paths

- `proxy-origin`: Proxies & Origins
- `oauth-sso`: OAuth/SSO
- `browser-channel`: Cross-Origin Channels
