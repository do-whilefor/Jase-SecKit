# HTTP Boundaries · Reference

Load after selecting the `http-message-boundary` Profile and forming a current-target hypothesis.

## Use Rule

- Use protocol specifications to identify parsing and forwarding assumptions, not to infer a vulnerability from malformed traffic alone.
- Compare the exact message boundaries seen by every intermediary and the final backend.
- Prove a security-relevant routing, request, cache, or response effect independently.

## Curated Sources

### RFC 9112 · HTTP/1.1 Message Syntax and Parsing

- Source URL: https://www.rfc-editor.org/info/rfc9112/
- Transferable test ideas:
  - Map how each hop handles message length, transfer coding, connection-specific fields, invalid syntax, and ambiguous framing.
  - Compare strict rejection with normalization, forwarding, and backend interpretation.
  - Preserve raw bytes at each observable hop and use controls to isolate the parser disagreement.
- Defensive anchor:
  - Use consistent, standards-compliant parsers and reject ambiguous or invalid framing before forwarding.

### RFC 9113 · HTTP/2

- Source URL: https://www.rfc-editor.org/info/rfc9113/
- Transferable test ideas:
  - Trace HTTP/2 to HTTP/1 conversion, pseudo-header handling, field normalization, and request boundary reconstruction.
  - Test whether gateways and backends derive the same authority, path, method, length, and connection semantics.
- Defensive anchor:
  - Normalize once at a trusted boundary and ensure downgrade paths cannot create a second interpretation.
