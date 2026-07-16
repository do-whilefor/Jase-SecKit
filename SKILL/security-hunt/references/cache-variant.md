# Cache Variants · Reference

Load after selecting the `cache-key-variant` Profile and forming a current-target hypothesis.

## Use Rule

- Use protocol sources to reason about cache identity and response reuse, not to infer current-target impact.
- Test the actual cache layers, key construction, `Vary` behavior, authentication context, and independent recipients.
- Confirm any cross-user or persistent effect from a clean session.

## Curated Sources

### RFC 9111 · HTTP Caching

- Source URL: https://www.rfc-editor.org/info/rfc9111/
- Transferable test ideas:
  - Enumerate every request input that changes response content, routing, identity, encoding, or security properties.
  - Compare those dimensions with the effective cache key and `Vary` handling at every cache layer.
  - Populate a candidate variant with one identity and verify reuse with an independent identity or unauthenticated request.
- Defensive anchor:
  - Include every security-relevant response dimension in cache identity or mark the response non-shareable.
  - Keep authentication and tenant-specific responses out of shared caches unless isolation is explicit and verified.
