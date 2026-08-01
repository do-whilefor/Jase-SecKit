# CVSS 3.1 Strict Scoring Methodology

CVSS is the difference between a defensible finding set and an inflated one. Score against the FIRST.org 3.1 spec formula, never against narrative.

**The engagement's honesty lesson:** Session 13 re-scored all 11 live findings against the spec and produced **4 severity downgrades + 1 upgrade**. The 4 downgrades came from 4 recurring inflation patterns — all documented below so you can catch them in your own scoring.

---

## The spec formula (FIRST.org CVSS 3.1)

### Exploitability metrics

```
Exploitability = 8.22 × AV × AC × PR × UI
```

Where:

| Metric | Value | Factor |
|---|---|---|
| **AV** (Attack Vector) | Network | 0.85 |
| | Adjacent | 0.62 |
| | Local | 0.55 |
| | Physical | 0.2 |
| **AC** (Attack Complexity) | Low | 0.77 |
| | High | 0.44 |
| **PR** (Privileges Required) — Scope Unchanged | None | 0.85 |
| | Low | 0.62 |
| | High | 0.27 |
| **PR** (Privileges Required) — Scope Changed | None | 0.85 |
| | Low | 0.68 |
| | High | 0.5 |
| **UI** (User Interaction) | None | 0.85 |
| | Required | 0.62 |

### Impact metrics

```
ISCBase = 1 − (1 − C) × (1 − I) × (1 − A)
```

Where C/I/A factors are:

| C/I/A | Factor |
|---|---|
| High | 0.56 |
| Low | 0.22 |
| None | 0 |

**Impact (Scope Unchanged):**
```
Impact_S_U = 6.42 × ISCBase
```

**Impact (Scope Changed):**
```
Impact_S_C = 7.52 × ISCBase − 3.25 × (ISCBase − 0.029) − 3.25 × ISCBase²
```

### Base score

```
BaseScore_S_U = roundup( min(Impact_S_U + Exploitability, 10) )            if Impact_S_U > 0
BaseScore_S_C = roundup( min(1.08 × (Impact_S_C + Exploitability), 10) )   if Impact_S_C > 0
```

If Impact ≤ 0, BaseScore = 0.

### roundup()

```
roundup(x) = ⌈x × 10⌉ / 10    (mathematically; not a naive round)
```

The implementation must avoid floating-point drift — multiply by 10, take the ceiling, divide by 10.

### Severity bands

| Score | Severity |
|---|---|
| 0.0 | None |
| 0.1 – 3.9 | Low |
| 4.0 – 6.9 | Medium |
| 7.0 – 8.9 | High |
| 9.0 – 10.0 | Critical |

---

## The four inflation patterns to strip

These were the recurring errors in the AcmeAuth session reports. Run a "precondition reality check" on every finding before assigning severity.

### Pattern 1 — PR:L treated as PR:N

**Concrete.** F8 (install-token reuse) was scored "High" by implicitly assuming the install token was obtainable without auth. The install token is only obtainable via legitimate device enrollment. Correcting PR:N → PR:L dropped the score from would-be ~7.5 to **5.4 (Medium)**.

**Rule.** Ask: did the attacker need a prior credential to reach the vulnerable code path? If yes — even a low-priv one — PR is at least Low. PR:N means truly anonymous.

### Pattern 2 — UI:R treated as UI:N

**Concrete.** F3 (AcmeAuthLink SSRF) and F10 (QR rpUrl injection) were both "Medium-High." Both require the victim to click a link or scan a QR. UI:R weighs 0.62 vs 0.85 for UI:N in the Exploitability factor — this cap dropped both to **4.5 (Medium)**.

**Rule.** Ask: must a human click/scan/interact for the exploit to fire? If yes, UI:R. UI:N means the exploit fires without any user action (e.g., a stateless unauthenticated SSRF).

### Pattern 3 — AC:H treated as AC:L

**Concrete.** F18 (Host header injection → Okta redirect_uri) was "High." RFC 7230 forbids clients from setting arbitrary `Host`, and modern browsers enforce this. The attack requires a MITM position on a proxy/CDN that forwards attacker-supplied Host. AC:H (factor 0.44 vs 0.77) dropped it to **3.2 (Low)**.

**Rule.** Ask: does the attack require a special condition outside the attacker's control (intermediary position, race condition, specific target configuration, victim on same subnet)? If yes, AC:H. AC:L means the attack works reliably on a standard internet connection.

### Pattern 4 — Narrative impact over direct C/I/A

**Concrete.** F24 (Affirm email-bomb) was "High" on narrative ("embarrassing for a passwordless vendor"). CVSS strictly counts impact dimensions — C:N (no data read), so it caps at **6.5 (Medium)**.

**Rule.** Ask: what DIRECT confidentiality, integrity, or availability impact does this vuln cause? CVSS does NOT credit "prerequisite for another vuln" — F12 (highest-impact info leak because it's a direct prerequisite for F13) still scores 5.3 because it only leaks C:L directly. The downstream F13 chain does not boost F12's score.

### Pattern 5 — Scoring persistence primitives (live vs dormant)

**Concrete.** Two persistence primitives in the engagement scored very differently because one is *live* and one is *dormant*:
- **F13 (live):** attacker can complete the credential injection and persist a credential they control onto a victim's account. The credential is *usable* in some authentication path (even if ATO is blocked by rpAppId binding, the credential itself is real). Score: **I:H** — the integrity of the victim's credential set is genuinely compromised.
- **F8 (dormant):** the install token can mint unlimited WORKSTATION Bearer tokens, but every downstream endpoint the token reaches is patched. The token is *not currently usable* for anything. Score: **I:L** — it's a latent primitive, current impact is hygiene/persistence only.

**Rule.** For a persistence primitive, ask: **is the planted credential / minted token usable in any authentication path right now?**
- **YES, fully usable** (attacker can authenticate as victim) → I:H AND score the cheapest auth path it enables as C:H (you've effectively stolen credentials).
- **YES, but partial** (credential persists, but path is blocked at a downstream gate — rpAppId binding, scope check, etc.) → I:H (the credential is real and persisted) but do NOT credit the blocked downstream path. This is the F13 case → I:H, A:N.
- **NO, dormant** (token mintable but all downstream endpoints patched) → I:L. Follow Lesson 7: score at current CVSS, retain as dormant primitive with "re-arms if any future gap appears" note.

The test: "if I stopped testing right now and shipped this report, would an attacker be able to do anything malicious with this primitive in the next 24 hours?" If yes → at least I:H. If no → I:L and document the dormancy explicitly.

---

## Worked examples (verified)

### F22 — Unauthenticated FIDO1 UAF state creation
**Vector:** `AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L`

- ISCBase = 1 − (1−0.22)(1−0.22)(1−0.22) = 1 − 0.475 = 0.525
- Impact (S:U) = 6.42 × 0.525 = 3.37
- Exploitability = 8.22 × 0.85 (AV:N) × 0.77 (AC:L) × 0.85 (PR:N) × 0.85 (UI:N) = 3.89
- BaseScore = roundup(min(3.37 + 3.89, 10)) = roundup(7.26) = **7.3 High** ✓

### F13 — Unauth FIDO2 credential injection
**Strict vector:** `AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N` = **9.1 Critical**
**Original submission vector:** `AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H` = 9.8 Critical

The original report scored A:H; on strict review **A:N is more defensible** — credential persistence does not, by itself, deny service to the victim (the attacker cannot authenticate as them due to the rpAppId binding). The headline Critical severity survives either way.

- ISCBase (strict A:N) = 1 − (1−0.56)(1−0.56)(1−0) = 1 − 0.1936 ≈ 0.81
- Impact (S:U) = 6.42 × 0.81 = 5.18
- Exploitability = 8.22 × 0.85 × 0.77 × 0.85 × 0.85 = 3.89
- BaseScore = roundup(min(5.18 + 3.89, 10)) = roundup(9.07) = **9.1 Critical** ✓

This revision is itself a CVSS-strictness meta-lesson: the original F13 A:H was a mild inflation that survived into the submission. A triage reviewer applying Pattern 4 would catch it. Score strictly the first time.

### F8 — Install token infinite reuse (post-patch, dormant)
**Vector:** `AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:L/A:N` (PR:L because install token requires prior device enrollment)

- ISCBase = 1 − (1−0.22)(1−0.22)(1−0) = 1 − 0.6084 = 0.39
- Impact (S:U) = 6.42 × 0.39 = 2.50
- Exploitability = 8.22 × 0.85 (AV:N) × 0.77 (AC:L) × 0.62 (PR:L) × 0.85 (UI:N) = 2.84
- BaseScore = roundup(min(2.50 + 2.84, 10)) = roundup(5.34) = **5.4 Medium** ✓

### F18 — Host header injection → Okta redirect_uri
**Vector:** `AV:N/AC:H/PR:N/UI:R/S:C/C:L/I:L/A:N` (AC:H because needs intermediary to forward Host; UI:R because victim must visit; S:C because crosses Keycloak → Okta trust boundary)

- ISCBase = 1 − (1−0.22)(1−0.22)(1−0) = 0.39
- Impact (S:C) = 7.52 × 0.39 − 3.25 × (0.39 − 0.029) − 3.25 × 0.39² = 2.93 − 1.17 − 0.49 = 1.27
- Exploitability = 8.22 × 0.85 × 0.44 (AC:H) × 0.85 (PR:N, S:C) × 0.62 (UI:R) = 1.62
- BaseScore = roundup(min(1.08 × (1.27 + 1.62), 10)) = roundup(1.08 × 2.89) = roundup(3.12) = **3.2 Low** ✓

### F24 — Affirm email-bomb (reCAPTCHA bypass for @acmeauth.example)
**Vector:** `AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:L` (C:N because no data read; I:L because unwanted emails sent; A:L because mailbomb DoS)

- ISCBase = 1 − (1−0)(1−0.22)(1−0.22) = 1 − 0.6084 = 0.39
- Impact (S:U) = 6.42 × 0.39 = 2.50
- Exploitability = 3.89 (same as F22)
- BaseScore = roundup(min(2.50 + 3.89, 10)) = roundup(6.39) = **6.5 Medium** ✓

---

## How to use the calculator script

```bash
node ~/.zcode/skills/web-vulnhunt-methodology/scripts/cvss31-calculator.js "AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L"
# Output:
#   Vector:  AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L
#   Score:   7.3
#   Severity: HIGH
#   Computation:
#     ISCBase = 0.525
#     Impact  = 3.37 (Scope Unchanged)
#     Exploit = 3.89
#     Base    = roundup(min(3.37 + 3.89, 10)) = 7.3
```

---

## Common CVSS pitfalls

1. **Don't use the CVSS 3.0 S:C formula.** CVSS 3.0 used `7.52 − 12.96 × (1−C)(1−I)(1−A) − 3.25 × (1−C−I−A)` which is wrong for 3.1. Always use the 3.1 formula above.

2. **Don't use naive `Math.round`.** Always use `Math.ceil(x * 10) / 10` to implement roundup.

3. **Don't conflate PR factor for S:U vs S:C.** PR:L is 0.62 for S:U but 0.68 for S:C. PR:H is 0.27 for S:U but 0.5 for S:C. The calculator script handles this automatically.

4. **Don't credit downstream chains.** F12 enables F13 but scores 5.3, not 9.8. CVSS scores the direct impact of *this* vuln, not its blast radius across other findings.

5. **Don't credit "prerequisite for another vuln" in C/I/A either.** If a vuln discloses info that enables a separate ATO, that's C:L for the disclosure, not C:H for the eventual ATO. The eventual ATO has its own finding with its own score.

6. **Don't include Temporal/Environmental metrics in the Base score.** Base is what you submit. Temporal (E:*, RL:*, RC:*) and Environmental (CR:*, IR:*, AR:*, MAV:*, etc.) are modifiers reported separately if at all.

7. **When in doubt, score conservatively.** A defensible Medium is better than an inflated High that triage rejects. The researcher's reputation compounds across submissions.

---

## Honesty meta-rule

CVSS strict scoring is itself a defense-in-depth for the researcher. The engagement's final honest picture — 1 Critical (F13, partially mitigated) + 1 High (F22, the only "clean High with no precondition caps") + 8 Medium + 1 Low — is CVSS-defensible precisely because the inflation was stripped out rather than left in. **Triage reads the vector string and checks the math.** If they catch an inflation pattern you missed, every other finding in your submission loses credibility. Score strictly the first time.
