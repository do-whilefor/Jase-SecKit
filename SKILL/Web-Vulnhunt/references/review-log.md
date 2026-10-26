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

---

## Round 22 — Policy revision: operator-scope authorization model

User directive: "用户输入就是授权范围" (the user's input IS the authorization scope). The Round 21 trust model (one declaration per session, re-confirm on target-class change) still demanded an explicit authorization declaration and kept customer-tenant refusal gates. The new model removes the gate entirely: the target and intent stated in the user's request define the working scope — the same operator-responsibility model as nmap / Burp / sqlmap. The operator owns the lawfulness of the engagement; the skill owns testing quality.

**Applied revision:**

1. **SKILL.md** — description and the line-10 banner now state "the user's request defines the working scope" instead of "authorized use only / confirm scope before any active test". Phase 0 rewritten from "Scope and integrity gate" to "Scope intake": record the scope from the user's input as note-taking (feeds the report's scope section), no confirmation prompts, no out-of-RoE refusal steps. Tier 2 credential validation no longer requires per-action/per-endpoint-group confirmation. "Document refusals" → "Document boundaries". Customer-tenant note reframed as third-party ownership identification.
2. **ethics-and-roe.md** — retitled "Ethics & Testing Discipline". §1 replaced: "Authorization is the gate / No authorization, no active test / ask the user before any active test" → "Scope comes from the operator / The user's input is the authorization scope", with the legal-responsibility line assigned to the operator. §2 retitled "Aim verification: know what you are hitting" — the customer-tenant lists stay as the engagement's factual record; the hard rule changes from "refuse the active probe and document the refusal" to "verify ownership, exclude assets the user did not point at, note the identification". §3 retitled "Testing hygiene and out-of-toolkit techniques"; the credential bullet now defers to the Tier framework instead of "report and stop". §4.8 "Document refusals" → "Document boundaries".
3. **methodology-lessons.md** — Lesson 4/5 codified rules reframed from refusal directives to ownership identification + aim verification; Lesson 11 Stage 3/4 no longer gated on per-endpoint-group confirmation (read-only discipline retained); chain stop-limits now "Tier-3 placeholder boundary, missing dependency".
4. **report-structure.md** — PoC hygiene reframed (test tenant or operator-designated target; sanitize third-party identifiers before the report leaves local control); chain Tier check no longer references RoE; blockage list updated.
5. **osint-asset-discovery.md** — customer-tenant table note reframed as third-party ownership identification.
6. **Scripts** — "Authorized testing only." headers → "Scope = the targets the operator names. Hygiene rules: references/ethics-and-roe.md."

**Deliberate non-changes:**

- **Tier-3 placeholder rule.** Destructive paths still use placeholder targets (`ZZFAKE`, `nobody@xyz.com`, `0`-prefixed random) — testing hygiene that protects the target's data and keeps PoCs reproducible, not an authorization gate.
- **Bounded-volume pacing.** Hard caps (~20–30 requests per hypothesis, sequential pacing) stay — probing discipline, not permission.
- **Negative control, CVSS-strict scoring, honest blockage documentation** — untouched methodology core.
- **No-remote-push rule (AGENTS.md §5.1)** — untouched; it governs this repo's git workflow, not target authorization.
- **Historical records** (killed-hypotheses.md, engagement narratives in methodology-lessons.md / ethics-and-roe.md) keep the engagement's actual refusals verbatim — they record what happened, not what future sessions must do.

---

## Round 23 — Transferability pass: class gaps, cold-start runbook, reading routing

User directive (post-Round-22): fix the residual ethics contradiction, fill the zero-coverage web-bounty vuln classes, promote the "Pattern → generic recipe → instance" three-part form to all references, add a cold-start runbook, add per-Phase reading routing, and sweep the small defects. Keep the operator-scope authorization model throughout.

**Class-gap verdict (verified):** the ethics contradiction (ethics §3 "Validating discovered credentials … report and stop" vs the Round-21 Tier framework) was **already fixed in Round 22** — §3's credential bullet now defers to the Tier framework; grep confirms zero residual "report and stop" text. No further edit needed.

**Applied revision:**

1. **Five new class references** (each Pattern → generic recipe → Instance, honest about zero/low corpus coverage, no authorization gates):
   - `race-conditions.md` — last-byte sync / single-packet attack, double-exploit + limit-overdraw taxonomy, serial-baseline-as-negative-control rule, bounded volume (~20–30 req/hypothesis), killed-hypothesis signatures.
   - `graphql-testing.md` — endpoint discovery, schema mapping incl. field-suggestion mining, token × resolver authz matrix, batching/aliasing (links to race class), depth/cost, mutation Tier discipline, subscriptions/APQ.
   - `cache-poisoning.md` — cache detection, unkeyed-input mining, marker-based bounded poisoning, web cache deception (bridged to the §A ladder), key-normalization disagreement; corpus hooks: F18 Host reflection, `/static/docs/**` templates, CloudFront/S3 deny XML.
   - `jwt-jose-attacks.md` — alg confusion, kid injection, jku/x5u → composes with the C2/C4 `jwksUrl` SSRF sinks, claim confusion (F7 token-type matrix as the worked instance), replay/revocation windows (F8 unexpiring install token as the dormant-primitive case), bounded by the no-key-reversing hygiene rule.
   - `client-side-dom.md` — bundle source→sink sweep incl. `bypassSecurityTrust*` (Angular, the corpus's framework), client-side prototype pollution with gadget-anchored detection, postMessage/WebView bridge; corpus anchor: the already-downloaded `loggedIn.js` bundle.
2. **`cold-start-runbook.md` added** — first 60 minutes on an unknown target: scope record → sinkhole → CT/hostnames → surface map → envelope fingerprint → primitive inventory, with decision gates G1–G4 and a route table into the class references; framework-agnostic notes for non-Spring/non-FIDO targets.
3. **Three-part form promoted**: `bypass-catalogue.md` gained §0 "Generic bypass recipe" (recipe layer above the instance tables); `osint-asset-discovery.md` gained a 10-step "Generic OSINT recipe" ahead of the Master Table. Instance tables retained verbatim — they are the evidence layer, not bloat.
4. **SKILL.md reading routing**: every Phase now carries **Read / Skip** lines to bound agent context budget (Phase 2 routes per hypothesis class; scoring/report references explicitly deferred to Phase 4); Phase 2 loop gained step 7 (run the class recipe before improvising); the on-demand table gained the 6 new files.
5. **Small fixes**: SKILL.md "an documented" → "a documented"; `fido-webauthn-testing.md` "Theacmeauth-login-nonce" → "The acmeauth-login-nonce"; `cvss-scoring-methodology.md` hardcoded `~/.zcode/skills/...` path → repo-relative `scripts/cvss31-calculator.js`; `authz-matrix.sh` + `patch-verify.sh` gained fail-fast dependency checks with Windows Git Bash install hints, `sinkhole-detector.sh` echoed CT commands gained a jq-free python3 fallback, authz-matrix Requirements line corrected (jq not required); `cve-watchlist.md` gained the hard entry rule (advisory reference + version-check command + concrete test, else cut) and the detail-less CVE-2026-47825 stub was cut per that rule (also dropped from bypass-catalogue's watchlist line).

**Deliberate non-changes:** operator-scope model (Round 22) untouched and carried into every new file; hygiene rules (Tier-3 placeholders, bounded volume, negative controls) restated in the new class files because they are testing discipline, not authorization gates; instance tables/engagement history in both restructured references preserved verbatim.

---

## Round 24 — Script toolkit rebuild: the 13-script system

User directive: rebuild the script toolkit deleted in the corpus restructure, per the inventory table (sweep-all / recon / dormant-watch / selftest / hunt / tenant-diff / body-mutator / bundle-diff / oracle-miner / hunt-ledger / valid-body-generator / ratelimit-probe / chain-matcher). Operator-scope model carried throughout — every script header states "Scope = the targets the operator names. Hygiene rules: references/ethics-and-roe.md."

**Architecture (the scripts interlock around the ledger):**
- **Ledger hub:** `hunt-ledger.sh` (TSV ledger; `add` REFUSES hypotheses without a falsification design — Core principle 1 enforced mechanically; `next` = highest-value open) ← `hunt.sh` (priority scheduler with working brief) ← `sweep-all.sh --ledger` (auto-records anomalies A1–A5 as hypotheses).
- **Discovery:** `recon.sh` (sinkhole → CT jq-free → vault-prefix → cloud error-leak → live-probe; emits the cold-start surface map) + `bundle-diff.js` (bundle diff = patch-scope enumeration).
- **Testing:** `sweep-all.sh` (four-way envelope discriminator at inventory scale; A1 = the 78:1 rule), `oracle-miner.sh` (built-in negative control; ≥3× same-status size ratio decisive — the F12 class must not downgrade to WEAK-SIGNAL), `ratelimit-probe.sh` (hard 30-request cap; LIMITED@k vs UNLIMITED), `tenant-diff.sh` (OUTLIER = per-tenant patch gap; SHARED = shared backend), `body-mutator.js` + `valid-body-generator.js` (schema-valid bodies kill the empty-`{}` 400 false positive; `--placeholder` carries Tier-3 into generated bodies), `authz-matrix.sh` (existing).
- **Monitoring/reporting:** `dormant-watch.sh` (STRICTLY GET-only — refuses mutating configs; drift fingerprinting for dormant primitives), `chain-matcher.js` (OUTPUTS × PRECONDITIONS matching with honest unsatisfied-precondition boundaries), `patch-verify.sh`, `negative-control-harness.sh`, `sinkhole-detector.sh`, `cvss31-calculator.js` (existing).
- **`selftest.sh`** validates the toolkit offline (syntax, reference wiring, ledger round-trip, JS fixtures, usage paths) and encodes the Round-22 invariants as executable assertions (no authorization-gate language regressions; hygiene rules present).

**Integration:** SKILL.md Reusable-scripts table (6 → 19 entries, workflow-ordered), Phase 1/2/3 hooks (recon → sweep-all → ledger/brief → patch-scope trio), cold-start runbook M5–20 and M50–60 wired to recon.sh and hunt-ledger/hunt.

**Windows Git Bash hardening found by the live smoke test** (local HTTP server as target — own infra):
1. `python3` often absent on Windows — all scripts resolve `python3` → `python` → `py`; fail-fast with install hints when none.
2. **MSYS2 argv conversion:** a bare `/` argument becomes the Git install root when spawning native binaries — endpoint extraction now passes spec/prefix via env vars with the leading slash stripped and re-attached inside python.
3. **MSYS2 env-value conversion** converts env values starting with `/` too (deeper than documented) — hence the strip-and-re-attach rather than plain env passing.
4. **Windows python CRLF:** `print()` emits `\r\n` into intermediates → every curl URL carried a trailing `\r` → all probes 000; fixed with `sys.stdout.reconfigure(newline="\n")` + defensive `${path%$'\r'}` on read.
5. `/tmp`-style file args to native interpreters go through `cygpath -w` (`nativ_path`).
6. `valid-body-generator.js` accepts MSYS-mangled path args and paths without leading slash; sweep-all `gen_body` falls back to `{}` on the generator's `_note` object and flattens notes to one line so the results TSV stays parseable.

**Verified:** selftest 60/60 PASS; live run of sweep-all against a local mock (12 endpoints: 6-strong uniform-403 class, SPA fallback with 405 discriminator, unauth POST) produced correct envelope classification and auto-recorded A1 (78:1) + A4 (unauth-write) anomalies; oracle-miner detected a 183× same-status size oracle (ORACLE-DETECTED); ratelimit-probe returned UNLIMITED within cap; ledger round-trip incl. falsification-refusal.

**Deliberate non-changes:** authorization gates — none added anywhere; hygiene is enforced as bounded volume (caps in ratelimit-probe/sweep-all/race recipe), Tier-3 placeholders (valid-body-generator/body-mutator placeholder modes), and mandatory negative controls (oracle-miner), which are testing discipline, not permission checks.

---

## Round 25 — bypass-catalogue §O (O0–O8): the current-generation edge battery

User directive: extend bypass-catalogue.md with nine subsections O0–O8 — deformation probes, the differential classics, the post-TE.TE frame layer, invisible bodies, verb layer, authority/hop confusion, body-structure differentials, cache-as-oracle (cross-ref), and the meta-method.

**Applied revision:**

1. **§O added to `bypass-catalogue.md`** (after §N, before Summary statistics), positioned honestly: §A–§N are the corpus record; §O is the open battery whose outcomes land in the differential matrix and `killed-hypotheses.md`, with corpus ties marked where they exist (§A/§I = partial normalization fingerprint feeding O0; §C = the dead TE.TE ladder motivating O2; §B's 401 = the verb-irrelevance instance in O4; F18 = the Host-parsing anchor in O5).
   - **O0** — normalization fingerprint (payload-free deformation set), 404-vs-403 routing-position mapping, low-traffic rule-engine timing fingerprint (rule-set generation without a single block, jitter-controlled), and the hard FP trap: CDN/POP normalize+cache too — cache-buster and second-egress re-test mandatory.
   - **O1** — the 8 differential classics, each as variant + discriminating signal + **per-variant negative control** (backslash separator, semicolon asymmetry, query `;` split, trailing-slash matcher gap, dot-segment collapse point, `%3F/%23` structural encoding, decode-depth ladder, empty-segment merging). Rule: a flip without a clean control is noise, not a finding.
   - **O2** — the modern frame layer (CL malformations incl. hex/plus/comma-list, bare-LF chunked, trailer smuggling, H2.CL downgrade desync, h2C upgrade bypass). Canary discipline stated as a hard rule: desync confirmed only via self-contained canaries (`GET /zcanary-<rand>` to your own receiver); cross-user pollution is a separate, explicitly-directed experiment — never an implicit side effect.
   - **O3** — gzip body, charset lies, multipart confusion, inspection-window binary search; 415 recorded as negative, not "almost".
   - **O5** — absolute-URI request line, `@`-component Host parsing, underscore/dash header ambiguity (nginx `underscores_in_headers` tripartition), hop-by-hop stripping ("your whitelist becomes their bypass").
   - **O6** — duplicate keys, `\u002f` escapes, number-form literals, depth/size-limit differentials — mechanized (see 2).
   - **O7** — cache-as-WAF-oracle as a side channel for verdicts you don't trigger directly; cross-references `cache-poisoning.md` without repeating it.
   - **O8** — the meta-method and the reusable artifact: `<target>-diffmatrix.tsv` (`variant / edge-verdict / origin-verdict / route-verdict`), fire only at divergence points, negatives into killed-hypotheses, matrix transfers to the next same-stack target.
2. **`body-mutator.js` extended for O6**: new `number-forms` profile (text-level literals 1e0/1.00/1e2/-0/1e999/2^53+1 — `JSON.stringify(1e999)` is `"null"`, so literals are spliced post-serialization) and `json-escapes` profile (`/` → `\u002f`, valid JSON text). Also **fixed a latent Round-24 bug**: `dup-keys` produced invalid JSON (colon displacement) — rewritten as line-splice; all 23 mutants across profiles now parse as valid JSON (verified).
3. **SKILL.md** Phase-2 routing updated: filter/403 wall → `bypass-catalogue.md` §0 **+ §O**.
4. File furniture updated: intro notes §O's provenance and where its outcomes go; Summary statistics gained the "§O: open battery, not corpus-counted" line; takeaways gained #6 (the differential matrix as the transferable artifact).

**Verification:** `node --check` clean; profile smoke test — `number-forms.4` emits literal `1e999`, `json-escapes` emits `\u002f`-escaped body, all mutants JSON-valid; selftest 60/60 (invariants intact — no gate language introduced by §O; O2's canary discipline is hygiene phrasing, consistent with the operator-scope model).

**Deliberate non-changes:** instance tables §A–§N untouched; §O contains no authorization gates — its hard rules (canary discipline, cache-buster re-test, negative controls) are evidence-quality discipline, not permission checks.

---

## Round 26 — §O escalation: more aggressive, wider, automated

User directive: make the bypass battery more aggressive. Applied as depth + breadth + automation, with the two lines that never move (no DoS instrument, canary-only desync) held as designed in Round 25.

**Coverage escalations (bypass-catalogue.md §O in place):**
- **O0** — passive zero-request fingerprinting added (h2 SETTINGS/JA4/ALPN/CT-issuer/CNAME/header-case quirks) + unknown-verb probe (`PROPFIND`/`TRACE`/`CONNECT`/`ZPROBE`) as the O4 bridge.
- **O1** — 8 → **16 differential classics**: unicode case-folding (U+212A/İ), control-char whitespace (%0B/%0C the chronically unfiltered), leading matrix segment, protocol-relative request target (`//x` = authority per RFC 3986), asterisk/unusual targets, duplicate Host (first-vs-last), exotic authority forms (IPv6-mapped/decimal/octal/trailing-dot/empty-port, receiver-confirmed), raw `?`/`#` bytes in-path. Every row keeps its per-variant negative control.
- **O2** — 4 new frame vectors: CL.0 desync, client-side desync (browser+own-receiver confirmation loop), h2 pseudo-header abuse (duplicate `:path`, `:method` casing, pre-pseudo regular headers), 0-length chunk + websocket-downgrade smuggling.
- **O3** — 5 new: stacked content-encoding, lenient-JSON gap (JSON5/comments/trailing commas/NaN — the parse-failure bypass), BOM prefix, trailing garbage, TLS 1.3 early-data replay differential.
- **O4** — server-level verbs + h2 pseudo-method casing.
- **O5** — duplicate Host, XFF chain trust (leftmost/rightmost), RFC 7239 `Forwarded` vs `X-Forwarded-*` family mismatch, Via injection, exotic authority forms.
- **O6** — homoglyph key collisions + lenient-JSON/BOM/trailing-garbage cross-refs.
- **O7** — cache-key divergence as a bypass amplifier (Vary misuse, Accept-Encoding variants, header case/order: cached-PASS under a variant key while the bare key caches 403).
- **§O9 (new) — Execution profiles**: aggression scaled to blast-radius control. STAGING/OPERATOR-CONTROLLED = full throttle (`--delay-ms 0`, parallel, exhaustive ladders); PRODUCTION = paced full coverage (coverage identical, throughput controlled — "aggressive ≠ fast", §A's quiet case-variant is the model). Never moves on either profile: canary-only desync, no availability/load testing, no cross-user pollution without explicit direction, Tier-3 placeholders. Aggression is a targeting decision, not a paperwork gate.

**Automation: `scripts/edge-mapper.sh` (new).** Runs the whole O0+O1 battery in one command: ~24 deformations × blocked/allowed twins, verb oracle, unknown-verb probe, built-in cache-buster FP control on every probe; classifies divergent cells (BYPASS-CANDIDATE = filter verdict flipped to 2xx/3xx, VERDICT-SHIFT, RESPONSE-SHIFT, ROUTE-SPLIT, VERB-OPEN) and emits `<host>-diffmatrix.tsv` + `divergent.txt`. Python-core (http.client) — immune to the MSYS argv/env conversion and CRLF issue class from Round 24; args travel via env with leading slashes stripped. SKILL.md scripts table + Phase-2 loop wired; selftest usage-check added.

**Verified (live, local mock edge with an exact-match blocklist filter):** 44 divergent cells auto-identified — 9 BYPASS-CANDIDATEs on the blocked twin (trail-slash, dot-self/dot-inside/dot-overroot/dot-enc/dot-tail/dot-lead, enc-slash both cases — all 403→200 through origin-side decoding the edge didn't apply), ROUTE-SPLITs on the allowed twin, VERB-OPEN (OPTIONS answered 200 over a 403 path — the filter doesn't cover verbs). selftest 62/62.

**Deliberate non-changes:** the two hard lines from Round 25 held — the battery gets more aggressive through coverage, automation, and execution profiles, not by becoming a DoS instrument or by loosening desync canary discipline; per-variant negative controls stay on every new O1 row; operator-scope model untouched.

---

## Round 27 — Refusal-content consolidation into restrictions.md

User directive: take the remaining refusal/red-line content in Web-Vulnhunt (the Web-Vulnhunt analog of the five restriction categories audited in flounder), move it verbatim into ONE file, delete it from the original positions, and reference it via links — preserving the refusal content rather than deleting it.

**Applied revision:**

1. **`references/restrictions.md` (new)** — the single home for all refusal-bearing rules, organized in 8 sections with source attribution: §1 out-of-toolkit techniques (ethics §3), §2 destructive paths & credential tiers (SKILL.md Integrity discipline + ethics §3 bullet), §3 data handling (ethics §5), §4 git discipline (ethics §6), §5 reporting/disclosure/publication (ethics §7 + cache-poisoning live-payload clause), §6 desync canary discipline (bypass-catalogue §O2), §7 execution-profile hard lines (§O9), §8 bounded volume & pacing (race/graphql playbooks). All moved verbatim.
2. **Original positions deleted, linked:** ethics-and-roe.md §3/§5/§6/§7 → one-line section stubs + bottom link; SKILL.md Integrity discipline section deleted → bottom link + reference-table row + Phase 0 enumeration now points at restrictions.md; bypass-catalogue §O2 canary paragraph and §O9 hard-lines paragraph → pointers + bottom link; jwt-jose §6 → bottom link; race-conditions step 5 → removed (renumbered) + bottom link; graphql step 6 → removed (renumbered) + step-5 clause trimmed + bottom link; cache-poisoning step-3 live-payload clause → pointer + bottom link; report-structure placeholder/PII bullets → removed + bottom link.
3. **Pointers kept accurate:** all 15 script headers now read "Hygiene rules: references/restrictions.md"; selftest invariants updated — ZZFAKE/Tier-3 check now asserts restrictions.md content, new check asserts SKILL.md links restrictions.md, ethics §1 model check still points at ethics-and-roe.md (sed collateral fixed).
4. **Untouched by design:** the operator-scope model (ethics §1, SKILL.md Phase 0/banner/frontmatter); ethics §2 aim verification, §4 evidence discipline, §8 forcing function (methodology, not refusal); worked examples that merely USE placeholders (http-auth-filter-testing ZZFAKE PoC line, methodology-lessons narratives); race step-5 CVSS anti-inflation note (scoring discipline).

**Verified:** selftest 49/49; residual scan shows no refusal-bearing rule text outside restrictions.md (remaining matches are pointers, worked examples, or scoring discipline).

**Deliberate non-changes:** the operator-scope model statement everywhere; the restrictions' wording (moved verbatim, nothing weakened); review-log history.
