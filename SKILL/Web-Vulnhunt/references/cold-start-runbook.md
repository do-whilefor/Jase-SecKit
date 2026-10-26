# Cold-Start Runbook — The First 60 Minutes on a Brand-New Target

The rest of this skill reads like a case file because it is one — distilled from one deep engagement on a Spring Boot / SCG / Keycloak / FIDO stack. This runbook is the **transferable entry point**: what to actually do, in order, when the target is new and nothing about it is known yet. It runs as Phase 0 + Phase 1; each block ends in a decision gate that routes you into the right reference. Total budget: ~60 minutes to a ranked hypothesis backlog. Scope model: the user's stated target and intent *are* the scope (ethics §1) — record it, then go.

---

## Minute 0–5 — Scope record + DNS reality check

1. **Record the scope** from the user's input: named targets/domains, requested vuln classes, depth (read-only sweep vs full chain). This is note-taking for the report's scope section, not a gate.
2. **Sinkhole detection** — resolve `totallymadeup.<domain>` (`scripts/sinkhole-detector.sh`).

**GATE G1:** If the fake hostname returns `198.18.0.0/15` → you're behind an RFC 2544 sinkhole resolver: **CT-log-only mode** for the whole session; never trust DNS absence, validate every hostname by live HTTP probe. Otherwise → normal DNS + CT both usable.

## Minute 5–20 — Hostname inventory (read `osint-asset-discovery.md` §recipe)

One command covers steps 1–4: `./scripts/recon.sh <domain> --out recon-<domain>` — sinkhole re-check + CT enumeration (jq-free) + vault-prefix mining + cloud error-leak pass + live-host validation, emitting `hosts-live.txt`, `vault-tenants.txt`, `aws-accounts.txt`, `surface-summary.txt`. Run it first; read the recipe below when you need the manual detail.

1. CT-log enumeration: `crt.sh` for `*.domain` (+ `cdn.`/app subdomains separately). Down → fallback chain (DNS brute → sitemap → statuspage → CloudFront/S3 error-leak).
2. Multi-tenant prefix mining: `vault-<name>.<aws-id>.<domain>` regex → customer roster + AWS account IDs.
3. Cloud error-leak pass: `assets.<domain>`-style S3/CloudFront `AccessDenied` XML → STS ARN (account + role names).
4. Live-host validation: HTTP-probe every CT-discovered hostname (sinkhole IPs `000`/timeout; real hosts answer). Bucket: LIVE / NXDOMAIN / timeout.

**GATE G2:** ≥1 live host? → continue. Zero live hosts but valid CT certs → the target is app-layer-only reachable: pivot to APK/SPA/doc mining (steps below work offline) and say so in the notes. Zero certs *and* zero DNS → wrong domain or scoped-out target: re-read the user's scope statement before improvising.

## Minute 20–35 — Surface mapping (read `osint-asset-discovery.md` rows for tooling)

1. Build fingerprint: unauth `GET /info`, `/health`, `/actuator/health`, `/` — version/build/commit metadata; note the framework from error templates (RFC 7807 `type` paths) and cookies (Spring Session UUID vs JWT vs custom).
2. API-doc discovery: docs subdomains → Postman CNAME / Docusaurus sitemap / OpenAPI JSON. Extract all state-changing endpoints, bucket by controller namespace, flag admin paths.
3. SPA bundle download (if any): main JS → regex `/api/*` paths (endpoint pass now; DOM-sink pass later via `client-side-dom.md`).
4. IdP probe: `/.well-known/openid-configuration` on candidate realm paths; note realms, `jwks_uri`, grant types.
5. Mobile APK (if the product has one): `apkeep` + `jadx` — endpoint inventory + SSL-pin logic + deep-link surface.

**GATE G3:** You now have an endpoint inventory × auth-gate class (unauth / user-token / admin-session). If inventory is empty → target is a thin edge: spend the remaining budget on `bypass-catalogue.md` §0 ladder + `cache-poisoning.md` against the live hosts.

## Minute 35–50 — Envelope fingerprint + auth-gate classification (read `http-auth-filter-testing.md` §1)

1. **Response-envelope oracle**: send malformed + valid + forbidden requests to 3-5 representative endpoints and classify every rejection into the four-way discriminator: edge-reject (uniform gateway 403 envelope) / origin-reject (400/415 framework signature) / SPA fallback (200 HTML, 405 on non-GET) / controller reach (200 JSON or operation-confirmed). Record each envelope verbatim — every later test classifies against it.
2. **Authz smoke** (if any low-priv token is already in hand): run `scripts/authz-matrix.sh` on the OpenAPI spec — one pass, low volume. A lone 200-with-data in a 403 class is the first finding candidate.
3. **Negative-control baseline**: pick the enumeration-looking endpoints (login, register, password-reset) and run each once with a guaranteed-nonexistent identifier — record the "absent" response verbatim. Every later oracle claim diffs against this.

**GATE G4:** Auth model classified (filter vs annotation vs scope-enum). This decides which bypass family is plausible and whether `bypass-catalogue.md` §L or `http-auth-filter-testing.md` is the working reference.

## Minute 50–60 — Primitive inventory + hypothesis backlog

Capture the primitive list — the raw materials every later chain composes from:
- **Token taxonomy**: every credential shape seen so far (prefix, type, TTL, where issued) — feeds `jwt-jose-attacks.md` §0.
- **URL-accepting fields**: every request field that takes a URL (`jwksUrl`, `webhookUrl`, `callback`, proxy hosts) — the SSRF/JWKS sink shortlist (§K method).
- **Enumeration oracles**: size/timing/status differentials spotted — candidates only; each needs the negative control before claiming.
- **State-changing unauth endpoints**: the Tier-3 placeholder shortlist — highest-value, highest-care list.
- **Rate-limit observations**: which endpoints count, which don't (F24 pattern) — feeds `race-conditions.md` §1.

Rank the backlog (impact × reachability × evidence cost), write it down — into the ledger, so the next session resumes at max value: `./scripts/hunt-ledger.sh init`, then one `add <class> <target> "<hypothesis>" "<falsification>" <prio>` per item (the falsification design is mandatory; `./scripts/hunt.sh next` later picks up exactly where you left off). Then route by what the target actually is:

| Target shows… | Read next |
|---|---|
| JWT/OAuth tokens anywhere | `jwt-jose-attacks.md` |
| GraphQL endpoint or bundle evidence | `graphql-testing.md` |
| Cache headers / CDN fronting | `cache-poisoning.md` |
| Concurrency-sensitive single-use ops | `race-conditions.md` |
| JS-heavy SPA (always, if present) | `client-side-dom.md` |
| FIDO/WebAuthn/UAF endpoints | `fido-webauthn-testing.md` |
| WAF / 403 wall / path filter | `bypass-catalogue.md` §0 |
| CVE-suspect versions from `/info` | `cve-watchlist.md` (entry rule applies) |

---

## Framework-agnostic notes (non-Spring / non-FIDO targets)

- The envelope oracle transfers directly: every stack has edge-reject / origin-reject / fallback / success signatures — the literal envelopes differ, the four-way classification doesn't. Spend GATE G3's first minutes recording *this stack's* signatures.
- The bypass ladder, authz matrix, negative-control discipline, and Tier framework are framework-free. What *is* Spring-specific: `@PreAuthorize` terminology (read "per-route authz annotation"), SCG envelopes, actuator paths (map to the stack's own debug/management surface).
- If the stack is Node/Go/PHP/dotnet: keep the runbook order, swap the framework-specific rows (GATE G3 fingerprint sources), and expect `cache-poisoning.md` + `client-side-dom.md` to carry more of the load than the Spring-centric files.
- Anything not covered by a reference: run the loop (hypothesis → falsification design → bounded test → record positive OR negative) and write the negative into `killed-hypotheses.md` — the runbook's job is to make you dangerous in 60 minutes, not to replace the discipline.
