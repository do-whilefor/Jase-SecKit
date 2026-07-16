# Normalization

## Goal

Compare the values seen by validation, proxy, framework, and final execution layers, and determine whether they resolve to the same subject, object, and target.

## Primary Boundary

Use this module as primary when two layers derive different meanings from the same representation.

Choose the Profile from the concrete disagreement:

- Use `params` only when a parser, binder, or precedence rule selects a different value; REST, forms, or JSON alone are not enough.
- Use `url-address` when URL parsing, DNS, redirects, or the final connection target diverge.
- Use `proxy-origin` when a proxy and application disagree about external host, scheme, origin, tenant, or trusted client identity.

## Loading Order

1. Read `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md` first.
2. Load the Profiles needed for the concrete hypothesis; keep plausible adjacent and combination paths queued, and add
   them whenever evidence, gaps, or downstream consumers require it.
3. Establish a baseline before reading matching References for additional variants. Progressive loading limits context use, not testing breadth or depth.

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| Domain/Origin allowlists; paths and filenames; keyword filters | `unicode` | Unicode Normalization |
| Download/upload paths; static files and reverse proxies; archive extraction | `path` | Path Canonicalization |
| REST APIs; gateways/WAFs; forms/JSON | `params` | Parameter Parsing |
| Proxy to backend; CDN/WAF; H2 to H1 conversion | `http-boundary` | HTTP Boundaries |
| Webhooks/callbacks; URL previews; remote imports | `url-address` | URLs & Addresses |
| Reverse proxies; password-reset links; SSO callbacks | `proxy-origin` | Proxies & Origins |

Profile paths are `${CLAUDE_SKILL_DIR}/profiles/<name>.md`; Reference paths are `${CLAUDE_SKILL_DIR}/references/<name>.md`.

## Workflow

1. Preserve raw bytes, transport representation, and the parsed value produced by each layer.
2. Test one axis at a time: encoding, case, duplicate values, path form, length, protocol conversion, and redirects.
3. Use controls to show that the difference comes from parsing rules rather than random routing, cache state, or backend instability.
4. Prove that the final route, file, network address, tenant, cache object, or request boundary changes.

## Do Not Stop Here

- Inferring a parsing difference from status-code differences alone.
- Calling every layer “the server” instead of separating CDN, proxy, gateway, framework, and business logic.
- Combining many encoding and boundary variants in one request and losing the root cause.

## Output

Record each round with the complete status, blackboard, evidence, impact-validation, severity-gate, blind-spot, and
closure rules in `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md`; do not replace them with a reduced local schema.
