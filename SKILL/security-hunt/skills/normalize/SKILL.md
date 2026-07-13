---
name: Normalization
description: Validation and execution layers derive different meanings from characters, paths, parameters, HTTP messages, URLs, or proxy identity. Use for authorized testing of Unicode normalization, path canonicalization, parameter parsing, HTTP boundaries, URLs and addresses, and proxy/origin handling.
user-invocable: false
allowed-tools: Read Grep Glob Bash
---

# Normalization

## Goal

Compare the values seen by validation, proxy, framework, and final execution layers, and determine whether they resolve to the same subject, object, and target.

## Loading Order

1. Read `${CLAUDE_PLUGIN_ROOT}/framework/verify-evidence.md` first.
2. Choose one or two Profiles based on the entry point, component, and anomaly; do not load every Profile in the group at once.
3. After forming a testable hypothesis, read the matching Reference for additional cases and variants.
4. When a chain crosses boundaries, load material from other groups according to the Profile’s “Combination Paths.”

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| Domain/Origin allowlists; paths and filenames; keyword filters | `unicode` | Unicode Normalization |
| Download/upload paths; static files and reverse proxies; archive extraction | `path` | Path Canonicalization |
| REST APIs; gateways/WAFs; forms/JSON | `params` | Parameter Parsing |
| Proxy to backend; CDN/WAF; H2 to H1 conversion | `http-boundary` | HTTP Boundaries |
| Webhooks/callbacks; URL previews; remote imports | `url-address` | URLs & Addresses |
| Reverse proxies; password-reset links; SSO callbacks | `proxy-origin` | Proxies & Origins |

Profile paths are `${CLAUDE_PLUGIN_ROOT}/profiles/<name>.md`; Reference paths are `${CLAUDE_PLUGIN_ROOT}/references/<name>.md`.

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

For each round, record only: Profile used, target object, testing identity, hypothesis, baseline, variant, independent verification, evidence path, current status, and next step or combination path. Mark a finding `confirmed` only when it meets the evidence threshold in the unified framework.
