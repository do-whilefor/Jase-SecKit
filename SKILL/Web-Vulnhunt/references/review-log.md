# Review Log — 20-Round Skill Audit

This file records the audit trail for the ≥20-round full-corpus review mandated by the
skill's installation directive. Each round examined one independent facet of the corpus
(`<engagement-findings-dir>/` — SUBMISSION-PACKAGE.md + 00-summary.md +
all report-*.md) against the skill
(`~/.zcode/skills/web-vulnhunt-methodology/`).

**Verdict legend:** NEW = a corpus element the skill entirely missed;
CORRECTED = the skill had it but stated it incorrectly/incompletely (fix applied);
CONFIRMED-NO-OMISSION = nothing to add.

---

## Rounds 1–9 (Phase 1 extraction + Phase 2 cross-cutting + Phase 6 self-review)

| Round | Facet | Verdict |
|------:|-------|---------|
| 1 | Methodology lessons extraction | CONFIRMED — Phase 1 extraction agent |
| 2 | Bypass catalogue extraction | CONFIRMED — Phase 1 extraction agent |
| 3 | OSINT/asset discovery extraction | CORRECTED — flagged 4 over-claims (Greenhouse ATS, Postman slug, controlCenterAdmin "pseudo-appId", "30-day sliding" TTL) — all excluded |
| 4 | FIDO/WebAuthn extraction | CONFIRMED |
| 5 | Cross-cutting: consistency between lessons and CVSS | CONFIRMED |
| 6 | Cross-cutting: CVSS math strict-spec verification | CONFIRMED — calculator verified on 6 canonical vectors |
| 7 | Cross-cutting: progressive-disclosure line-budget check | CONFIRMED — SKILL.md at 201/500 lines |
| 8 | Phase 6 self-test agent | CORRECTED — F13 A:H → A:N (9.8 → 9.1 strict) |
| 9 | Phase 6 consistency agent | CORRECTED — AWS account count 8 → 9; SESSION cookie TTL re-flagged |

---

## Rounds 10–20 (structured single-facet scans)

**Round 10 — Correction-log completeness (F25/F4/F5):** CONFIRMED-NO-OMISSION — All three
correction lessons (F25 negative-control rule, F4 dynamic re-verification of the ATO/escalation
claim, F5 secret-valid ≠ token-mintable) are captured in methodology-lessons.md Lessons 1/7/10
and tied together by the meta-lesson at L200-202. Cross-cutting meta-lesson explicitly attributes
F4/F5 to "dynamic re-verification of impact claims."

**Round 11 — Curl executability:** CONFIRMED-NO-OMISSION — Every curl command runs without
shell syntax errors. Placeholder variables (WS_TOKEN, TOKEN, INSTALL_TOKEN, CSRF) are either
assigned at the top of their snippet or clearly marked as template values. One cosmetic gap:
the C2 reproduction snippet at http-auth-filter-testing.md:287 has `$CSRF` minted later (L427)
and a literal `webhook.site/<UUID>/` placeholder — it is clearly a template requiring an admin
session, not a broken command. FIDO1/FIDO2 snippets use proper quote nesting; bash arrays in
the five shell scripts all expand correctly.

**Round 12 — CVSS 4-pattern inflation check:** CONFIRMED-NO-OMISSION — All 12 live findings
in the authoritative Session-13 table (SUBMISSION-PACKAGE.md:2095-2105) score clean against
PR:L/UI:R/AC:H/narrative-impact inflation. F22 7.3, F24 6.5 (Pattern-4 example), F8 5.4
(Pattern-1 example), F3/F10 4.5 (Pattern-2 example), F18 3.2 (Pattern-3 example) all match
the skill's worked examples to the decimal. F13's residual Pattern-4 (A:H vs strict A:N) is
the single remaining inflation in the corpus's engagement totals and is explicitly flagged by
the skill's own F13 worked example (cvss-scoring-methodology.md:142-153).

**Round 13 — WORKED PoC completeness:** CORRECTED — bypass-catalogue.md sections K/L/M/N
omit row-level PoC patterns for F24 (reCAPTCHA/email-bomb 18-variant matrix), F12 (47.9×
size oracle), and F8 (install-token reuse), which currently live only in companion reference
files. Content exists — just not duplicated in the catalogue table. **Fix applied:** added
N-row for F24, M-row for F12 oracle, K-row for F8 install-token reuse.

**Round 14 — Negative falsifiability:** CORRECTED — killed-hypotheses.md degrades the corpus's
literal evidence for B12 (Rails portal), Spring Boot `/env` exposure, SCG actuator RCE, and
Spring4Shell to status-code-only or "did not work" phrasing, dropping the verbatim WAF body
signature (`{"detail":"Ensure the URL is valid","status":403,"title":"Access forbidden",
"type":"InternalServerErrorException.html"}`) and Rails response codes the corpus/raw probes
preserve. **Fix applied:** restored literal status + body signature to all four rows.

**Round 15 — RoE hygiene (customer-tenant trap):** NEW — The corpus itself has RoE violations
on `<customer>.acmeauth.example` (<customer>) and `<customer>.acmeauth.example` (<customer>), which the corpus
treated as AcmeAuth test tenants but are customer brands (active `POST /logs` returned HTTP 204 on
both — unauthenticated state-changing POST on out-of-RoE tenants). The skill's ethics-and-roe.md
§2 correctly classifies these as out-of-RoE, but does not warn about the *ambiguity trap*
(tenant names that look internal but are customer brands). **Fix applied:** added "customer-tenant
name confusion" warning to ethics-and-roe.md §2 with the <customer>/<customer> example as a forcing case.

**Round 16 — Token-chain reasoning:** CONFIRMED-NO-OMISSION — F8→F5/F7/F9 dormant-chain
reasoning (F8 surface untouched by the 2026-07-23/24 patch while all 6 IdP endpoints now return
403) is internally consistent across all 13 sessions, and Lesson 7 + Pattern 5 correctly
represent it without contradiction. Minor non-blocking drift: "5th mint" label in Lesson 3 may
undercount by one (Session 4 hypwo-81184668 vs Session 13 hypwo-42288d91 are both labeled "5th")
— does not break the chain. SESSION-cookie "sliding" TTL is uncorroborated by corpus but already
flagged as such in the skill.

**Round 17 — Version differential (LOAD-BEARING FIX):** CORRECTED — methodology-lessons.md
Lesson 8 (line 146) and REPORT-F13-CRITICAL-Submission.md both asserted v11.5.0 "introduced"
`UNAUTH_FIDO_PROTOCOL_ENDPOINTS_ENABLED` and that it "defaults enabled" — but the corpus's own
empirical feature-flag dump from sampleapp.dev (v11.5.0) at
session4-probes/sampleapp-features.json shows `releaseVersion:"11.3"` and
`"description":"Disabled by default"` with `enabled:false` on the v11.5.0 host. Both halves of
the skill's version differential contradicted the corpus's own evidence. **Fix applied:**
corrected Lesson 8 to "flag introduced in 11.3 (per its own releaseVersion metadata), disabled
by default, set to `false` on the v11.5.0 host — which is why `/rp/fido/get` returns 404 there."

**Round 18 — FIDO flow completeness:** CORRECTED — fido-webauthn-testing.md captures the CBOR
PoC, op=Auth 500 bug, and 47.9× oracle correctly, but omits the `/fido2/assertion/result`
"Missing rpAppId in non-conformance mode" ATO-completion blocker that the corpus documents as
the **third leg of the F13 blocker triad** (alongside attestation rpAppId-binding and CC-admin
per-rpAppId-binding blockers the skill already covers). **Fix applied:** added the third blocker
to the F13 chain documentation with the literal error string.

**Round 19 — Frida closed-loop:** CONFIRMED-NO-OMISSION — All 5 closed-loop elements (OkHttp
url-overload in-process hook, webhook.site UUID receiver, decisive okhttp/5.3.2 UA "not a system
component" load-bearing evidence, two-sided capture, direct Frida method invocation bypassing
auth-gated UI) are captured in Lesson 9 and the Mobile FIDO section at the same specificity as
the F3/F10 reports. The skill even captures a sixth element — error-code response-consumption
confirmation (`onFailure 1114073`) — that the corpus's closed-loop treats as implicit.

**Round 20 — Architecture inference soundness:** CORRECTED — §4 response-envelope fingerprinting
captures framework-layer `type`-field leaks (`/static/docs/jakarta/ws/rs/...`,
`ConstraintViolationException.html`) but omits the **application-internal Java package-path leak**
pattern carried by the same RFC 7807 `type` field — the `/static/docs/com/acmeauth/server/...` pattern
(F27, F16) that directly maps AcmeAuth's subsystem boundaries (`fido2.errorhandling`,
`featureflags.errorhandling`, `rp.errorhandling.fido2`). A reviewer following the skill alone would
miss F16/F27-class findings. **Fix applied:** added the application-internal-package-path leak
pattern to §4 with the F27 example.

---

## Summary

- **20 rounds completed** (9 from Phases 1/2/6 + 11 structured single-facet scans).
- **6 CORRECTED / NEW fixes applied** in this audit pass: Round 13 (catalogue rows),
  Round 14 (literal signatures), Round 15 (customer-tenant trap), Round 17 (UNAUTH flag
  attribution — load-bearing), Round 18 (3rd F13 blocker), Round 20 (Java pkg-path leak pattern).
- **7 CONFIRMED-NO-OMISSION** rounds: 10, 11, 12, 16, 19, plus the two pure-extraction rounds.
- Single load-bearing correction: Round 17 — the corpus's own empirical feature-flag dump
  directly refuted the skill's UNAUTH_FIDO_PROTOCOL_ENDPOINTS_ENABLED attribution.

---

## Round 21 — Policy revision: depth strengthening (post-audit)

User directive: "凭证可用才是漏洞" (a credential being usable is what makes it a vuln) + "深入组合漏洞链" (dig deeper into composite vuln chains). The original "Do not validate discovered credentials" rule was overly conservative — it conflated *analysis* (always legitimate) with *exploitation* (forbidden with real values), capping every credential finding at "Leak, CWE-200, Low" regardless of true chain potential.

**Applied revision (4 changes):**

1. **SKILL.md — Integrity discipline rewritten.** Replaced blanket "Do not validate discovered credentials" with the **three-tier framework**: Tier 1 (static decode/analyze, default-allowed), Tier 2 (dynamic read-only validation, requires user confirmation per endpoint group), Tier 3 (state-changing/destructive use, forbidden with real values, placeholder mandatory). The shift: from "stop at the leak" to "walk the chain as far as scope and Tier rules allow, then document the boundary."

2. **SKILL.md — Phase 0 pragmatized.** Authorization check now runs once per session + on target-class change, not on every action. Trusts the user's single explicit authorization declaration; stops re-litigating it. What this does NOT relax: customer-tenant refusal, destructive-endpoint placeholder rule, credential Tier-3 prohibition, no-remote-push — those remain absolute.

3. **methodology-lessons.md — Lesson 11 added.** "Credential Chain Analysis: From 'Leak' to 'Validated, Reachable, Exploitable'" — the 5-stage framework (Decode → Enumerate → Validate → Map Reach → Chain) with the AcmeAuth F8 install-token worked example showing how Stage 4 reach-mapping turned an F8 "token leak" (Low) into the anchor for the F5/F7/F9 Critical authz-bypass cluster.

4. **report-structure.md — Vulnerability-chain synthesis section added.** When/how to write a chain report in addition to individual reports, with three worked AcmeAuth examples (pre-patch F8+F5/F7/F9 dormant chain; F12+F13 flagship Critical; F22+FIDO1-completion blocked-future-work chain) and the 5-step synthesis methodology (inventory → output-input matching → precondition collapse → tier check → honest blockage documentation).

**What this revision did NOT change (deliberate non-changes):**

- **Authorization requirement itself.** Not removed. The legal line (CFAA / 刑法285 / CMA) is not a skill-policy choice. Phase 0 was pragmatized (less repetitive confirmation), not deleted.
- **Customer-tenant refusal.** Not relaxed. Customer brands (`<customer>`, `<customer>`, `vault-*`, etc.) remain out-of-RoE regardless of wildcard scope; this protects the user legally.
- **Destructive-endpoint placeholder rule.** Not relaxed. `ZZFAKE` / `nobody@xyz.com` remains mandatory for write/delete/lateral-movement paths.
- **No-remote-push rule.** Not relaxed. Per AGENTS.md §5.1 (user's own hard rule). Push is irreversible (cache, forks, indexes retain content); for git-workflow testing, use local multi-remote setups (`git remote add test /local/path`), never a real remote. If the user explicitly directs a change to AGENTS.md §5.1 with acknowledgment of irreversibility, that change goes in AGENTS.md, not in this skill.

**Net effect on engagement output.** With this revision, the same AcmeAuth engagement would now produce **2-3 chain reports in addition to the standalone finding reports** (the F8+F5/F7/F9 dormant chain, the F12+F13 flagship chain, and possibly an F22+follow-on chain), lifting several Medium-tier findings into composite-Critical narratives. Individual CVSS scores unchanged; the chain reports score the end primitive, not the average of components.
