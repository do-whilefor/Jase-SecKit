# Asset Attribution & Evidence Methodology

Asset attribution and reproducible evidence are the reusable lessons from the AcmeAuth engagement.

---

## 1. Asset attribution: know what you are hitting (AcmeAuth example, generalizable)

The AcmeAuth engagement identified vendor and third-party assets under `*.acmeauth.example` / `*.cdn.acmeauth.example`. Third-party examples included:

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

### Other service hosts
- `support.acmeauth.example`
- `help.acmeauth.example`
- `partners.acmeauth.example`

### Generalization rule

Customer (third-party) assets under a vendor wildcard are recognizable by:
- Recognizable brand names (`<customer>`, `<customer>`, `<customer>`, `<customer>`)
- `vault-*` or similar per-customer prefix pattern
- Non-vendor AWS account IDs embedded in hostname (cross-reference with CT-log vault-prefix enumeration — see [osint-asset-discovery.md](osint-asset-discovery.md) #2)
- Customer brand appearing in marketing strings (APK `strings.xml`, vendor `/customers` page)

**A shared parent domain does not establish common ownership; correlate tenant names with independent vendor and brand evidence.**

### ⚠️ Customer-tenant name-confusion trap (Round 15 audit forcing case)

Some customer tenants are branded with names that look like internal AcmeAuth test infrastructure —
**Brand attribution adds evidence that hostname shape alone cannot supply.** During the AcmeAuth
engagement, `<customer>.acmeauth.example` (<customer>) and `<customer>.acmeauth.example` (<customer>) were
mistakenly grouped with AcmeAuth-owned test tenants (`pentesting`, `tenant-001`, `crowd`) and an
unauthenticated state-changing `POST /logs` was accepted on both (HTTP 204). The ownership classification was wrong even though the names looked internal.

The same trap applies to: any `<word>.acmeauth.example` tenant where `<word>` is not a known AcmeAuth
internal label (compare with the engagement's vendor-host labels: `tenant-demo`, `pentesting*`,
`tenant-001`, `tenant-002`, `sampleapp.dev`, `oauth.dev`, `demo`, `portal`, `demobank`, `cc`,
`app`, `api`, `docs`, `vpn-pritunl`, `enhancements`).

---

## 2. Evidence methodology (Honesty > Severity)

These rules are mandatory for every finding and every report.

### 2.1 Negative control for enumeration/differential claims
Before claiming an oracle distinguishes existing vs non-existing identifiers, run the identical protocol against a freshly-generated random identifier guaranteed not to exist (`zzznonexistent<timestamp>@nowhere.com`). Without the control, rate-limit counters, IP reputation, and lockout cooldowns masquerade as deterministic differentials. **F25 was retracted on this rule.**

### 2.2 Dynamic verification before claiming exploitability
"Dynamic verified" = closed loop with two-sided evidence: (a) in-process hook showing the vulnerable code constructed the request, AND (b) an external attacker receiver (webhook.site) showing the request arrived with a decisive app fingerprint. Static analysis identifies; dynamic verification proves.

### 2.3 CVSS strict — never score against narrative
Score against the FIRST.org 3.1 spec formula. Strip the 4 inflation patterns (PR:L as PR:N, UI:R as UI:N, AC:H as AC:L, narrative impact as direct C/I/A). See [cvss-scoring-methodology.md](cvss-scoring-methodology.md).

### 2.4 Empty body `{}` returning 400 is NOT an authz bypass
Bean Validation runs BEFORE `@PreAuthorize`. Always re-test with a schema-valid body before claiming bypass.

### 2.5 SPA fallback ≠ controller reach
A `200` with `text/html` after a path-filter bypass usually means the request fell through to the SPA static handler. Discriminating signal: SPA fallback serves `index.html` and returns `405` on non-GET.

### 2.6 Reproducibility and severity correction
Re-run dynamic verification on challenge; if the chain cannot complete, downgrade severity and document the correction in a versioned log. **The AcmeAuth user's challenge ("接管谁的账户？越权读到别人的了么？请你实际验证" — whose account? did you read someone else's data? actually verify) triggered a correction log** that downgraded F4 (High→Medium, "account takeover" removed) and F5 ("tenant impersonation" removed). The correction log itself is a methodology artifact. Triage (and the researcher's reputation) depend on the claims being reproducible.

### 2.7 Empirical closure (document negatives)
"Hard goal 0/3" must be documented with negative results per host/per hypothesis, not asserted. See [killed-hypotheses.md](killed-hypotheses.md).

### 2.8 Document technical dependencies
When a chain cannot complete because of a missing dependency or hardware authenticator, record the deepest reproduced stage and the missing condition. See [report-structure.md](report-structure.md).

---

## 3. The forcing function: user / verifier challenges

Treat user or verifier challenges to your claims as a forcing function, not an attack. The AcmeAuth engagement's most valuable corrections came from user challenges:

- "这不是测试站点吗？sample" (Isn't this a test site? sample) → demo-environment classification and impact correction
- "接管谁的账户？越权读到别人的了么？请你实际验证" (Whose account? Did you read someone else's data? Actually verify) → F4/F5 dynamic re-verification and severity correction

When challenged:
1. Re-read the original finding critically.
2. Re-run the dynamic verification.
3. If the claim cannot be reproduced, downgrade severity and document the correction.
4. Update the report with the corrected version.

**Honesty is the only durable strategy in vuln research.** Inflated findings get rejected; rejected findings cost reputation; reputation loss compounds across submissions. A defensible Medium is better than an inflated High.

---
