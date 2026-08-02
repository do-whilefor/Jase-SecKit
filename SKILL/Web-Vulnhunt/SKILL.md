---
name: Web-Vulnhunt
description: Authorized security testing methodology for web apps, APIs, multi-tenant SaaS, Spring Boot / Cloud Gateway stacks, FIDO/WebAuthn passwordless auth, mobile backends, and OAuth/SSO integrations. Use whenever the user asks to test, probe, scan, find vulnerabilities in, or pentest any web service — including bug bounty engagements, authorized pentests, CTF challenges, post-patch re-verification, CVSS scoring, subdomain/asset discovery, WAF/auth-filter bypass, **authorization bypass / IDOR / broken access control / missing @PreAuthorize / privilege escalation** testing, FIDO2/UAF testing, token-chain analysis, or writing vulnerability reports. Also triggers on the words "AcmeAuth", "Keycloak", "Okta", "PingFederate", "Auth0", or any passwordless-auth vendor. This is a defensive skill for authorized work only — always confirm scope before any active test.
---

# Web Vulnerability-Hunting Methodology

A field-tested methodology for authorized vuln research on enterprise SaaS / API / passwordless-auth targets. Distilled from a 13-session, 30+ finding engagement against AcmeAuth Control Center (Spring Boot 3 + Spring Cloud Gateway + Keycloak + Okta + FIDO1/FIDO2 + Android SDK).

**Authorized use only.** Confirm scope (program policy, RoE, written permission) before any active test. Refuse out-of-scope work and document the refusal with rationale. See `references/ethics-and-roe.md`.

---

## When to use this skill

Trigger when the user asks to:
- Test / probe / pentest / scan / hunt vulnerabilities in a web service, API, or mobile backend
- Re-verify a finding after a vendor patch
- Bypass a WAF, auth filter, path filter, or 403/401 wall
- Enumerate subdomains, assets, customer tenants, or API endpoints
- Test FIDO1 UAF, FIDO2/WebAuthn, OAuth, SAML, OIDC, Keycloak, Okta, or other passwordless/SSO flows
- Score CVSS for a finding (especially: "is this really High?")
- Write a vulnerability report for HackerOne / Bugcrowd / internal
- Analyze a JWT, session token, magic-link, or install-token chain
- Reverse-engineer a mobile APK for endpoints / SSL-pinning / SSRF surface

---

## Core principles (load-bearing rules)

These are the rules that, when skipped, produced false positives or overstated claims in the source engagement. Re-read before any submission.

### 1. Hypothesis first, falsify, record — every time
For every test: state the hypothesis, design the falsification, run it, record the result (positive OR negative). Negatives are evidence. An undocumented "I couldn't find it" is unfalsifiable; an documented "B1-B12: tried X, got Y" is auditable and reusable. See `references/killed-hypotheses.md`.

### 2. Negative control is mandatory for any enumeration/differential claim
Before claiming an oracle distinguishes existing vs non-existing identifiers, run the identical protocol against a freshly-generated random identifier guaranteed not to exist (e.g. `zzznonexistent<timestamp>@nowhere.com`). Without the control, rate-limit counters, IP reputation, and lockout cooldowns masquerade as deterministic differentials. **This rule caught the F25 PingFederate false positive** (random nonexistent username also flipped to `account_locked`). Run `scripts/negative-control-harness.sh`.

### 3. Empty body `{}` returning 400 is NOT an authz bypass
Bean Validation runs BEFORE `@PreAuthorize`. A 400 on a malformed body says nothing about authorization. For every 400 in an authz sweep: look up the OpenAPI schema, craft a valid body, re-test. Only `200 with data` or `200 with operation-confirmed` counts as bypassed. **This rule prevented 130+ false positives** in the F7 sweep. See `references/http-auth-filter-testing.md` §1.

### 4. CVSS strict — never score against narrative
Score against the FIRST.org 3.1 spec formula, not the story. Four common inflation patterns to strip: PR:L mis-scored as PR:N, UI:R as UI:N, AC:H as AC:L, narrative impact credited as direct C/I/A. CVSS does NOT credit "prerequisite for another vuln." Run `scripts/cvss31-calculator.js`. See `references/cvss-scoring-methodology.md`.

### 5. SPA fallback ≠ controller reach
A `200` with `text/html` after a path-filter bypass usually means the request fell through to the SPA static handler, not the controller. Spring MVC routing is case-sensitive; a case-variant that bypasses a case-sensitive WAF filter still misses `@RequestMapping`. Discriminating signal: SPA fallback serves `index.html` and returns `405` on non-GET. See `references/bypass-catalogue.md` §A.

### 6. A per-tenant toggle is not a code fix
If a vendor "fixes" a vuln by disabling it per-tenant, sweep ALL tenants. A 200-with-`status:failed` mitigation means the unauthenticated code path (CWE-306) is unchanged — only the downstream feature is gated. **F13 stayed live on 3 of 11 tenants** after the "fix." See `references/methodology-lessons.md` Lesson 8.

### 7. Static analysis identifies; dynamic verification proves
"Dynamic verified" = closed loop with two-sided evidence: (a) in-process hook showing the vulnerable code constructed the request, AND (b) an external receiver (webhook.site) showing the request arrived with a decisive app fingerprint (e.g. the app's own User-Agent). For mobile: hook OkHttp via Frida and invoke the vulnerable method directly. See `references/methodology-lessons.md` Lesson 9.

### 8. Persistence primitive vs dormant chain — score current, retain both
When a patch breaks a chain but leaves the issuance primitive intact (e.g. install-token infinite mint), do NOT close the primitive. Score at current CVSS (downstream impact nil = lower score) but retain as a dormant persistence primitive with "re-arms instantly if any future gap appears" note. See `references/methodology-lessons.md` Lesson 7.

---

## The workflow

### Phase 0 — Scope and integrity gate (run once per session, re-confirm per new target class)

**Authorization trust model.** The skill trusts a single explicit authorization statement from the user at session start ("I have authorization for `<target>` under `<program/contract>`") and does NOT re-litigate it on every action. The gate below runs **once per session**, then per-target-class re-confirmation only when the target type changes (e.g. "demo tenant" → "production tenant", "owned lab" → "third-party system"). What this gate does NOT relax: customer-tenant refusal, destructive-endpoint placeholder rule, credential Tier-3 prohibition, and the no-remote-push rule. Those are absolute, not workflow noise.

1. **Confirm authorization (once per session, then on scope expansion).** If the user has declared authorization for the target, record it and proceed without re-asking for the same target class. Re-confirm only when: (a) the target changes to a class not covered by the original declaration, (b) the user directs testing at an asset type that materially changes risk (production vs. demo, vendor-owned vs. customer-hosted), (c) the action crosses from read-only to state-changing.
2. **Identify out-of-RoE assets and refuse them with documented rationale** (customer-named tenants, production user data, third-party systems). This is non-negotiable regardless of authorization framing — a wildcard program scope covers vendor-owned assets, not customer data hosted on vendor infrastructure.
3. **Detect DNS sinkhole:** resolve a guaranteed-fake hostname (`totallymadeup.<domain>`). If it returns `198.18.0.0/15` instead of NXDOMAIN, you are behind an RFC 2544 sinkhole resolver — pivot to CT-log-only enumeration. Run `scripts/sinkhole-detector.sh`.
4. **Classify each target:** (a) in-scope production, (b) in-scope demo/sample (cap at informational unless explicitly authorized higher), (c) out-of-RoE customer (refuse, document the refusal).

### Phase 1 — Asset discovery and attack-surface mapping
- **CT log enumeration** (primary): `curl 'https://crt.sh/?q=%25.<domain>&output=json'`. Fallback chain when crt.sh is down: DNS brute-force → sitemap parse → statuspage mining → CloudFront/S3 error-leak analysis.
- **CT vault-prefix enumeration** (multi-tenant SaaS): regex `/^vault-([^.]+)\.(\d{12})\.<domain>$/` extracts customer name + AWS account ID from cert SANs.
- **Cloud account-ID discovery**: `curl https://assets.<domain>/` — S3 MRAP AccessDenied XML leaks STS ARN with AWS account + IAM role name.
- **Mobile APK reverse**: `apkeep -a <package> -p APKPure; jadx -d out <pkg>.apk; apktool d <pkg>.apk`. Mine `AcmeAuthApiEndpoints.java`, `RetrofitGenerator.java` (SSL-pin logic), `strings.xml` (Firebase config).
- **OpenAPI/Postman discovery**: `<docs subdomain>` often CNAMEs `phs.getpostman.com`. Extract all state-changing endpoints (POST/PUT/PATCH/DELETE) and bucket by controller namespace.
- **SPA bundle mining**: download `loggedIn.js` / main bundle, regex-extract all `/api/*` paths.
- **Third-party intel**: Sentry DSN from CSP `report-uri`, Greenhouse ATS API, statuspage incident history, Keycloak `/auth/realms/*/.well-known/openid-configuration` realm enumeration.
- See `references/osint-asset-discovery.md` for the full 22-technique playbook.

### Phase 2 — Hypothesis-first testing
For each candidate sink, run this loop:
1. **Identify the auth gate** (filter? `@PreAuthorize`? scope enum?) via the response-envelope oracle:
   - `{"detail":"Ensure the URL is valid"...}` + `InternalServerErrorException.html` → WAF/path filter
   - `AccessDeniedException` → Spring Security controller authz
   - `InvalidJSONRequestProblem` / `ConstraintViolationException.html` → reached business logic (authz-gap candidate — retest with valid body)
   - SPA HTML `Error | <app>` → fell through to static handler
2. **For each URL-accepting field** (`jwksUrl`, `invocationEndpoint`, `acmeauthServerUrl`, `proxies[].host`, `webhookUrl`): send a `webhook.site` URL, check inbound UA — Java/Go/AWS-EventBridge identify distinct code paths needing independent patching.
3. **For each enumeration/differential claim**: run negative control before claiming the oracle.
4. **For each filter bypass**: run the full ordered ladder (`scripts/path-bypass-fuzzer.sh`) and verify controller-reach vs SPA-fallback.
5. **For each authz-gap candidate**: run token × endpoint namespace matrix (`scripts/authz-matrix.sh`).
6. **For mobile static findings**: close the Frida loop before claiming exploitability.

### Phase 3 — Post-patch re-verification
When a vendor reports a patch, never assume closure:
1. Mint a fresh credential via any still-live persistence primitive (proves the auth surface itself wasn't touched).
2. Re-run every original PoC; record before/after status codes.
3. Use a deliberately-nonexistent target value (`ZZFAKE` provider, `nobody@xyz.com`) for destructive endpoints to prove zero state change.
4. Attempt 20+ path-normalization bypass variants.
5. Distinguish SPA-fallback (200 + `text/html`) from controller reach (200 + JSON data).
6. Infer patch mechanism (path filter vs annotation) from response uniformity — this determines which adjacent endpoints are still exposed.
7. Sweep all tenants — AcmeAuth-style vendors apply fixes per-tenant inconsistently.
- Run `scripts/patch-verify.sh`.

### Phase 4 — Scoring and reporting
- Score CVSS strictly (`scripts/cvss31-calculator.js`). Strip the 4 inflation patterns.
- Write the report following the canonical structure. See `references/report-structure.md`.
- Cross-tenant patch-state matrix as a table.
- Negative control result as evidence.
- Two-sided dynamic verification (hook + external receiver) for mobile findings.
- Honest "could not complete" sections (e.g. "credential registration blocked — requires real FIDO1 authenticator") with the specific dependency that blocked escalation.

---

## Reference files (read on demand)

| Read this when… | File |
|---|---|
| Testing a path filter / WAF / 403 wall | `references/bypass-catalogue.md` |
| Designing the falsification test or wondering "what did we learn last time" | `references/methodology-lessons.md` |
| Enumerating subdomains / customer tenants / AWS account IDs / mobile endpoints | `references/osint-asset-discovery.md` |
| Testing an authz gap, distinguishing filter vs controller, sweeping endpoints | `references/http-auth-filter-testing.md` |
| Testing FIDO1 UAF or FIDO2/WebAuthn (CBOR PoC, attestation/assertion flows) | `references/fido-webauthn-testing.md` |
| Scoring CVSS or sanity-checking a "High" rating | `references/cvss-scoring-methodology.md` |
| Avoiding repeats of dead hypotheses (CVEs that didn't apply, techniques that failed) | `references/killed-hypotheses.md` |
| Deciding whether to refuse an action (RoE, customer tenants, integrity corrections) | `references/ethics-and-roe.md` |
| Writing the actual report file | `references/report-structure.md` |
| CVEs that *might* apply but weren't attempted yet | `references/cve-watchlist.md` |

---

## Reusable scripts

| Script | When to run |
|---|---|
| `scripts/cvss31-calculator.js` | Score any finding. Takes a vector string, prints score + severity + computation. |
| `scripts/path-bypass-fuzzer.sh` | Test a patched/filtered endpoint against the full 20+ variant ladder. Buckets results. |
| `scripts/negative-control-harness.sh` | Auto positive+negative control for any enumeration/differential claim. |
| `scripts/authz-matrix.sh` | Token × endpoint namespace matrix to find missing-`@PreAuthorize` gaps. |
| `scripts/patch-verify.sh` | Post-patch re-verification protocol (mint fresh token → re-run PoC → bypass ladder → tenant sweep). |
| `scripts/sinkhole-detector.sh` | Detect RFC 2544 DNS sinkhole; recommend CT-log-only fallback. |

---

## Target-class quick notes

### Spring Boot 3 + Spring Cloud Gateway + WAF (the AcmeAuth pattern)
- Edge returns `{"detail":"Ensure the URL is valid","status":403,"type":"InternalServerErrorException.html"}` when the path filter blocks. Defense-in-depth: WAF normalizes case, comments, versioned MySQL hints, encoding, matrix params.
- Filter is case-sensitive but Spring MVC is case-sensitive too — case variants bypass the filter and fall through to SPA. Non-exploitable.
- `/actuator/gateway/*` blocked at SCG; `/cc/..;/actuator` bypasses SCG block but Spring rejects malformed path.
- Jackson default typing off; parameterized JPA everywhere; no template engine on unauth response path. So SQLi/SSTI/SpEL/Jackson-deser universally negative on the unauth perimeter.

### FIDO2 / WebAuthn
- Two unauthenticated ceremonies: `/fido2/attestation/options` (issues challenge, leaks `excludeCredentials`) and `/fido2/attestation/result` (accepts forged `fmt:"none"` attestation).
- Size oracle: valid user → ~11,740-byte response with 130+ credential IDs; non-existent → ~245 bytes. **47.9× size amplification.**
- `fmt:"none"` requires no attestation chain — server accepts self-attested credential with empty `attStmt`. See `references/fido-webauthn-testing.md` for the CBOR PoC.

### FIDO1 UAF (legacy)
- `/rp/fido/get` accepts `op=Reg|Auth|Dereg` unauthenticated for any `userName`.
- `sessionId` fully client-controlled and reflected verbatim → session fixation.
- `op=Auth` always throws uncaught 500 `InternalServerErrorException` → state-pollution oracle + DoS amplifier.
- `/rp/fido/send/reg` strictly validates FIDO1 TLV → credential-completion blocked without real authenticator. Caps severity at High, not Critical.

### Multi-tenant SaaS
- AcmeAuth-owned test tenants vs customer-named tenants:AcmeAuth-owned = `<word>.cdn.acmeauth.example` test tenants + `<word>.acmeauth.example` corp. Customer = recognizable brand names (`<customer>`, `<customer>`, `<customer>`, `<customer>`) + `vault-<customer>.<aws-id>.acmeauth.example` prefix.
- Customer tenants are out-of-RoE even under a wildcard program scope.
- Cross-tenant DB-sharing detection: identical `/rp/versioned/features` payloads across tenants = shared backend cluster.

### Token taxonomy (AcmeAuth example)
| Prefix | Type | Scope | TTL |
|---|---|---|---|
| `hypws-` | install token | install/bootstrap | unexpiring (5 mints, never consumed) |
| `hypwo-` | WORKSTATION Bearer | lowest device-priv | ~89 days |
| `SESSION` cookie | CC admin | ADMIN/CONTROL_CENTER | sliding (TTL not in corpus — do not propagate uncorroborated) |
| OAuth bearer | API | per-scope | 600s (`oauthBearerTokenTTLSecs`) |

---

## Integrity discipline

- **Exaggeration that survives unverified is worse than honest downgrade.** Re-run dynamic verification on challenge; if the chain cannot complete, downgrade severity and document the correction in a versioned log.
- **For destructive endpoints** always substitute a placeholder (`ZZFAKE`, `nobody`, `0`-prefixed random) — never use a real identifier to "test if DELETE works."
- **Credential validation is tiered, not blanket-prohibited.** A discovered credential that is never validated yields only a "leak" finding; a validated credential proves the full vuln chain. Use this three-tier framework (see `references/methodology-lessons.md` Lesson 11 for the full decision tree):
  - **Tier 1 — Static analysis (default-allowed, no confirmation needed):** decode JWT/OAuth tokens, inspect `claims`/`scope`/`aud`/`exp`/`iss`, extract structure from session cookies, reason about theoretical reachability from token metadata alone. This is analysis, not usage. Do this exhaustively — it is where most chain value lives.
  - **Tier 2 — Dynamic read-only validation (requires explicit per-action user confirmation):** use the credential against **read-only** endpoints (GET only, no state change) within the declared scope to prove it is live and to enumerate its actual reach. Confirm with the user before each distinct endpoint group. Capture the response as evidence. This is what turns "credential leaked" into "credential valid → CVSS justifies I:H".
  - **Tier 3 — State-changing / destructive use (forbidden with real values, always):** write/delete/lateral-movement/persistence operations use placeholder targets (`ZZFAKE` provider, `nobody@xyz.com`, `0`-prefixed random IDs). Never run a real identifier through a destructive path even with confirmation. If the chain requires real destructive proof to close, document the gap honestly rather than execute.
- **Do not reverse token schemas against live auth systems** beyond what's required to confirm the vuln class.
- **Document refusals** with the ethical rationale. "Customer tenant — out-of-RoE even under wildcard scope" is a complete sentence.
- **Never push to remote git.** Per `AGENTS.md` §5.1: local commits only. The user must explicitly authorize any remote push, and push is irreversible (cache, forks, indexes retain content even after force-delete). For git-workflow testing, use local multi-remote setups (`git remote add test /local/path`), never a real remote.

---

## Honesty about this skill's limits

This methodology was distilled from one deep engagement (AcmeAuth). It is strong for:
- Spring Boot / SCG / Keycloak / Okta / FIDO stacks
- Multi-tenant SaaS attack surface
- Mobile-API-led recon (APK reverse + Frida)
- CVSS discipline and false-positive prevention

It is weaker for:
- Cloud-native (Lambda/Step Functions/ECS-specific vuln classes)
- Thick-client / desktop apps
- Binary exploitation / reverse engineering beyond APK
- Crypto-specific flaws (side channels, signature malleability)
- WebGL / browser-specific client-side bugs

For those, supplement with targeted research.
