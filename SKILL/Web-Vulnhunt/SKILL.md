---
name: Web-Vulnhunt
description: Web/API/mobile-backend vulnerability-hunting methodology for bug bounty, authorized pentests, CTF, post-patch re-verification, CVSS scoring, asset discovery, WAF/403 bypass, authorization bypass / IDOR / missing @PreAuthorize, FIDO2/WebAuthn/UAF, OAuth/SSO (Keycloak, Okta, PingFederate, Auth0), token-chain analysis, APK reverse engineering, and vulnerability report writing. Triggers on "AcmeAuth" too. Scope model: the user's request defines the working scope — test the targets the user names (operator-responsibility model, no separate authorization gate).
---

# Web Vulnerability-Hunting Methodology

Field-tested methodology distilled from a 13-session, 30+-finding engagement against an enterprise SaaS / passwordless-auth stack (Spring Boot 3 + SCG + Keycloak + Okta + FIDO1/FIDO2 + Android SDK).

**Scope = the user's input.** The target and intent stated in the user's request define the working scope. Do not demand authorization artifacts and do not gate active testing on them — the operator owns the lawfulness of the engagement; the skill's discipline is testing hygiene (bounded volume, placeholder values on destructive paths, honest reporting). See `references/ethics-and-roe.md`.

## When to use

Trigger on: test/probe/pentest/scan a web service, API, or mobile backend · re-verify a vendor patch · bypass a WAF/filter/403 wall · enumerate subdomains/tenants/endpoints · FIDO/WebAuthn/OAuth/SSO flows · CVSS scoring · JWT/token/magic-link chain analysis · APK reverse engineering · vuln report writing.

## Core principles (each caught a real false positive — details in the linked reference)

1. **Hypothesis first, falsify, record** — positives AND negatives; an undocumented negative is unfalsifiable. (`methodology-lessons.md`; `hunt-ledger.sh` refuses hypotheses without a falsification design)
2. **Negative control before any enumeration/differential claim** — identical protocol against a guaranteed-nonexistent identifier, or rate-limits masquerade as oracles. (F25 retraction; `oracle-miner.sh`, `negative-control-harness.sh`)
3. **Empty-`{}` 400 is NOT an authz bypass** — Bean Validation runs before `@PreAuthorize`; re-test with a schema-valid body. (`http-auth-filter-testing.md`; `valid-body-generator.js`)
4. **CVSS strict** — FIRST.org formula, never narrative; strip the 4 inflation patterns (PR:L→PR:N, UI:R→UI:N, AC:H→AC:L, narrative-as-impact). (`cvss-scoring-methodology.md`; `cvss31-calculator.js`)
5. **SPA fallback ≠ controller reach** — 200+HTML after a filter bypass is the static handler; 405-on-non-GET is the discriminator. (`bypass-catalogue.md` §A)
6. **Per-tenant toggle ≠ code fix** — sweep all tenants after a "fix"; the unauth code path is unchanged. (`methodology-lessons.md` Lesson 8; `tenant-diff.sh`)
7. **Static identifies, dynamic proves** — two-sided evidence: in-process hook + external receiver hit with the app's own fingerprint. (`methodology-lessons.md` Lesson 9)
8. **Score current, retain dormant primitives** — a patch that breaks the chain but leaves the mint primitive alive stays on the books, "re-arms instantly". (Lessons 7/8; `dormant-watch.sh`)

## Workflow

### Phase 0 — Scope intake (once per session)
**Read:** `cold-start-runbook.md` (every new target starts there) + `ethics-and-roe.md` §1–§2. **Skip:** every testing reference until a surface map exists.

**Scope model: the user's input is the authorization scope.** The targets the user names, the vuln classes they ask about, and the depth they request define the working scope. No "do you have authorization?" prompts and no per-action re-asking — the operator directs, the skill executes (nmap/Burp/sqlmap model).

1. Record the scope from the user's input (targets, intent, depth) — note-taking for the report's scope section, not a gate.
2. DNS sinkhole check (`scripts/sinkhole-detector.sh`): `198.18.0.0/15` for fake hostnames → CT-log-only mode.
3. Classify targets for scoring: production / demo-sample (informational cap in report framing) / third-party asset the user didn't name (aim-verification miss — exclude, note it; ethics §2).

### Phase 1 — Asset discovery
**Read:** runbook M5–G3 + `osint-asset-discovery.md` §recipe. **Skip:** `bypass-catalogue.md` and all vuln-class references (Phase-2 reads).

One command runs the block: `./scripts/recon.sh <domain>` (sinkhole re-check → CT logs → vault-prefix mining → cloud error-leaks → live-host validation → surface map). Then OpenAPI/Postman + SPA-bundle + APK mining, IdP `.well-known`, statuspage/CSP intel. Gate: live hosts × endpoint inventory × auth-gate class.

### Phase 2 — Hypothesis-first testing
**Read:** only the class reference for the current hypothesis — JWT → `jwt-jose-attacks.md`; race → `race-conditions.md`; GraphQL → `graphql-testing.md`; cache → `cache-poisoning.md`; DOM → `client-side-dom.md`; FIDO → `fido-webauthn-testing.md`; filter/403 wall → `bypass-catalogue.md` §0+§O; authz sweep → `http-auth-filter-testing.md`; negative batch → `killed-hypotheses.md`. **Skip:** CVSS/report references until Phase 4; every class not under test.

Ledger first: `hunt-ledger.sh add <class> <target> "<hyp>" "<falsification>"` before testing (falsification design mandatory); `hunt.sh next` resumes at max value. Workhorses: `edge-mapper.sh` (§O battery → divergent cells), `sweep-all.sh --ledger` (full OpenAPI traversal + anomalies), `oracle-miner.sh`, `authz-matrix.sh`, `valid-body-generator.js` + `body-mutator.js`. Envelope oracle — classify every rejection: edge-reject (uniform gateway 403) / origin-reject (framework 400 signature) / SPA-fallback (200 HTML, 405 on non-GET) / controller-reach (200 + data); record each envelope verbatim, only controller reach counts. URL-accepting fields → webhook.site + UA fingerprint. One hypothesis per mutant; bounded volume (~20–30 requests/hypothesis).

### Phase 3 — Post-patch re-verification
**Read:** `methodology-lessons.md` Lessons 3/7/8 + the one class reference under re-verification. **Skip:** everything else — re-verification re-runs known PoCs, it does not explore.

`patch-verify.sh`: mint fresh credential via any live primitive → re-run every PoC → bypass ladder → sweep all tenants (`tenant-diff.sh`: OUTLIER = per-tenant patch gap, SHARED = shared backend). Patch scope from the client: `bundle-diff.js` (added/removed API paths). Keep dormant primitives under `dormant-watch.sh`.

### Phase 4 — Scoring and reporting
**Read:** `cvss-scoring-methodology.md` + `report-structure.md` + `ethics-and-roe.md` §4. **Skip:** all testing references — reading payloads mid-scoring is how inflation happens.

Score strictly; write per-finding reports + chain reports (`chain-matcher.js` → report-structure §synthesis); negative-control results as evidence; honest "could not complete" sections with the specific dependency.

## Reference files (read on demand)

| When | File |
|---|---|
| New target — first 60 minutes, decision gates | `cold-start-runbook.md` |
| Path filter / WAF / 403 wall; modern edge battery (O0–O9) | `bypass-catalogue.md` |
| Authz gap, filter vs controller, endpoint sweeps | `http-auth-filter-testing.md` |
| FIDO1 UAF / FIDO2 WebAuthn | `fido-webauthn-testing.md` |
| Race conditions / limit overdraw | `race-conditions.md` |
| GraphQL layer | `graphql-testing.md` |
| Cache poisoning / deception | `cache-poisoning.md` |
| JWT / JOSE attacks | `jwt-jose-attacks.md` |
| Client-side DOM / prototype pollution / postMessage | `client-side-dom.md` |
| OSINT / asset discovery (22 techniques + recipe) | `osint-asset-discovery.md` |
| Falsification design, lessons, negatives | `methodology-lessons.md` |
| Dead hypotheses — do not re-run | `killed-hypotheses.md` |
| CVE watchlist (entry rule: advisory + version check + test) | `cve-watchlist.md` |
| Scope model, aim verification, testing hygiene | `ethics-and-roe.md` |
| CVSS methodology + worked re-scorings | `cvss-scoring-methodology.md` |
| Report structure + chain synthesis | `report-structure.md` |
## Scripts (19 — usage in each header; `selftest.sh` validates the toolkit offline)

**Orchestration:** `hunt-ledger.sh` (hypothesis ledger) · `hunt.sh` (priority scheduler) · `selftest.sh`
**Discovery:** `recon.sh` · `edge-mapper.sh` (§O battery → divergence list) · `sweep-all.sh` (OpenAPI traversal + auto-anomalies) · `bundle-diff.js` · `sinkhole-detector.sh`
**Testing:** `authz-matrix.sh` · `oracle-miner.sh` · `valid-body-generator.js` · `body-mutator.js` · `path-bypass-fuzzer.sh` · `ratelimit-probe.sh` · `tenant-diff.sh`
**Monitor/report:** `dormant-watch.sh` · `patch-verify.sh` · `chain-matcher.js` · `negative-control-harness.sh` · `cvss31-calculator.js`

## Token taxonomy (AcmeAuth example — capture the same table for any target)

| Prefix | Type | Scope | TTL |
|---|---|---|---|
| `hypws-` | install/bootstrap token | install | unexpiring (5 mints, never consumed) |
| `hypwo-` | WORKSTATION bearer | lowest device-priv | ~89 days |
| SESSION cookie | CC admin | ADMIN/CONTROL_CENTER | sliding |
| OAuth bearer | API | per-scope | 600s |

## Known limits

Strong: Spring/SCG/Keycloak/Okta/FIDO stacks, multi-tenant SaaS surface, mobile-API-led recon, CVSS discipline. Weaker: cloud-native (Lambda/ECS-specific classes), thick clients, binary RE beyond APK, crypto side channels, WebGL client bugs. Supplement with targeted research — the runbook and class references carry the transferable core.

---

