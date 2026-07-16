---
id: protocol-field-injection
group: input
reference: ../references/field-injection.md
---

# Protocol Field Injection

**Use for:** HTTP headers/cookies, download filenames, MIME/email, SSH/SCP, and messaging protocols.

**Misalignment to find:** Filenames, headers, MIME fields, cookies, SCP/XMPP fields, or other protocol data are
reinterpreted by another endpoint as control information, cross-domain state, or a different content type.

## Baseline

- A protocol field may be data at the sender and syntax or persistent state at the receiver.
- Look for unescaped delimiters, line breaks, control characters, MIME types, field replay, and state persistence.
- Focus on one endpoint validating a string while another reparses it into protocol fields.
- Record wire bytes, field boundaries, the receiver parse tree, persisted state, and later requests.

## Validation Order

1. Identify every field that is forwarded, persisted, or serialized again.
2. Inject delimiters, line breaks, control characters, and alternate encodings.
3. Observe receiver fields, cookie/cache/file state, and subsequent sessions.
4. Use an independent later request to prove cross-component impact.

## Variant Axes

- Field location: header, cookie, MIME, filename, message attribute, protocol parameter
- Boundary characters: CR/LF, semicolon, comma, quote, backslash, NUL
- Escaping and folding: encoding, quoting, line folding, case, duplicate fields
- Parser roles on both sides and subsequent state writes

## Combination Paths

- `http-boundary`: HTTP Boundaries
- `terminal-escape`: Terminal Escapes
- `shared-state`: Shared Protocol State
