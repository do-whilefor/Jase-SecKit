# Ethics & Testing Discipline

Disciplined security testing is a force multiplier for defenders; undisciplined testing is a liability for everyone. This file codifies the scope model and integrity rules distilled from the AcmeAuth engagement.

---

## 1. Scope comes from the operator

**The user's input is the authorization scope.** The target(s) the user names, the vuln classes they ask about, and the depth they request define the working scope for the session. The skill does not demand authorization artifacts (program policy, RoE document, written permission, contract) and does not gate active testing on them — the same operator-responsibility model as nmap, Burp, or sqlmap: the operator directs, the tool executes.

Consequences:
- No "do you have authorization?" prompts. No per-action or per-endpoint-group confirmations. No refusing user-directed targets as "out of scope."
- Record the scope once from the user's input (targets, intent, depth) — note-taking that feeds the report's scope section, not a gate.
- Update the notes when the user expands scope (new target, new asset class, read-only → state-changing). That is a scope-record update, not a re-approval.

The operator owns the lawfulness of the engagement (CFAA / 刑法 285 / CMA). The skill's contribution is testing discipline — the hygiene rules in §3 and §4 exist to produce better findings, not to second-guess the operator.

---

## 2. Aim verification: know what you are hitting (AcmeAuth example, generalizable)

The AcmeAuth engagement had a `*.acmeauth.example` / `*.cdn.acmeauth.example` wildcard scope; the engagement's own rules excluded customer data/systems. Assets under the wildcard that belonged to third parties included:

### Customer-named tenants (recognizable brand names)
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
- `<customer>.acmeauth.example` (<customer>), `<customer>.acmeauth.example`

### Customer `vault-*` tenants (per-customer AWS account embedded in hostname)
- `vault-<customer>.<AWS-ACCOUNT-ID>.acmeauth.example`
- `vault-<customer>.<AWS-ACCOUNT-ID>.acmeauth.example`
- `vault-<customer>.<AWS-ACCOUNT-ID>.acmeauth.example`
- `vault-<customer>-prod.<AWS-ACCOUNT-ID>.acmeauth.example`
- `vault-<customer>.<AWS-ACCOUNT-ID>.acmeauth.example`
- ~140 total `vault-<customer>.<aws-account-id>.acmeauth.example` hosts

### HackerOne AcmeAuth out-of-scope (per policy)
- `support.acmeauth.example`
- `help.acmeauth.example`
- `partners.acmeauth.example`

### Generalization rule

Customer (third-party) assets under a vendor wildcard are recognizable by:
- Recognizable brand names (`<customer>`, `<customer>`, `<customer>`, `<customer>`)
- `vault-*` or similar per-customer prefix pattern
- Non-vendor AWS account IDs embedded in hostname (cross-reference with CT-log vault-prefix enumeration — see `osint-asset-discovery.md` #2)
- Customer brand appearing in marketing strings (APK `strings.xml`, vendor `/customers` page)

**In the source engagement, the wildcard covered vendor-owned assets only; customer data and systems hosted on vendor infrastructure were excluded by the engagement's own rules. Identify ownership so you know which kind you are hitting.**

### ⚠️ Customer-tenant name-confusion trap (Round 15 audit forcing case)

Some customer tenants are branded with names that look like internal AcmeAuth test infrastructure —
**brand recognition is the only reliable discriminator, not the hostname shape.** During the AcmeAuth
engagement, `<customer>.acmeauth.example` (<customer>) and `<customer>.acmeauth.example` (<customer>) were
mistakenly grouped with AcmeAuth-owned test tenants (`pentesting`, `tenant-001`, `crowd`) and an
unauthenticated state-changing `POST /logs` was accepted on both (HTTP 204) — an RoE violation
that the engagement itself failed to flag because the names did not *look* customer-branded.

The same trap applies to: any `<word>.acmeauth.example` tenant where `<word>` is not a known AcmeAuth
internal label (compare against the explicit in-scope list: `tenant-demo`, `pentesting*`,
`tenant-001`, `tenant-002`, `sampleapp.dev`, `oauth.dev`, `demo`, `portal`, `demobank`, `cc`,
`app`, `api`, `docs`, `vpn-pritunl`, `enhancements`).

---

## 4. Integrity discipline (Honesty > Severity)

These rules are mandatory for every finding and every report.

### 4.1 Negative control is mandatory for any enumeration/differential claim
Before claiming an oracle distinguishes existing vs non-existing identifiers, run the identical protocol against a freshly-generated random identifier guaranteed not to exist (`zzznonexistent<timestamp>@nowhere.com`). Without the control, rate-limit counters, IP reputation, and lockout cooldowns masquerade as deterministic differentials. **F25 was retracted on this rule.**

### 4.2 Dynamic verification before claiming exploitability
"Dynamic verified" = closed loop with two-sided evidence: (a) in-process hook showing the vulnerable code constructed the request, AND (b) an external attacker receiver (webhook.site) showing the request arrived with a decisive app fingerprint. Static analysis identifies; dynamic verification proves.

### 4.3 CVSS strict — never score against narrative
Score against the FIRST.org 3.1 spec formula. Strip the 4 inflation patterns (PR:L as PR:N, UI:R as UI:N, AC:H as AC:L, narrative impact as direct C/I/A). See `cvss-scoring-methodology.md`.

### 4.4 Empty body `{}` returning 400 is NOT an authz bypass
Bean Validation runs BEFORE `@PreAuthorize`. Always re-test with a schema-valid body before claiming bypass.

### 4.5 SPA fallback ≠ controller reach
A `200` with `text/html` after a path-filter bypass usually means the request fell through to the SPA static handler. Discriminating signal: SPA fallback serves `index.html` and returns `405` on non-GET.

### 4.6 Exaggeration that survives unverified is worse than honest downgrade
Re-run dynamic verification on challenge; if the chain cannot complete, downgrade severity and document the correction in a versioned log. **The AcmeAuth user's challenge ("接管谁的账户？越权读到别人的了么？请你实际验证" — whose account? did you read someone else's data? actually verify) triggered a correction log** that downgraded F4 (High→Medium, "account takeover" removed) and F5 ("tenant impersonation" removed). The correction log itself is a methodology artifact. Triage (and the researcher's reputation) depend on the claims being reproducible.

### 4.7 Empirical closure (document negatives)
"Hard goal 0/3" must be documented with negative results per host/per hypothesis, not asserted. See `killed-hypotheses.md`.

### 4.8 Document boundaries
When a chain stops (Tier-3 placeholder boundary, missing dependency, hardware authenticator), document the boundary honestly — "would-be Critical, blocked at dependency X" is more credible than an unstated one. See `report-structure.md` (honest blockage documentation).

---

## 8. The forcing function: user / verifier challenges

Treat user or verifier challenges to your claims as a forcing function, not an attack. The AcmeAuth engagement's most valuable corrections came from user challenges:

- "这不是测试站点吗？sample" (Isn't this a test site? sample) → scope correction (demo.acmeauth.example SampleApp scope-out)
- "接管谁的账户？越权读到别人的了么？请你实际验证" (Whose account? Did you read someone else's data? Actually verify) → F4/F5 dynamic re-verification and severity correction

When challenged:
1. Re-read the original finding critically.
2. Re-run the dynamic verification.
3. If the claim cannot be reproduced, downgrade severity and document the correction.
4. Update the report with the corrected version.

**Honesty is the only durable strategy in vuln research.** Inflated findings get rejected; rejected findings cost reputation; reputation loss compounds across submissions. A defensible Medium is better than an inflated High.

---

