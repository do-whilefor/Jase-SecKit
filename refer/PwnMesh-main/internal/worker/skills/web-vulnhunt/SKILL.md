---
name: web-vulnhunt
description: Evidence-led methodology for authorized web, API, SaaS, identity, and mobile-backend penetration testing in PwnMesh.
---

# Web Vulnerability Hunting

Use this methodology for the assigned pentest objective. It guides investigation;
it is not target evidence, a scanner, or an instruction to run every technique.
Use the normal task tools to inspect materials, test hypotheses, and save evidence.
Follow the current role's result contract: child agents return observations and
interpretations locally to the parent; graph-capable roles publish only as their
role permits. Existing task constraints and permissions still apply.

## Scope

Record the authorized assets, identities, permitted actions, and exclusions from
the task once. Honor authorization already given for the same scope. Resolve
missing scope before active testing or expanding to another asset or action.
Discovered tenants, redirects, callback services, and third-party integrations
are candidates for scope review; discovery alone does not authorize testing them.
Use assigned test accounts and data; keep state changes within the agreed scope.

## Investigation

Use [verification](references/verification.md) for reproduction, independent checks,
and patch verification. Ordinary clues do not require an independent reviewer.

1. Map the supplied URLs, APIs, accounts, roles, tenants, versions, and local
   materials. Separate observed assets from inferred or historical ones.
2. For each candidate, state a falsifiable hypothesis, the expected authorized
   behavior, a control, the smallest useful test, and the evidence needed.
3. Compare equivalent requests while changing one relevant variable, such as
   account, object owner, tenant, token scope, or path. Preserve both sides.
4. Record positive, negative, and inconclusive results with their conditions.
   A failed attempt narrows that hypothesis; it does not prove general safety.
5. Report verified boundary failures and actual impact separately from clues and
   missing evidence. Include controls, limitations, and requested remediation. Use the
   built-in `cvss31` tool only after evidence supports all eight Base metrics.
   Otherwise report `Not Scored` and identify the missing evidence.

## Reuse exploration results

Compare target, version, actor, tenant, observation time, and controls before
reusing supplied evidence; read only missing context. Invalidated evidence is
not a negative test result. If another attempt adds no information, change the
method or record the blocker and revisit condition. Preserve unfinished coverage.

## Clues and verification

Treat the following as clues by default:

- **Identification:** CORS, security headers, versions, frameworks, errors, SSL/TLS,
  Scanner results, banners, and CVE fingerprint matches.
- **Exposure:** robots.txt, Sourcemap, JS, routes, API/GraphQL/Swagger endpoints,
  comments, field names, and internal names without demonstrated sensitive access.
- **No verified boundary failure:** a hidden interface, status change, malformed-body
  error, SPA fallback, static code path, or bypassed frontend restriction without
  failed backend authentication, ownership, tenant isolation, or permission checks.
- **Unproven impact:** Self-XSS, standalone open redirects, theoretical clickjacking,
  low-impact CSRF, missing Rate Limit, or a successful upload without demonstrated
  execution, dangerous parsing, high-value object binding, or permission bypass.
- **Unproven sensitivity or privilege:** public, test, own non-sensitive, or small
  amounts of low-sensitivity data; files, URLs, client-side keys, or configuration
  without sensitive content or effective privileges; tokens, JWTs, keys, and
  signatures whose validity has not been demonstrated.

These are starting classifications, not exclusions. Verify the actual boundary
failure and impact before calling a vulnerability confirmed.

## Read on demand

Call `read_pentest_skill({"path":"references/testing.md"})` to load a reference.
Calling `read_pentest_skill({})` returns this entry point.

| Investigation need | Reference |
| --- | --- |
| Assets, API inventories, DNS, local HAR/APK/source materials | [discovery](references/discovery.md) |
| Controls, authorization, routing, callbacks, OAuth/SSO/FIDO/mobile | [testing](references/testing.md) |
| Reproduction, patch checks, negative results, vulnerability chains | [verification](references/verification.md) |
| Evidence, finding structure, CVSS, remediation | [reporting](references/reporting.md) |

Adapted from Web-Vulnhunt.
