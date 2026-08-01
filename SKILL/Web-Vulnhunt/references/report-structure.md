# Vulnerability Report Structure

Canonical report structure distilled from the AcmeAuth engagement's submission set. Triage reads dozens of reports a week — make yours scannable, reproducible, and CVSS-defensible.

---

## File naming

`report-<FINDING-ID>-<short-slug>.md`

Examples:
- `report-F22-unauth-fido1-uaf-submit.md`
- `report-C2-jwksurl-ssrf.md`
- `report-F5-workstation-token-idp-secret-leak.md`
- `report-F8-install-token-reuse.md`

Use `C` prefix for Critical-track, `F` for everything else. Number sequentially within the engagement.

---

## Canonical report template

```markdown
# <Finding ID> — <Short title> (<CVSS score> <Severity>)

**CVSS 3.1**: `<vector string>` — <score> <SEVERITY>
**CWE**: <CWE-ID> <name> (+ <CWE-ID> <name> if multi)
**Status**: <Live / Remediated / Partially mitigated> as of <date>
**Affected versions/tenants**: <list>

---

## 1. Summary

One paragraph (3-5 sentences) covering: what the vuln is, where it lives, what an attacker can do, and the impact ceiling. This is the elevator pitch — if triage reads only this, they should understand the finding.

## 2. Affected assets

Table of every affected tenant / version / endpoint. Include the negative-control result here if applicable.

| Tenant | Endpoint | Result |
|---|---|---|
| pentesting2.cdn.acmeauth.example | POST /rp/fido/get | 200 — vuln confirmed |
| tenant-001.cdn.acmeauth.example | same | 200 — vuln confirmed |
| sampleapp.dev.acmeauth.example (v11.5.0) | same | 404 — endpoint removed |

## 3. Reproduction

Step-by-step PoC with literal `curl` commands (or Python / Frida script for mobile). Triage should be able to copy-paste and reproduce.

\`\`\`bash
# Step 1: ...
curl -sk -X POST https://pentesting2.cdn.acmeauth.example/rp/fido/get \
  -H 'Content-Type: application/json' \
  -d '{...}'

# Step 2: ...
\`\`\`

Expected output (truncated):
\`\`\`json
{"status":{"responseCode":200,...},"response":{...}}
\`\`\`

## 4. Negative control

Required for any enumeration/differential claim. Show the identical protocol run against a guaranteed-nonexistent identifier. If the result is the same, you don't have an oracle.

\`\`\`bash
curl -sk -X POST https://pentesting2.cdn.acmeauth.example/rp/fido/get \
  -H 'Content-Type: application/json' \
  -d '{"fidoPayload":{"context":{"transaction":"Reg","userName":"zzznonexistent1785022468@nowhere.com"},"op":"Reg","extras":{}},"session":{"sessionId":"x"}}'
# Response: HTTP 200, "Registration Success", challenge bound to zzznonexistent1785022468@nowhere.com
# Conclusion: endpoint accepts ANY username; not an enumeration oracle but IS unauth state creation.
\`\`\`

## 5. CVSS computation (manual, per FIRST.org 3.1)

Show the math so triage can verify:

- ISCBase = 1 − (1−0.22)(1−0.22)(1−0.22) = 0.525
- Impact (S:U) = 6.42 × 0.525 = 3.37
- Exploitability = 8.22 × 0.85 × 0.77 × 0.85 × 0.85 = 3.89
- BaseScore = roundup(min(3.37 + 3.89, 10)) = roundup(7.26) = **7.3 High**

## 6. CWE mapping

- **CWE-306** (Missing Authentication for Critical Function) — primary
- **CWE-384** (Session Fixation) — sessionId echoed verbatim
- **CWE-248** (Uncaught Exception) — op=Auth 500

## 7. Impact

Enumerate the direct impacts (C/I/A), not narrative:
- **C:L** — server confirms username exists in challenge response
- **I:L** — attacker can plant FIDO1 registration state on arbitrary accounts
- **A:L** — op=Auth 500 amplifies CPU via stack-trace generation

Note what the vuln DOES NOT enable (be explicit, prevents triage inflation concerns):
- Does NOT enable credential completion (TLV validation blocks)
- Does NOT enable ATO (rpAppId binding)
- Does NOT read customer data

## 8. Escalation attempts (what couldn't be completed)

Be explicit about dead ends. This is honesty, not weakness.

- `/rp/fido/send/reg` strictly validates FIDO1 TLV; all syntactic-injection variants rejected with 400/500
- Without a real FIDO1-compliant authenticator (or leaked AcmeAuth SDK), the credential-registration step cannot be completed
- This caps severity at High (7.3) rather than Critical (9.8)

## 9. Recommended remediation

Concrete, actionable fixes:
1. Enforce authentication on `/rp/fido/get` (or restrict to localhost/workstation context as newer versions appear to do)
2. Regenerate `sessionId` server-side rather than echoing the client value
3. Add graceful error handling for `op=Auth` against authenticator-less users
4. (Defense-in-depth) Remove `/rp/fido/get` from production tenants — v11.5.0 has already done this

## 10. Version differential

| Version | Endpoint status |
|---|---|
| v11.1.0 (tenant-demo) | Live |
| v11.3.0 (pentesting2, tenant-001, etc.) | Live |
| v11.5.0 (sampleapp.dev) | 404 — endpoint removed |

The removal in v11.5.0 is implicit vendor acknowledgement that the legacy FIDO1 surface is a liability.

## 11. Evidence

Absolute paths to local evidence files (screenshots, captured responses, Frida scripts):
- `<engagement-findings-dir>/sessionXX-<slug>-evidence.txt`
- `<engagement-findings-dir>/<slug>-poc.{sh,py,js}`

## 12. References

- FIRST.org CVSS 3.1 spec
- CWE database entries
- Relevant CVEs (e.g., CVE-2022-2193 for AcmeAuth FIDO2 IDOR pattern)
- Any prior art on the same vuln class
```

---

## Report-writing discipline

### Do
- **Show the math.** CVSS computation section is non-negotiable.
- **Show the negative control.** Required for enumeration claims.
- **Show the version differential.** Demonstrates thoroughness.
- **Be explicit about what the vuln does NOT enable.** Pre-empts triage inflation concerns.
- **Use placeholder values for destructive endpoints.** `ZZFAKE`, `nobody`, `0`-prefixed random.
- **Include literal `curl` commands.** Triage should copy-paste to reproduce.
- **Include the response body.** Truncate if huge but show the structure.
- **Cite absolute paths for local evidence.** Triage may ask for the full capture.

### Don't
- **Don't inflate severity.** Strip the 4 inflation patterns before scoring.
- **Don't claim exploitability without dynamic verification** for mobile findings.
- **Don't omit the escalation attempts section.** Dead ends are honesty, not weakness.
- **Don't use real customer identifiers in PoCs.** Use placeholders or test-tenant values.
- **Don't include customer PII.** Even inadvertently. If a PoC returned customer data, redact before reporting.
- **Don't credit downstream chains in CVSS.** Score the direct impact of THIS vuln.
- **Don't conflate "info leak" with "prerequisite for ATO".** F12 enables F13 but scores 5.3, not 9.8.

---

## Report package structure (for the engagement)

```
<vendor>-findings/
├── SUBMISSION-PACKAGE.md        # master narrative, all sessions, all findings
├── 00-summary.md                # round-by-round tactics
├── 01-*.md through 13-*.md      # per-session detailed logs
├── report-*.md                  # per-finding canonical reports (one per finding)
├── session<N>-<topic>/          # per-session raw evidence
│   ├── SUMMARY.md
│   ├── evidence.txt
│   └── ...
├── openapi-spec.json            # discovered API surface (696 KB)
└── apk/                         # mobile APK reverse-engineering output
    ├── jadx-out/
    └── apktool-out/
```

The SUBMISSION-PACKAGE.md is the master document — every session's work appended in chronological order, every finding re-scored in the final session. The per-finding `report-*.md` files are the canonical submissions to the program. The session-N directories hold raw evidence.

---

## Video / demo script (if requested)

For findings that benefit from a demo (F22 was demonstrated via video), produce a companion script:

```
<FINDING-ID>-PRESENTATION-SCRIPT.md    # narration script, 4-5 min runtime
<FINDING-ID>-RECORD.sh                 # directly-executable recording script
```

The recording script should:
- Use a TARGET variable at the top (default to authorized test tenant)
- Run each segment as a clear block with a header
- Pause for narration between segments
- End with a closing card showing CVSS, CWE, and severity
- Use placeholder attacker hosts (webhook.site URLs, not real attacker domains)
- Demonstrate against an AUTHORIZED TEST TENANT only, never a customer tenant

---

## Vulnerability-chain synthesis (turn N Mediums into 1 Critical)

Single-finding reports cap out at the single-finding CVSS. The highest-value engagement output is often a **synthesized chain** that combines multiple individual findings into a single higher-impact primitive. Triage rewards chains because they prove real-world exploitability, not just theoretical weakness.

### When to write a chain report vs. individual reports

Write a chain report (`report-CHAIN-<topic>.md`) **in addition to** the individual finding reports when **two or more findings compose into a primitive none of them produces alone**. Always submit the individual findings as standalone reports first (programs frequently pay for each independently), then submit the chain report as a separate higher-severity item.

Do NOT write a chain report when:
- The "chain" is just "finding A makes finding B slightly easier" with no qualitative severity change
- One of the findings is already Critical on its own (F13 + anything is still just F13)
- The chain requires a step that is out-of-RoE or Tier-3-prohibited to actually exploit (document the chain as "future work" in the master report instead)

### Chain report structure

```markdown
# CHAIN-<topic>: <headline primitive> (e.g. "Unauthenticated account takeover via FIDO1 state injection + session fixation")

## Composite findings
- F-X (<individual CVSS>): <one-line role in the chain>
- F-Y (<individual CVSS>): <one-line role>
- F-Z (<individual CVSS>): <one-line role>

## Chain narrative
<Step-by-step, each step citing the finding it depends on>

## Chain precondition reality check
<Honest assessment of every precondition: which are zero-precondition, which require prior attacker position, which require UI:R / AC:H>

## Composite CVSS
<Score the END primitive, not the average of components. Cite the strict vector and walk the computation.>

## Why this is worse than the sum of its parts
<The one-paragraph triager-friendly explanation of why the chain matters as a separate submission>

## Per-finding evidence
<Cross-reference each component finding's report-*.md file; do not re-produce PoCs>
```

### Worked AcmeAuth examples (chains the engagement identified)

**Chain 1 — Pre-patch F8 + F5/F7/F9 (Critical-equivalent, now dormant).**
- F8 (Medium 5.4): unauthenticated install-token infinite mint produces a WORKSTATION bearer
- F5 (was Critical, remediated): WORKSTATION bearer reads plaintext `keycloakSecret` for all SSO integrations via missing `@PreAuthorize`
- F9 (was Critical, remediated): WORKSTATION bearer permanently deletes SSO integrations
- **Chain primitive**: unauthenticated attacker mints a bearer, exfiltrates every customer's SSO secret, and/or destructively deletes SSO — taking down customer authentication. The individual findings were each "authenticated with a low-priv token" Medium/Critical; the chain was "fully unauthenticated destructive cross-tenant auth disruption" — qualitatively worse. (Post-patch the chain is dormant; F8 retains as persistence primitive.)

**Chain 2 — F12 + F13 (Critical, the engagement's flagship).**
- F12 (Medium 5.3): unauthenticated FIDO2 assertion-options leaks `admin@acmeauth.example`'s 130 credential IDs + 47.9× size oracle for user enumeration
- F13 (Critical 9.1): unauthenticated FIDO2 attestation-result accepts forged `fmt:"none"` credential, persists to the victim account
- **Chain primitive**: F12 hands F13 the target list and confirms which accounts are valid; F13 plants attacker-controlled credentials on each. Individual CVSS for F12 caps at 5.3 (CWE-200, no direct impact); the chain is account-credential-injection at Critical.

**Chain 3 — F22 + FIDO1-completion-dependency (blocked, documented as future work).**
- F22 (High 7.3): unauthenticated `/rp/fido/get op=Reg` plants session state on arbitrary accounts + session fixation
- Blocker: `/rp/fido/send/reg` strictly validates FIDO1 UAF TLV; requires real authenticator
- **Chain primitive (hypothetical)**: if the FIDO1 completion dependency were resolvable (real authenticator or leaked AcmeAuth SDK), F22 → full account takeover. **Documented as future work, not as a chain report**, because the chain cannot actually be completed within the engagement's dependencies.

### Chain synthesis methodology

1. **Inventory**: list every finding with its CVSS, preconditions, and "what it gives the attacker" (a credential, a primitive, an oracle, a state change).
2. **Output-input matching**: for each finding's output, scan for another finding whose input it satisfies. F8 outputs a bearer → which findings accept a bearer? F12 outputs credential IDs → which findings need a target credential?
3. **Precondition collapse**: when finding A's output satisfies finding B's precondition, the chain's *effective* precondition is the union minus the now-satisfied ones. F8 + F5 collapses PR:L (F8's install-token requirement) + PR:N (F5's endpoint) → effectively PR:N if the install token is itself unauthenticated-mintable, otherwise PR:L. This collapsed precondition is what the chain CVSS uses.
4. **Tier check**: confirm every step of the synthesized chain is within RoE and within the credential Tier framework (Stages 1-4 mandated; Stage 5 narrative always allowed, exploitation Tier-bound).
5. **Honest blockage documentation**: when a chain step is blocked by an unresolvable dependency (hardware authenticator, OSINT API access, out-of-RoE target), do NOT omit it — document it as the chain's boundary. A documented "would-be Critical, blocked at dependency X" is more credible than an unstated one.

### The reporting discipline

A chain report is a **force multiplier**, not a substitute for individual reports. Submit both:
- Individual reports let the program patch each component independently and pay each bounty
- The chain report demonstrates that the components compose, justifying a higher composite bounty and forcing the vendor to verify the patch closes the chain (not just each component)

Skipping the chain report leaves value on the table; skipping the individual reports risks the program closing only one component and leaving the chain re-armsable.
