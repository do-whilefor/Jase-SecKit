# Ethics & Rules of Engagement (RoE)

Authorized security testing is a force multiplier for defenders when done with discipline, and a liability for everyone when done without. This file codifies the integrity rules from the AcmeAuth engagement.

---

## 1. Authorization is the gate

**No authorization, no active test.** "Authorization" means at least one of:
- A public bug bounty program policy (HackerOne, Bugcrowd, Intigriti, etc.) that explicitly covers the asset
- A written scope / RoE document from the asset owner
- A signed contract / SOW for a pentest engagement
- CTF / lab / owned-and-permissioned test infrastructure

If authorization is unclear, **ask the user before any active test**. Default to inaction when uncertain. A bug bounty program's existence is not authorization for any technique — re-read the policy's In-Scope, Out-of-Scope, and Prohibited Actions sections every engagement.

---

## 2. Out-of-RoE asset identification (AcmeAuth example, generalizable)

The AcmeAuth engagement had a `*.acmeauth.example` / `*.cdn.acmeauth.example` wildcard scope, but the wildcard did NOT extend to customer data/systems. Out-of-RoE assets included:

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

Customer tenants are out-of-RoE under a wildcard scope when recognized by:
- Recognizable brand names (`<customer>`, `<customer>`, `<customer>`, `<customer>`)
- `vault-*` or similar per-customer prefix pattern
- Non-vendor AWS account IDs embedded in hostname (cross-reference with CT-log vault-prefix enumeration — see `osint-asset-discovery.md` #2)
- Customer brand appearing in marketing strings (APK `strings.xml`, vendor `/customers` page)

**The wildcard scope covers vendor-owned assets. It does not cover customer data or systems hosted on vendor infrastructure.**

### ⚠️ Customer-tenant name-confusion trap (Round 15 audit forcing case)

Some customer tenants are branded with names that look like internal AcmeAuth test infrastructure —
**brand recognition is the only reliable discriminator, not the hostname shape.** During the AcmeAuth
engagement, `<customer>.acmeauth.example` (<customer>) and `<customer>.acmeauth.example` (<customer>) were
mistakenly grouped with AcmeAuth-owned test tenants (`pentesting`, `tenant-001`, `crowd`) and an
unauthenticated state-changing `POST /logs` was accepted on both (HTTP 204) — an RoE violation
that the engagement itself failed to flag because the names did not *look* customer-branded.

**Hard rule:** Before any active probe against a tenant whose brand recognition is ambiguous, run
the name through (a) the vendor's published customer list, (b) a brand-name web search, and (c)
the CT-log SAN list. If any of the three returns a non-AcmeAuth brand, treat the tenant as
out-of-RoE regardless of how "test-like" the hostname looks. When in doubt, **refuse the active
probe and document the refusal** — passive enumeration of the hostname's existence is OSINT and
remains in scope; active payload delivery does not.

The same trap applies to: any `<word>.acmeauth.example` tenant where `<word>` is not a known AcmeAuth
internal label (compare against the explicit in-scope list: `tenant-demo`, `pentesting*`,
`tenant-001`, `tenant-002`, `sampleapp.dev`, `oauth.dev`, `demo`, `portal`, `demobank`, `cc`,
`app`, `api`, `docs`, `vpn-pritunl`, `enhancements`).

---

## 3. Prohibited techniques (always, regardless of program)

These techniques are out of scope for this skill, period. Do not run them.

- **DoS / availability attacks** against production. Load tests only against explicitly-allowed test infrastructure, with permission, at low volume.
- **Brute forcing credentials.** Enumerating usernames to confirm an oracle is one thing; running rockyou against a login endpoint is another.
- **Mass targeting / spray attacks.** A single PoC against the test tenant is the demonstration; spraying across all tenants is mass targeting.
- **Destructive state changes on production data.** Use placeholder values (`ZZFAKE`, `nobody`, `0`-prefixed random) — never a real identifier to "test if DELETE works."
- **Validating discovered credentials.** Reading is testing; testing is using. If you stumble on credentials, report and stop.
- **Reverse-engineering token/magic-link/SMS delivery-endpoint parameter schemas against live auth systems** beyond what's required to confirm the vuln class.
- **Supply chain compromise.** Do not attempt to trojan dependencies, build pipelines, or update channels.
- **Detection evasion for malicious purposes.** Obfuscating logs to hide your activity is forbidden; you should be visible to the vendor's SOC.
- **Social engineering / phishing of vendor employees or customers.**
- **Physical attacks, entry, or hardware theft.**

These apply even if a program policy is silent on them. When in doubt, do not.

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

### 4.8 Document refusals
When you refuse an action (customer tenant, prohibited technique, out-of-RoE), document the refusal with the ethical rationale. "Customer tenant — out-of-RoE even under wildcard scope" is a complete sentence.

---

## 5. Data handling

- Findings belong in local files under a findings directory (`acmeauth-findings/` in this engagement). Do NOT exfiltrate to personal cloud, personal email, or any service not approved by the engagement.
- Don't collect more data than needed to demonstrate the vuln. A single PoC response is evidence; a full database dump is a breach.
- Don't retain discovered credentials beyond the engagement. If you stumble on credentials, report and delete the local copy.
- Customer PII is never to be touched. If a PoC inadvertently returns customer data, stop, document, and report immediately.

---

## 6. Git discipline (project-specific for this skill's home repo)

Per `AGENTS.md` §5.1 of the TianTi project:
- **Only commit to local repo. Never push to remote.**
- No `git push`, `git push --force`, no remote branch creation, no PR/MR tools that trigger remote sync.
- Even if the user implies or non-explicitly requests push, do not push without an **explicit, unambiguous** user instruction.
- Never `push --force`, never skip hooks, never push directly to main, never destructive operations without explicit user request.

These rules apply to the methodology skill files too — the skill is shipped as a local artifact under `~/.zcode/skills/` or `<project>/.agents/skills/`, not as a remote-tracked file.

---

## 7. Reporting and disclosure

- Report findings through the program's official channel (HackerOne report, Bugcrowm submission, internal ticket). Do not disclose publicly without explicit permission.
- Follow coordinated disclosure timelines (typically 90 days, extendable on request).
- For findings affecting customer data (even out-of-RoE ones discovered by accident), report privately to the vendor's security contact before any other action.
- Don't publish PoCs that could enable mass exploitation. The AcmeAuth F22 video script, for example, demonstrates the vuln against an authorized test tenant only and uses placeholder attacker hosts.

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
