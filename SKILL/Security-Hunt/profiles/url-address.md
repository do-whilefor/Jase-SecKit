---
id: ssrf-url-address
group: normalize
reference: ../references/url-address.md
---

# URLs & Addresses

**Use for:** webhooks/callbacks, URL previews, remote imports, image/PDF fetchers, proxies, and OIDC/JWKS metadata.

**Misalignment to find:** The URL string seen by a filter, the parsed host, DNS results, redirect target, and the final network address reached by the stack do not match.

## Baseline

- A URL string is not the final connection target.
- Look for parser differences, redirects, DNS changes, special IPv4/IPv6 forms, userinfo, and proxy rewriting.
- Focus on a validated target that differs from the final socket peer.
- Record the raw URL, canonical URL, every DNS result, each redirect hop, and final peer address.

## Validation Order

1. Use one strict parser to record scheme, host, and port.
2. After resolution, validate every address family and IP.
3. Reapply policy at every redirect and before the final connection.
4. Test DNS changes, special address forms, proxies, and connection reuse.
5. Prove impact through an internal-service response or out-of-band evidence.

## Variant Axes

- URL parse: scheme, userinfo, host, port, fragment
- Host representation: IPv4/IPv6, integer, octal, mixed encoding, IDNA
- Resolution timing: validation, DNS, rebinding, redirect, final connection
- Network stack: proxy, NO_PROXY, dual stack, Unix socket, cloud metadata

## Combination Paths

- `unicode`: Unicode Normalization
- `proxy-origin`: Proxies & Origins
- `shared-state`: Shared Protocol State
