---
id: cache-key-variant
group: channels
reference: ../references/cache-variant.md
---

# Cache Variants

**Use for:** CDNs/reverse proxies, page caches, API caches, static rendering, and edge functions.

**Misalignment to find:** An input that changes the origin response, identity, or security properties is omitted from
a shared cache key, causing a response variant created by an attacker to be reused for other users.

## Baseline

- A cache key must fully represent every security-relevant response variant.
- Look for unkeyed headers, cookies, hosts, query parameters, normalization differences, or omitted user context.
- Focus on requests that produce different origin responses but are treated as equivalent by the cache.
- Record the cache key, Vary behavior, hit state, origin response, and independent session.

## Validation Order

1. Identify every input that affects response content, identity, routing, or encoding.
2. Compare cache-key construction and hit behavior for each input.
3. Populate the cache with an attacker request, then verify with a clean request from an independent session.
4. Prove cross-user response reuse or a persistent effect.

## Variant Axes

- Response-affecting input: Host, header, cookie, query, path, encoding
- Cache key, Vary, normalization, and layered-cache composition
- User, role, tenant, language, device, and authentication state
- Populator, recipient, TTL, revalidation, and purge behavior

## Combination Paths

- `proxy-origin`: Proxies & Origins
- `http-boundary`: HTTP Boundaries
- `shared-state`: Shared Protocol State
- `tenant-isolation`: Tenant Isolation
