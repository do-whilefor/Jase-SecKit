# Normalization

## Goal

Compare the values seen by validation, proxy, framework, and final execution layers, and determine whether they resolve to the same subject, object, and target.

## Route Here When

Use this module as primary when two layers derive different meanings from the same representation.

Choose the Profile from the concrete disagreement:

- Use `params` only when a parser, binder, or precedence rule selects a different value; REST, forms, or JSON alone are not enough.
- Use `url-address` when URL parsing, DNS, redirects, or the final connection target diverge.
- Use `proxy-origin` when a proxy and application disagree about external host, scheme, origin, tenant, or trusted client identity.

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| Domain/Origin allowlists; paths and filenames; keyword filters | `unicode` | Unicode Normalization |
| Download/upload paths; static files and reverse proxies; archive extraction | `path` | Path Canonicalization |
| REST APIs; gateways/WAFs; forms/JSON | `params` | Parameter Parsing |
| Proxy to backend; CDN/WAF; H2 to H1 conversion | `http-boundary` | HTTP Boundaries |
| Webhooks/callbacks; URL previews; remote imports | `url-address` | URLs & Addresses |
| Reverse proxies; password-reset links; SSO callbacks | `proxy-origin` | Proxies & Origins |

## Workflow

1. Preserve raw bytes, transport representation, and the parsed value produced by each layer.
2. Test one axis at a time: encoding, case, duplicate values, path form, length, protocol conversion, and redirects.
3. Use controls to show that the difference comes from parsing rules rather than random routing, cache state, or backend instability.
4. Prove that the final route, file, network address, tenant, cache object, or request boundary changes.

## Do Not Stop Here

- Inferring a parsing difference from status-code differences alone.
- Calling every layer “the server” instead of separating CDN, proxy, gateway, framework, and business logic.
- Combining many encoding and boundary variants in one request and losing the root cause.
