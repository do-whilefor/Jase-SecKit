# Input Chains

## Goal

Trace semantic changes as the same input crosses multiple consumers, and locate where upstream treats it as data while
a downstream parser, interpreter, or protocol treats it as control content.

## Route Here When

Use this module as primary when the same attacker-controlled value is reinterpreted across processing stages or
components. Prefer `normalize/path` when canonicalization alone changes the resolved target, and prefer
`system/fs-identity` when a validated path and the filesystem object ultimately opened are different.

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| File upload/import/export; archive extraction and dependency handling; configuration, repository metadata, and package installation | `file-chain` | File Processing Chain |
| Polymorphic deserialization; object merge/deep copy; automatic parameter binding | `object-types` | Objects & Types |
| HTML/SVG/MathML sanitization; rich-text editors; frontend templates | `browser-parse` | Browser Parsing |
| Deep merge/filtering; object-path assignment; configuration override | `prototype` | Prototype Pollution |
| Audit logs; SSH/operations platforms; CI output | `terminal-escape` | Terminal Escapes |
| HTTP headers/cookies; download filenames; MIME/email | `field-injection` | Protocol Field Injection |
| SQL/NoSQL/LDAP/XPath; server templates; expression and query DSLs | `server-interpreters` | Server Interpreters |

## Workflow

1. Enumerate entry points, persistence locations, background jobs, parsers, interpreters, and every downstream consumer.
2. Map the raw value, normalized value, grammar or parse tree, construction API, working directory, and privilege at each hop in actual execution order.
3. Validate one semantic transition first, then follow it to the final file, DOM, object, query, expression, command, log, or protocol state.
4. Preserve evidence for each hop in a cross-component chain, then confirm the final result through an independent read or side effect.

## Do Not Stop Here

- Looking only at the upload endpoint while ignoring preview, export, build, synchronization, and installation stages.
- Stopping after a filter bypass, syntax error, or changed response without confirming that the final consumer actually executes under a different interpretation.
- Reporting ordinary reflection, an error, or an unreachable gadget as a vulnerability.
