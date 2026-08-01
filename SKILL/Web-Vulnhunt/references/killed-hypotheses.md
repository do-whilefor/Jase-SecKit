# Killed Hypotheses — What Did NOT Work

Repeating dead work is the most expensive failure mode in vuln research. This file catalogues the 12+ closed hypotheses from the AcmeAuth engagement so future work on similar stacks (Spring Boot + SCG + Keycloak + Okta + FIDO) skips them.

For each: the hypothesis, the exact test, the result, and a one-line takeaway.

---

## B1 — RADIUS service exposure (backdoor usernames)

**Hypothesis.** The OSINT-leaked AcmeAuth RADIUS config (`<vendor-employee>/public` repo) revealed admin port `9077`, default shared secret `"acmeauth"`, and load-test backdoor usernames `test.radius.{accept,reject}.<sleep-ms>@acmeauth.example`. The RADIUS service might be reachable from the public internet with these defaults.

**Test.** TCP connect to ports 9077/9700/1812/1813/2083 on AcmeAuth hosts. Auth attempt with `test.radius.accept.5000@acmeauth.example` + shared secret `"acmeauth"`.

**Result.** Ports accept TCP (LB-fronted) but no RADIUS protocol response. Backdoor usernames do not short-circuit the ControlCenter call from public internet.

**Takeaway.** RADIUS admin ports are LB-fronted but the LB doesn't speak RADIUS — internal-only protocol.

---

## B2 — Pritunl VPN CVE surface

**Hypothesis.** `vpn-pritunl.acmeauth.example` runs Pritunl, which has CVE-2021-44547 (auth bypass) and CVE-2023-33831 (unauth reset).

**Test.** All `/api/*` paths on `vpn-pritunl.acmeauth.example`. CVE-2021-44547 paths (`/api/server`, `/api/user`). CVE-2023-33831 paths (`/reset/...`, `/password/reset`).

**Result.** All 404. No Pritunl API surface exposed.

**Takeaway.** Either patched past the CVE range or API stripped at the edge.

---

## B3 — `/sample/*` namespace

**Hypothesis.** The Sample Bank sample app on `demo.acmeauth.example/sample/*` might expose additional controllers.

**Test.** Every subpath under `/sample/`: `/sample/admin`, `/sample/login`, `/sample/fido2/oob/register`, `/sample/api`.

**Result.** All return DispatcherServlet "no mapping" 400. No controller mounted at `/sample/` (except on demo.acmeauth.example which is scope-capped).

**Takeaway.** `/sample/` is a Spring Boot routed namespace with no controllers — confirmed via DispatcherServlet error signature.

---

## B4 — CVE-2023-1837 legacy API auth bypass

**Hypothesis.** AcmeAuth Legacy API (`/rp/api/versioned/rpUser/*`, `/rp/wsapi/*`) has auth bypass in versions <8.0 per CVE-2023-1837.

**Test.** 15 endpoints under `/rp/api/versioned/rpUser/*` and `/rp/wsapi/*`. `/AcmeAuth/rest/conformance/{Get,Send/Reg,Send/Auth}`.

**Result.** All 401. `/AcmeAuth/rest/conformance/*` returns only FIDO2 conformance test scaffolding.

**Takeaway.** All tenants run ≥11.1.0 — vuln class N/A. The conformance endpoint is testing scaffolding, not a vuln sink.

---

## B5 — Path-confusion bypass vs admin sinks

**Hypothesis.** One of the standard path-confusion variants (matrix params, double-encode, case, suffix) might bypass the auth filter and reach an admin sink.

**Test.** 11 path variants against admin endpoints (`/cc/api/email/send/template`, `/cc/api/jobs/scheduler/*`).

**Result.** All reach Spring generic 400 (malformed path) — never the controller.

**Takeaway.** SCG-path-bypass + Spring-rejects-malformed is the two-layer defense. `..;/` traversal rarely yields data even when it reaches the backend.

---

## B6 — CVE-2026-2414 AcmeAuth IDOR variant hunting

**Hypothesis.** AcmeAuth CVE-2026-2414 (IDOR CVSS 9.8 CWE-639) suggests missing-`@PreAuthorize` is a known bug class in this codebase. Variant hunting might find more.

**Test.** 453-path GET + 342-path write-method scan across all non-idp `/cc/api/*` controllers, all `{path-param}` substituted.

**Result.** 0 endpoints returned 200 with the test token. No missing-`@PreAuthorize` defect reachable without an existing session.

**Takeaway.** The IdP controller cluster (F5/F7/F9) was the isolated miss; the rest of `/cc/api/*` is properly annotated.

---

## B7 — OAuth token exchange

**Hypothesis.** `/rp/token/endpoint/exchange/*` might accept alternative grant types that bypass intended scoping.

**Test.** All grant type variants under `/rp/token/endpoint/exchange/*`.

**Result.** All return `InvalidTokenExchangeRequest` (errorCode 1201047).

**Takeaway.** Token exchange is strict; client_assertion signed JWT is the only path and it requires the AcmeAuth-issued app client private key.

---

## B8 — HTTP request smuggling

**Hypothesis.** Edge nginx might be vulnerable to CL.TE, TE.CL, TE.TE obfuscation, or CL-CL duplicate.

**Test.** Raw TLS socket requests with each smuggling variant against `/sample` and CC hosts.

**Result.** Edge nginx canonicalizes/rejects every ambiguous-header variant before the backend.

**Takeaway.** nginx canonicalizes Transfer-Encoding. No smuggling primitive.

---

## B9 — `/logs/binary` multipart endpoint

**Hypothesis.** `/logs/binary` is a multipart endpoint that might have a deserialization sink.

**Test.** Various multipart bodies.

**Result.** Dominant 500 regardless of body; handler bug not sink.

**Takeaway.** 500 is a server-side exception, not a sink confirmation. Unverifiable from outside.

---

## B10 — `/rp/api/oob/*` device-auth namespace

**Hypothesis.** The `/rp/api/oob/*` namespace might have unauthenticated endpoints.

**Test.** All 25+ subpaths.

**Result.** All 401.

**Takeaway.** Device-auth namespace is fully authenticated.

---

## B11 — v11.5.0 differential

**Hypothesis.** v11.5.0 (`sampleapp.dev.acmeauth.example`) moved FIDO2 endpoints to `/rp/fido2/*` — those new endpoints might have new bugs.

**Test.** All `/rp/fido2/*` subpaths.

**Result.** All return unmapped 400.

**Takeaway.** v11.5.0 is a newer branch where the legacy FIDO1 endpoints are removed (`/rp/fido/get` → 404). Useful for version-differential reasoning but not a vuln sink.

---

## B12 — `enhancements.acmeauth.example` Rails portal

**Hypothesis.** `enhancements.acmeauth.example` is a Rails portal with open signup — might have privilege escalation.

**Test.** `POST /portal_users` (signup); `POST /portal_session` (login); authenticated paths `/admin`, `/rails/info/routes`, `/graphql`.

**Result.** Signup `POST /portal_users` → **422 "invalid params"** (open signup confirmed by the validation error, not by a 201); login `POST /portal_session` → **302** redirect to authenticated landing; `/admin`, `/rails/info/routes`, `/graphql` all returned no privileged surface (404 or Rails default). No privilege-escalation primitive.

**Takeaway.** Rails portal is a feature-tracker (Canny-style), not a security-sensitive surface. The falsifiable signature is the 422-on-signup + 302-on-session shape, not "open signup confirmed" in the abstract.

---

## Other killed hypotheses (beyond B1-B12)

### Spring Boot `/env` exposure
**Hypothesis.** Standard Spring Boot Actuator `/env` might leak config.
**Test.** `/env` + 20 normalization variants (case, trailing, encoded, matrix, traversal).
**Result.** All variants return **HTTP 403, 119 bytes, body `{"detail":"Ensure the URL is valid","status":403,"title":"Access forbidden","type":"InternalServerErrorException.html"}`** — the canonical WAF path-filter rejection. (The same body signature fires on every path-filtered route — see http-auth-filter-testing.md §3.)
**Takeaway.** WAF ruleset is actively maintained, not naive regex — it normalizes case + encoding + matrix params before the path reaches Spring.

### SCG actuator RCE (CVE-2022-22947)
**Hypothesis.** `/actuator/gateway/routes` + `/refresh` might allow RCE.
**Test.** 20 sibling actuator endpoints + 20 normalization bypasses + X-Forwarded headers.
**Result.** All return **HTTP 403, 119 bytes, body `{"detail":"Ensure the URL is valid","status":403,"title":"Access forbidden","type":"InternalServerErrorException.html"}`** at the WAF; `/cc/..;/actuator` reaches Spring but Spring returns its own 400 (malformed path).
**Takeaway.** `/cc/..;/actuator` bypasses the SCG block but Spring rejects the malformed path — two-layer defense. The WAF 403 body signature is the same `/InternalServerErrorException.html` envelope as Spring Boot `/env`.

### Spring Cloud Function SpEL (CVE-2022-22963)
**Hypothesis.** `/functionRouter` with `spring.cloud.function.routing-expression` header might eval SpEL.
**Test.** Standard PoC.
**Result.** 403 from ALB (`awselb/2.0`).
**Takeaway.** Request blocked before backend.

### Spring4Shell (CVE-2022-22965)
**Hypothesis.** `class.module.classLoader...` headers on `/login` might achieve RCE.
**Test.** Standard payload (`class.module.classLoader.resources.dircontext.docBase=xxx`).
**Result.** **HTTP 200, response body unchanged** from the no-payload baseline — no parameter reflection, no class-loader binding error, no log path traversal indicator.
**Takeaway.** No class-binding DataBinder surface on `/login`. The falsifiable signature is the byte-identical 200 response vs. baseline (capture both for diff).

### Spring Data RCE (CVE-2018-1273)
**Hypothesis.** SpEL in form parameter might eval.
**Test.** Standard payload.
**Result.** 302 → accessDenied.
**Takeaway.** Either patched or no Spring Data form-binding surface.

### CORS reflection
**Hypothesis.** Reflected Origin might yield cross-origin credentialed reads.
**Test.** `Origin: https://evil.example.com` on `/cc/basic/token`, `/cc/ui/token`, `/cc/ui/serverconfig/global`.
**Result.** No ACAO/ACAC reflection.
**Takeaway.** Not vulnerable.

### Content-Type / XXE
**Hypothesis.** XML/text-yaml/cbor CTs on `/cc/api/email/send/template` might trigger XXE.
**Test.** Each CT in turn.
**Result.** 400 / 415.
**Takeaway.** No XXE surface.

### Direct OPA REST
**Hypothesis.** `/v1/data`, `/v1/query`, `/v1/compile`, `/v1/config` might be exposed.
**Test.** Each in turn.
**Result.** Spring 400 (wildcard route, not OPA).
**Takeaway.** Not actual OPA endpoints.

### JAX-RS/CXF
**Hypothesis.** `/services`, `/cxf`, `/cc/services` might expose JAX-RS/CXF.
**Test.** Each in turn.
**Result.** 403 / 302.
**Takeaway.** Not exposed.

### Customer-tenant lateral movement
**Hypothesis.** F8 install token from tenant-001 might work cross-tenant on customer hosts.
**Test.** tenant-001 install token → `portal.acmeauth.example`, customer-named tenants.
**Result.** 401 `"Cannot find hypws-41"` (tenant-bound).
**Takeaway.** **Refused further testing on customer tenants** — out-of-RoE. Technical isolation matches RoE intent.

---

## Methodology takeaway

Every entry above is a **closed hypothesis with documented evidence**. This is what "hard goal 0/3" looks like in practice — not "I couldn't find it" (unfalsifiable) but "I tried B1-B12 + 8 additional closed paths with these specific payloads and here is the rejection evidence" (falsifiable, auditable, and reusable).

For your next engagement on a similar stack:
1. Skim this list FIRST. If your target is Spring Boot + SCG + Keycloak + FIDO, many of these will save you hours.
2. When you close a hypothesis, add it to your own killed-hypotheses file with the same structure.
3. Share the killed-hypotheses file with triage — it shows thoroughness and prevents "did you try X?" back-and-forth.
