---
id: http-parser-differential
group: normalize
reference: ../references/http-boundary.md
---

# HTTP Boundaries

**Use for:** proxy-to-backend paths, CDNs/WAFs, H2-to-H1 conversion, connection pools, and service meshes.

**Misalignment to find:** Front proxies, gateways, protocol converters, and backends derive different message boundaries from request lengths, duplicate headers, line endings, H2/H1 conversion, or connection reuse.

## Baseline

- The same byte stream must produce one message boundary at every hop.
- Look for CL/TE ambiguity, duplicate headers, invalid line endings, pseudo-headers, length truncation, and protocol-conversion differences.
- Focus on an upstream layer validating one request while downstream executes two requests or a different request.
- Record raw bytes, parse boundaries, connection reuse, and the subsequent victim request at every hop.

## Validation Order

1. Identify every HTTP hop and protocol version.
2. Send ambiguous but controlled boundary probes.
3. Compare frontend/backend responses, timeouts, connection contamination, and behavior of the next request.
4. Use an independent subsequent request to prove routing, caching, or authorization impact.

## Variant Axes

- Length: Content-Length, Transfer-Encoding, H2 length
- Duplicate headers, whitespace, case, obs-fold, and line endings
- H2/H1, proxy chains, connection reuse, and upgrades
- Frontend boundary, backend boundary, and ownership of the next request

## Combination Paths

- `params`: Parameter Parsing
- `cache-variant`: Cache Variants
- `proxy-origin`: Proxies & Origins
