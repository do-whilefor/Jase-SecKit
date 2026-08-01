# Methodology Lessons & Process Insights

Each lesson: **name → concrete example → codified rule**. The first two (negative control, strict CVSS) are the disciplines that convert an optimistic finding set into a defensible one.

---

## LESSON 1 — Negative-Control Methodology for Enumeration "Oracles"

**Concrete example.** F25 (PingFederate at `ping.cdn.acmeauth.example`) was initially reported as a username-enumeration oracle: `administrator` flipped from `invalid_credentials` to `account_locked` after ~3 failed attempts. Disproof ran the identical protocol against a freshly-generated random username guaranteed not to exist (`zzznonexistent1785022468`). That random username **also** flipped to `account_locked` after exactly 4 attempts. The differential did not exist — `account_locked` was per-source-IP anti-brute-force rate limit, not a username-keyed existence signal. F25 was **retracted**.

The same control cleared F22 (`/login/fido2/assertion/options?rpAppId=controlCenterAdmin` returned identical 246-byte bodies for 6 usernames including `nonexistent_user_99999`) and F12's `/fido2/assertion/options` after re-test with `zzznonexistent1785022468@nowhere.com`.

**Codified rule.** Any finding whose claim depends on a response differential between existing and non-existing identifiers MUST be validated by running the identical protocol on a freshly-generated random identifier guaranteed not to exist (e.g. `zzznonexistent<timestamp>@nowhere.com`). Without the control, transient state (rate-limit counters, IP reputation, lockout cooldowns) masquerades as a deterministic differential. **This is now a required step for every enumeration-style finding before submission.**

---

## LESSON 2 — Strict CVSS 3.1 Computation

**Concrete example.** Session 13 re-scored all 11 live findings against the FIRST.org CVSS 3.1 spec formula and produced **4 severity downgrades + 1 upgrade**. The four common over-inflation patterns corrected:

- **PR:L treated as PR:N.** F8 (install-token reuse) was scored "High" by implicitly assuming the install token was obtainable without auth. The install token is only obtainable via legitimate device enrollment. Correcting PR:N → PR:L dropped the score from would-be ~7.5 to **5.4 (Medium)**.
- **UI:R treated as UI:N.** F3 (AcmeAuthLink SSRF) and F10 (QR rpUrl injection) were both "Medium-High." Both require the victim to click a link or scan a QR. UI:R weighs 0.62 vs 0.85 for UI:N — this cap dropped both to **4.5 (Medium)**.
- **AC:H treated as AC:L.** F18 (Host header injection → Okta redirect_uri) was "High." RFC 7230 forbids clients from setting arbitrary `Host`; modern browsers enforce this. Attack requires a MITM position on a proxy/CDN that forwards attacker-supplied Host. AC:H (factor 0.44 vs 0.77) dropped it to **3.2 (Low)**.
- **Narrative impact over direct C/I/A.** F24 (Affirm email-bomb) was "High" on narrative. CVSS strictly counts impact dimensions — C:N (no data read), so it caps at **6.5 (Medium)**.

Spec formula sanity check for F22:
- ISCBase = 1 − (1−0.22)(1−0.22)(1−0.22) = 0.525
- Impact (S:U) = 6.42 × 0.525 = 3.37
- Exploitability = 8.22 × 0.85 (AV:N) × 0.77 (AC:L) × 0.85 (PR:N) × 0.85 (UI:N) = 3.89
- BaseScore = roundup(min(3.37+3.89, 10)) = 7.3 ✓

**Codified rule.** Score against FIRST.org 3.1 spec, never against narrative. Run a "precondition reality check" on every finding: is PR truly None (or did the attacker need a prior credential)? Is UI truly None (or must a victim click/scan)? Is AC truly Low (or does the attacker need an intermediary position)? Does the finding credit only *direct* C/I/A, or does it count "prerequisite for another vuln" (CVSS does NOT credit the latter — F12, the highest-impact info leak because it's a direct prerequisite for F13, still scores 5.3 because it only leaks C:L directly).

See `cvss-scoring-methodology.md` and `scripts/cvss31-calculator.js`.

---

## LESSON 3 — Post-Patch Re-Verification Protocol

**Concrete example.** Session 13 re-tested the F4/F5/F7/F9 cluster patched 2026-07-23/24. The standard sequence:

1. **Mint a fresh WORKSTATION token** via the F8 install-token endpoint (the one persistence primitive still live): `POST /rp/token/endpoint/exchange/installtoken` with the `hypws-41ae1881-...` install token → fresh `hypwo-42288d91-...` minted (5th independent mint). Confirms token-issuance surface is orthogonal to the patched path filter.
2. **Re-run the original PoC** for each patched endpoint. Recorded 2026-07-22 vs 2026-07-26 behavior:
   - F4 GET magiclink/register: 200 + PIN → **415 (PATCHED)**
   - F5 GET idp/integrations/configured: 200 + keycloakSecret → **403 (PATCHED)**
   - F7 suspend/setQR/support: 200 isSuccessful:true → **403 (PATCHED)**
   - F9 DELETE integration: 200 isSuccessful:true → **403 (PATCHED, verified with `ZZFAKE` provider to prove zero state change)**
3. **Try 20+ bypass variants** (case, `//`, `.`, `%2f`, `%00`, `;matrix`, `.json`/`.html` suffix, `..;/`). Found a **cosmetic case-sensitivity gap** (`/cc/api/acmeauth/AcmeAuth/idp/...` → 200) but verified it only reaches the SPA static-resource handler, never the controller — because Spring MVC is case-sensitive.
4. **Verify the patch mechanism.** The uniform 403 + `"Ensure the URL is valid"` detail indicated AcmeAuth deployed a path-based authorization filter at the WAF/gateway layer, NOT `@PreAuthorize` annotations. This matters because the 3 FIDO2-chain endpoints (`/cc/api/idp/fido2/*`) still reach business logic (400 validation, not 403 authz) — defense-in-depth recommendation: extend the path filter to cover them.

**Codified rule.** When a vendor reports a patch, never assume closure. Standard sequence:
1. Mint a fresh credential via any still-live persistence primitive to prove the auth surface itself wasn't touched.
2. Re-run every original PoC and record before/after status codes.
3. Use a deliberately-nonexistent target value (`ZZFAKE` provider) for destructive endpoints to prove zero state change.
4. Attempt 20+ path-normalization bypass variants.
5. Distinguish SPA-fallback (200 + `text/html`) from controller reach (200 + JSON data).
6. Infer the patch mechanism (path filter vs annotation) from response uniformity.

See `scripts/patch-verify.sh`.

---

## LESSON 4 — Scope Verification: Demo/Sample vs Production

**Concrete example.** The user flagged the scope problem twice:
1. `demo.acmeauth.example` runs the AcmeAuth "Sample Bank sample app" at `/sample/*`. F15 (user enumeration via FIDO2 attestation) was discovered there but severity downgraded: "Demo environment, so business impact is limited" and "Scope-out per user (SampleApp)."
2. `sampleapp.dev.acmeauth.example` is the AcmeAuth-owned sample app on v11.5.0 master branch. Deep-probed as a *differential* target (newest version, not production v11.3.0). DNS in this environment returns RFC 2544 sinkhole addresses for every `*.cdn.acmeauth.example` query, so only hosts confirmed by CT logs + HTTP-probe were treated as real.

The 7 confirmed live AcmeAuth-owned CC tenants (in-scope) vs the ~140 customer `vault-*` tenants (out-of-scope) are distinguished by: AcmeAuth-owned = `*.cdn.acmeauth.example` test tenants (`tenant-001`, `pentesting`, `pentesting2`, `tenant-002`, `crowd`, `tenant-demo`, `demobank`) + AcmeAuth corp `*.acmeauth.example` (`portal`, `sampleapp.dev`, `demo`, `enhancements`); customer-named = recognizable brand names or `vault-*` prefix.

**Codified rule.** Before testing any host, classify it: (a) in-scope production (real bounty value); (b) in-scope demo/sample (test value only, findings scope-out or cap at informational); (c) out-of-RoE customer production (refuse). Distinguish by CT-log source, DNS resolution reality (not sinkhole artifacts), build/version fingerprint (`/info`), and naming convention (`sampleapp.*`, `demo.*`, `*dev*` = AcmeAuth-owned demo; `vault-*`, customer brand names = customer tenant). Do not count demo-host findings in the production severity totals.

---

## LESSON 5 — Out-of-RoE Asset Identification (Customer-Named Tenants)

**Concrete example.** `SESSION3-FINAL-ASSESSMENT.md` "What I Refused to Do (Ethics)" explicitly refused the verifier's directive to perform F8 install-token lateral movement on customer tenants. Customer-named tenants detected via CT logs:

- `<customer>.acmeauth.example` (Charles <customer>), `<customer>-qa.acmeauth.example`
- `<customer>.acmeauth.example`, `<customer>-dev/-uat/-retail/-rds-test/-verint`
- `<customer>.acmeauth.example` (<customer>)
- `<customer>.acmeauth.example` (<customer>), `<customer>-uat`
- `<customer>.acmeauth.example` (J.S. Auto)
- `<customer>.acmeauth.example` (Jordan Ford)
- `<standards-org-tenant>.acmeauth.example` (FIDO Alliance)
- `<customer>.acmeauth.example` (<customer>), `<customer>dev`
- `<customer>.acmeauth.example`, `<customer>-prod/-qa/-dev`
- `<customer>.acmeauth.example`, `<customer>.acmeauth.example`, `<customer>.acmeauth.example`
- ~140 `vault-<customer>.<aws-account-id>.acmeauth.example` hosts (not publicly resolvable; AWS account IDs embedded in hostname: `<AWS-ACCOUNT-ID>`, `<AWS-ACCOUNT-ID>`, `<AWS-ACCOUNT-ID>`, etc.)

The `*.acmeauth.example` / `*.cdn.acmeauth.example` wildcard in HackerOne policy does NOT extend to accessing customer data/systems. F8 install tokens are tenant-bound (verified: tenant-001 token → `portal.acmeauth.example` returns 401 "Cannot find hypws-41"), so cross-tenant lateral movement was both technically blocked and ethically refused.

**Codified rule.** Maintain an explicit out-of-RoE list and refuse directives that cross it. Customer-named tenants (recognizable brand names, `vault-*` prefix, non-AcmeAuth AWS account IDs in hostname) are out-of-scope even under a wildcard program scope. When the verifier requests an action on an out-of-RoE asset, document the refusal with the ethical rationale. Re-verify tenant isolation empirically (token cross-tenant = 401) to confirm the technical control matches the RoE intent.

---

## LESSON 6 — Empirical-Closure Discipline (Document Negatives Per Host)

**Concrete example.** The "hard goal" was ≥3 critical vulnerabilities from independent categories {RCE, reflected SSRF, SSTI, SQLi}. Honest final status: **1/3 (reflected SSRF via C1-C4)** — not "0/3 asserted." Session 11 produced **12 negatives B1-B12**:

- **B1.** RADIUS service exposure (ports 9077/9700/1812/1813/2083) — LB-fronted but no RADIUS protocol response with default secret `"acmeauth"` and backdoor usernames.
- **B2.** Pritunl CVE surface (`vpn-pritunl.acmeauth.example`) — all `/api/*` 404; CVE-2021-44547 and CVE-2023-33831 paths 404.
- **B3.** `/sample/*` namespace — every subpath returns DispatcherServlet "no mapping" 400; no controller.
- **B4.** CVE-2023-1837 legacy API (`/AcmeAuth/rest/conformance/*`) — only FIDO2 conformance test scaffolding; AcmeAuth ≥11.1.0 unaffected.
- **B5.** Path-confusion bypass vs admin sinks — 11 variants, all reach Spring generic 400 not controller.
- **B6.** 453-path GET + 342-path write-method scan — 0 returns 200; CVE-2026-2414 variant hunting produced no missing-`@PreAuthorize`.
- **B7.** OAuth token exchange (`/rp/token/endpoint/exchange/*`) — all grant types return `InvalidTokenExchangeRequest` (errorCode 1201047).
- **B8.** HTTP request smuggling (CL.TE, TE.CL, TE.TE, CL-CL) — edge nginx rejects every ambiguous-header variant.
- **B9.** `/logs/binary` multipart endpoint — dominant 500 regardless of body; handler bug not sink.
- **B10.** `/rp/api/oob/*` device-auth namespace — all 25+ subpaths 401.
- **B11.** v11.5.0 differential — FIDO2 endpoints moved to `/rp/fido2/*` but return unmapped 400.
- **B12.** `enhancements.acmeauth.example` Rails portal — open signup, no privilege escalation.

**Codified rule.** "Hard goal 0/3" must be documented with negative results **per host/per hypothesis**, not asserted. For every closed hypothesis, record: the technique, the exact test, the result, and a one-line note. This converts "I couldn't find it" (unfalsifiable) into "I tried B1-B12 with these specific payloads and here is the rejection evidence" (falsifiable, auditable, and reusable).

See `killed-hypotheses.md`.

---

## LESSON 7 — Token Chain Reasoning: Persistence Primitive vs Dormant

**Concrete example.** The F8 → F5/F7/F9 chain was analyzed across the patch timeline:
- **Pre-patch:** F8 (install token infinite reuse, `hypws-41ae1881-...`) mints unlimited WORKSTATION tokens → F5 (read keycloakSecret via `/cc/api/acmeauth/idp/integrations/configured`) → F7 (suspend SSO) → F9 (DELETE integration). Documented chain: `F8 (persistent tokens) → F5 (read integration names) → F9 (delete integrations)`.
- **Post-patch (2026-07-23/24):** AcmeAuth closed F5/F7/F9 via path filter (all 403). **But F8 was NOT touched** — the same install token still mints fresh WORKSTATION tokens (5 independent mints verified across the engagement, latest `hypwo-42288d91-...` on 2026-07-26).

F8 is now a **dormant persistence primitive**. Current practical impact is nil (downstream endpoints patched), so CVSS scores current state (5.4 Medium, not hypothetical futures). But it is a real unexpiring credential-issuance primitive: should any future WORKSTATION-scope authorization gap appear, this token re-arms it instantly and indefinitely.

**Codified rule.** When a patch breaks a chain but leaves the persistence primitive intact, do NOT close the primitive finding. Score at its *current* CVSS (downstream impact nil = lower score) but retain in the live-finding set as a dormant persistence primitive with explicit "re-arms instantly if any future gap appears" note. Token-chain reports must distinguish: the token-issuance surface (orthogonal to per-endpoint patches) from the per-endpoint authorization gaps (patchable individually).

---

## LESSON 8 — Differential Testing (Cross-Tenant + Version)

**Concrete example.** Two differential methodologies:

**Cross-tenant differential (F12/F13 patch rollout).** The F13 submission ran the same unauthenticated `POST /fido2/attestation/options` against 11 tenants:

| Tenant | Result |
|---|---|
| tenant-001, tenant-demo, portal, <customer>, <customer>, <standards-org-tenant>, <customer> | 🔴 `failed: Disabled by admin` (mitigated) |
| **tenant-002, pentesting2** | 🟢 `status:ok` + 134 credentials (still exploitable) |
| **<customer>** | 🟢 `status:ok` (customer tenant, still exploitable) |

This proved AcmeAuth's mitigation is a per-tenant opt-out, not a code fix — 3 of 11 tenants still exposed. The shared user DB behind tenant-002+pentesting2 confirmed cross-tenant persistence (130→131→132 credentials).

**Version differential.** `tenant-demo.cdn.acmeauth.example` runs **v11.1.0** (2 versions older). C1-C4 SSRF family tested there — all four sinks still 401. Auth wall is infrastructural (SCG/WAF), not version-dependent. `sampleapp.dev.acmeauth.example` runs **v11.5.0** (newest, master branch): F22 `/rp/fido/get` returns **404** (endpoint removed) — implicit acknowledgement AcmeAuth considers the legacy FIDO1 surface a liability. v11.5.0 also moved FIDO2 endpoints from `/fido2/*` to `/rp/fido2/*` and introduced the `UNAUTH_FIDO_PROTOCOL_ENDPOINTS_ENABLED` flag (per the flag's own metadata in `sampleapp-features.json`: `releaseVersion:"11.3"`, `description:"Gate unauthenticated FIDO/UAF protocol endpoints. Disabled by default."`, `enabled:false` on the v11.5.0 host — i.e., **introduced in 11.3, defaults disabled, set to `false` on v11.5.0**, which is *why* `/rp/fido/get` returns 404 there; do NOT propagate the older "defaults enabled" claim — Round 17 audit correction).

**Codified rule.** Two differential axes for every finding:
1. **Cross-tenant** — run the same PoC across all discovered tenants to detect inconsistent patch rollout (a per-tenant toggle is not a code fix; report it as stopgap-not-closure).
2. **Version** — test older versions (the bug may predate the fix) and newer versions (the bug may be deprecated/removed, which itself confirms vendor awareness). Version removal of an endpoint (e.g., F22 gone in v11.5.0) is implicit vendor acknowledgement and strengthens the live-version finding's credibility.

---

## LESSON 9 — Dynamic-Verification Standard (Frida Closed-Loop)

**Concrete example.** F3 (AcmeAuthLink SSRF) and F10 (QR rpUrl injection) were both *statically confirmed* by jadx decompilation but **dynamically verified** via Frida on a rooted Android emulator (GeelyRoot API 35, arm64) under Frida 16.7.19. The closed-loop pattern:

1. **Set up an attacker receiver** (webhook.site with a UUID endpoint).
2. **Hook OkHttp in-process** to prove URL construction (`f3-poc-frida.js` hooks `okhttp3.Request$Builder.url` overloads).
3. **Invoke the vulnerable method directly via Frida**, bypassing the login-gated UI: `AcmeAuthLink.getLongLink()` with `r=webhook.site/<UUID>&t=PROOFTEST123` (F3); `createMagicLinkProfile(ctx, "https://webhook.site/<UUID>")` (F10).
4. **Confirm two-sided evidence:** (a) in-process capture `[HTTP-URL] https://webhook.site/<UUID>/rp/versioned/link?id=PROOFTEST123`; (b) attacker-server capture with decisive `User-Agent: okhttp/5.3.2` (the app's unpinned OkHttpClient, not a system component) from emulator egress IP `45.207.153.159`.
5. **Confirm response consumption** via the app's own error code (`onFailure 1114073 - Sorry, this link is invalid or expired` proves `treatResponse()` parsed the attacker response).

Static analysis was enough to *identify* the vuln (regex-only validation, unpinned `new OkHttpClient()`, trusted `url` field at jadx line 256/276). Dynamic verification was required to *prove exploitability* (that the code path actually executes and reaches the attacker host).

The mobile UI path is gated behind an enrolled/logged-in state and the app ships `TrustData` anti-emulator/anti-tamper checks (crashes on emulator), so the direct method invocation via Frida proves the code path executes identically regardless of UI entry point.

**Codified rule.** Static analysis identifies; dynamic verification proves. The standard for "dynamically verified" = a closed loop with **two-sided evidence**: (a) in-process hook showing the vulnerable code constructed the request, AND (b) an external attacker receiver (webhook.site) showing the request arrived with a decisive app fingerprint (e.g., the app's own User-Agent string). The decisive UA (`okhttp/5.3.2` from the unpinned client, not a system component) is the load-bearing evidence — it proves the request originated from the vulnerable code path, not a generic system fetch. When the UI path is auth-gated or anti-emulator-protected, invoke the vulnerable method directly via Frida to prove the code path itself executes.

---

## LESSON 10 — Methodology Gaps Acknowledged

**Concrete example.** What *future engagements should try* that this one could not:

1. **CC admin credential block (the dominant blocker).** Every RCE/SSTI/SQLi sink (`/cc/api/email/send/template` SSTI, `/cc/api/jobs/scheduler/*` RCE, `/cc/api/idv/code-customization/test` RCE, `/cc/api/reports/execute`, OPA/Rego evaluation, email-customization template render) is gated behind a CC admin session. CC login is FIDO2-gated end-to-end. The test account is enrolled under `AcmeAuthDefaultWorkstationApplication` only, not `controlCenterAdmin`. **5 classes of auth-bypass** all failed. F13's ATO cannot escalate to CC admin because credential binding is hardcoded to `AcmeAuthDefaultApplication` rpAppId. **Future: obtain a read-only CC admin test account** (physical FIDO2 device dependency outside the remote tester's control).

2. **FIDO2 device dependency (F4 chain dead-end).** The F4 PIN-leak → sessionId chain **cannot complete device registration** because `/rp/versioned/device/registrations` returns 404 `OOBChallengeNotFound` — it requires the victim's EC cryptographic key pair from the hardware-backed keystore. The original "account takeover" claim was **exaggerated and removed**; F4 downgraded High → Medium (information disclosure only).

3. **FIDO1 completion dependency (F22).** F22's `/rp/fido/send/reg` strictly validates the FIDO1 UAF `RegResponse` TLV structure and rejects all syntactic-injection variants. Without a real FIDO1-compliant authenticator (or a leaked AcmeAuth SDK), the credential-registration step cannot be completed — capping F22 at High (7.3) rather than Critical (9.8). **Future: use a real FIDO1 authenticator or leaked SDK.**

4. **DNS sandbox caveat.** DNS in the test environment returns RFC 2544 sinkhole addresses for every `*.cdn.acmeauth.example` query including fabricated hostnames. Subdomain enumeration via local DNS is unreliable — only hosts confirmed via CT logs + HTTP-probe were treated as real. **Future: use a non-sinkholed resolver or CT-log-only enumeration.**

5. **OSINT environment blocks.** GitHub code search, Google dorking via WebFetch, Censys, Shodan — all blocked by sandbox network restrictions or API-key requirements. One OSINT win did land: leaked AcmeAuth source on `github.com/<vendor-employee>/public` (RADIUS admin port 9077, default secret `"acmeauth"`, load-test backdoor usernames) — but the RADIUS service itself was unreachable (B1).

6. **Exaggeration self-correction.** The user's challenge ("接管谁的账户？越权读到别人的了么？请你实际验证" — whose account? did you read someone else's data? actually verify) triggered a correction log: F4 "account takeover" removed (404 OOBChallengeNotFound), F5 "tenant impersonation" removed (secret valid but cannot obtain tokens, integrations disabled), F4→F5 chain broken (WORKSTATION token was from legitimate enrollment not F4 PIN path), 89-day persistent token attribution removed.

**Codified rule.** Maintain an explicit "what did NOT work / what future engagements should try" section. For each gap, record the *dependency* that blocked it (physical FIDO2 device, hardware-backed keystore, FIDO1-compliant authenticator, non-sinkholed DNS, OSINT API keys). Treat user/verifier challenges to exaggerated claims as a forcing function: re-run the dynamic verification, and if the chain cannot complete, downgrade the severity and document the correction in a versioned correction log. **Exaggeration that survives unverified is a worse outcome than honest downgrade** — because triage (and the researcher's reputation) depend on the claims being reproducible.

---

## Bonus rule — "Empty body `{}` returning 400 is NOT an authz bypass"

Documented in `report-F7-systemic-authz-bypass.md`. Bean Validation runs BEFORE the `@PreAuthorize` check. An automated sweep of all 254 `/cc/api/` endpoints with empty `{}` bodies showed 130+ endpoints returning 400 — initially misread as 18 bypassed namespaces. This was **Spring deserialization error, not authz bypass.**

Correct methodology: retest with a valid OpenAPI-schema body; correct body + 403 = protected, correct body + 200/500 = true bypass. This pattern was responsible for an initial F7 false-positive of 130+ endpoints and was applied consistently to eliminate false positives across the 520-endpoint sweep.

---

## LESSON 11 — Credential Chain Analysis: From "Leak" to "Validated, Reachable, Exploitable"

**Forcing insight.** A discovered credential that is never analyzed past "I found it" produces a leak finding (typically Low/Medium, CWE-200). The same credential whose **full reachability chain** is mapped — claims decoded, scopes enumerated, downstream endpoints probed, lateral-movement paths reasoned through — often produces a Critical (CWE-522, CWE-287). The gap between these two outcomes is purely methodological. Skill policy (post-Round-21 revision) is to **push every discovered credential as deep down the chain as the scope allows**, using the tiered framework below.

### The 5-stage credential chain

For every discovered credential (token, cookie, API key, JWT, install token, refresh token), walk this chain in order. Stop only when a stage is blocked by a hard limit (Tier-3 prohibition, out-of-RoE target, missing dependency). Document the deepest stage reached as part of the finding's impact statement.

```
Stage 1: DECODE        — static structure, no system interaction
Stage 2: ENUMERATE     — reason about theoretical reach from claims/scope/aud
Stage 3: VALIDATE      — prove the credential is live (read-only, Tier-2)
Stage 4: MAP REACH     — enumerate every endpoint the validated token reaches
Stage 5: CHAIN         — synthesize with other findings to reach a higher-impact primitive
```

### Stage 1 — Decode (always allowed, Tier 1)

Decode the credential **without sending it anywhere**:

- **JWT/OIDC tokens**: split header.payload.signature, base64url-decode payload, extract `iss` / `aud` / `sub` / `exp` / `iat` / `nbf` / `scope` / `roles` / `client_id` / `azp` / `acr` / `amr` / `jti` / custom claims. Identify the signing algorithm (`alg`), key id (`kid`), and whether the signature is verifiable against any published JWKS (`/.well-known/jwks.json`, `/.well-known/openid-configuration`).
- **Session cookies**: inspect shape, length, character set, structural markers (`.` separators, base64 segments, HMAC tails). Identify whether it is a random opaque ID, a signed serialized session, or an encrypted blob. Spring Session UUIDs look different from JWT cookies which look different from Keycloak `AUTHSESSION_ID`-style cookies.
- **Install/bootstrap tokens** (e.g. AcmeAuth `hypws-`): length, entropy, prefix pattern, any embedded tenant/device hints. Compare against known taxonomy (see SKILL.md "Token taxonomy" table).
- **API keys / bearer tokens**: prefix conventions (`sk_live_`, `AKIA...`, `xoxb-`, `ghp_`), checksums, embedded metadata.

**Output of Stage 1**: a structured claim inventory + a hypothesis list ("this `scope:admin` claim, if live, would reach `/cc/api/admin/*`").

### Stage 2 — Enumerate theoretical reach (always allowed, Tier 1)

Reason about what the credential *should* be able to reach, based purely on its decoded claims and your independent knowledge of the target's API surface (from OpenAPI docs, SPA bundle mining, APK reverse, etc.):

- Cross-reference each `scope` value against the OpenAPI security scheme definitions
- Cross-reference `aud` against known service endpoints
- Identify privilege tiers the claims imply (user vs workstation vs admin vs service account)
- Note `exp` — if expired, the credential is dormant (still useful for replay-attack narratives against refresh paths)
- Note `azp` / `client_id` — identifies the issuing client, which constrains which endpoints will accept it

**Output of Stage 2**: a prioritized target-endpoint matrix. "If this token is live, here are the N endpoints to validate against, ordered by privilege tier."

### Stage 3 — Validate liveness (Tier 2 — requires user confirmation per endpoint group)

Prove the credential is currently accepted by the issuer. **Read-only endpoints only.** Confirm with the user before each distinct endpoint group; capture the response as evidence.

- Single GET to the `/me`, `/userinfo`, `/introspect`, or token-info endpoint
- Single GET to one representative endpoint per claim tier (`/profile` for user-tier, `/admin/users` for admin-tier — but **read-only**, no destructive path)
- Record the response status (200 = live, 401 = expired/revoked, 403 = live-but-wrong-scope) — each of these is a distinct evidence signal

**Critical boundary.** Stage 3 is where the credential transitions from "data we observed" to "credential we used." Each use may appear in audit logs, may trip anomaly detection, may in some jurisdictions count as unauthorized access if scope was overstated. **This is why Stage 3 requires explicit user confirmation per endpoint group**, even though the broader session authorization is trusted. The user is the one who knows whether a given GET against `/admin/users` is inside or outside their authorization envelope.

**Output of Stage 3**: liveness proven + the actual privilege tier confirmed empirically (not just inferred from claims).

### Stage 4 — Map reach (Tier 2 — requires user confirmation per endpoint group)

Now that the credential is proven live at a known tier, enumerate **every endpoint within scope** that it reaches. Still read-only.

- Run the authz matrix (`scripts/authz-matrix.sh`) with the discovered token against the full endpoint set
- Bucket results: reachable-with-data (true reach), reachable-but-empty (scope-capped), rejected (authz boundary)
- Cross-reference the reachable set against the original enumeration hypothesis from Stage 2 — discrepancies are themselves findings (e.g. a `user`-scoped token reaching `admin` endpoints = F5/F7-class authz bypass)

**Output of Stage 4**: the actual reachable surface, empirically mapped. This is the finding's "what could the attacker do" evidence base.

### Stage 5 — Chain synthesis (analysis; exploit steps remain Tier-bound)

Combine the mapped reach with other findings to construct a higher-impact primitive. The chain *narrative* is always constructible; the chain *exploitation* may be Tier-bound.

Examples from the AcmeAuth engagement:
- **F12 (credential ID leak) → F13 (credential injection)**: F12 enumerated `admin@acmeauth.example`'s 130 credential IDs (Stage 4 of F12's chain), which became the target list for F13's injection. F12 alone was 5.3 Medium; F12 + F13 = Critical.
- **F8 (install token) → F5/F7/F9 (authz bypass)**: F8's minted `hypws-` token (Stage 3 of F8's chain) reached F5/F7/F9's missing-`@PreAuthorize` endpoints (Stage 4 of F8's chain mapped the reach). Pre-patch this synthesized to a destructive DELETE chain (F9). Post-patch the chain is dormant but the primitive remains — Stage 5 reasoning retains it as a persistence primitive.
- **F22 (FIDO1 UAF state injection) → potential FIDO1 completion**: F22 reached Stage 4 (state planted on `admin@acmeauth.example`'s account), Stage 5 chain was blocked by `/rp/fido/send/reg` TLV validation. Documented as "chain blocked at dependency X" rather than closed.

**Output of Stage 5**: a chain narrative with explicit per-stage reachability evidence, used either for report submission (if all stages completed within scope) or for the "future work / dependencies" section (if a stage was blocked).

### What this lesson replaces

The prior blanket rule "Do not validate discovered credentials — reading is testing, testing is using" conflated *analysis* (Stages 1-2, always allowed) with *exploitation* (forbidden with real values). The tiered framework separates them: **analysis is mandated and exhaustive**, dynamic validation against read-only endpoints is permitted with user confirmation, and destructive exploitation with real values remains prohibited. The shift is from "stop at the leak" to "walk the chain as far as scope and Tier rules allow, then document the boundary."

### Concrete AcmeAuth worked example

When the install token (`hypws-`) was discovered:

- **Stage 1 (decode)**: prefix `hypws-` (install/bootstrap class), 89-char high-entropy opaque body, no embedded claims. Identified as the AcmeAuth install-token taxonomy class.
- **Stage 2 (enumerate)**: from SKILL.md's "Token taxonomy" + the OpenAPI surface, hypothesized it reaches `/cc/install/token/exchange` and downstream WORKSTATION-scope endpoints.
- **Stage 3 (validate)**: confirmed via `POST /cc/install/token/exchange` → minted `hypwo-` WORKSTATION bearer. Proven live. (This is a state-changing endpoint, but it is the *issuance* primitive, not a destructive downstream call — treated as Tier-2-equivalent validation because it is the only way to prove the install token itself is live. Borderline; document the reasoning.)
- **Stage 4 (map reach)**: ran the WORKSTATION bearer against the full `/cc/api/*` matrix → discovered F5/F7/F9 (the 9 IdP endpoints missing `@PreAuthorize`). This is the stage where the finding escalated from "token leak" (CWE-200, Low) to "authz bypass cluster" (CWE-862, originally Critical before patch).
- **Stage 5 (chain)**: pre-patch, F9's destructive DELETE was the chain terminus (would-have-been Critical). Post-patch, the chain is dormant — F8 retains as persistence primitive at 5.4 Medium.

Without this 5-stage walk, F8 would have been reported as "install token leaked, CWE-200, Low." With it, F8 became the anchor for the F5/F7/F9 authz-bypass cluster — a substantially different triager outcome.

---

## Cross-cutting Meta-Lesson

The single strongest process insight across all 13 sessions: **the negative-control test (Lesson 1) and the strict CVSS precondition-reality check (Lesson 2) are the two methodology disciplines that convert an optimistic finding set into a defensible one.** F25 was caught by Lesson 1; F4/F5 were caught by Lesson 2's sibling (dynamic re-verification of impact claims); F8/F18/F24/F3/F10 were correctly tiered by Lesson 2. The engagement's final honest picture — 1 Critical (F13, partially mitigated) + 1 High (F22, the only "clean High with no precondition caps") + 8 Medium + 1 Low — is CVSS-defensible precisely because the inflation was stripped out rather than left in.
