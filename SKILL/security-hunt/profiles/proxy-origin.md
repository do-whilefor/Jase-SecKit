---
id: host-origin-proxy-trust
group: normalize
reference: ../references/proxy-origin.md
---

# Proxies & Origins

**Use for:** reverse proxies, password-reset links, SSO callbacks, multi-tenant Host routing, and CORS/WebSocket handling.

**Misalignment to find:** The application incorrectly trusts client-controlled Host, Origin, or forwarding headers, or the proxy and backend disagree about the external origin, scheme, or host identity.

## Baseline

- External host, scheme, client IP, and origin must be established only by a trusted boundary.
- Look for Host, X-Forwarded-*, Forwarded, or Origin rewriting and incorrect trusted-proxy configuration.
- Focus on frontend and backend disagreement about request origin or host identity.
- Record the connection peer, proxy chain, raw headers, canonical external URL, and tenant route.

## Validation Order

1. Map the proxy chain and mark which headers each layer can overwrite.
2. Send requests through direct connections, untrusted proxies, and different Host/Origin values.
3. Compare generated links, callbacks, cookies, caching, and authorization results.
4. Prove impact through cross-tenant effects, credential disclosure, or origin bypass.

## Variant Axes

- Host, :authority, Origin, Referer, and Forwarded/X-Forwarded-*
- Proxy overwrite order, trusted-proxy list, and direct backend access
- External versus internal views of scheme, host, and port
- Absolute URLs, callbacks, caches, cookies, security redirects, and tenant routing

## Combination Paths

- `cache-variant`: Cache Variants
- `oauth-sso`: OAuth/SSO
- `url-address`: URLs & Addresses
