# JWT / JOSE Attack Battery — alg, kid, jku/x5u, Claim Confusion, Replay

The corpus has the token *inventory* half of this class fully mapped (see the Token taxonomy table in SKILL.md and `http-auth-filter-testing.md` §token-taxonomy) — what this file adds is the **attack battery** that turns a captured token inventory into testable hypotheses. Three corpus artifacts already point straight into it: F7's token-type verification, F5's `keycloakSecret` leak, and the C2/C4 `jwksUrl` SSRF sinks.

---

## Pattern

A JWT is trust delegated to crypto plus a parser. Every attack below is either (a) a signature-verification bypass (the check runs differently than the issuer meant), (b) a claim-interpretation confusion (two components parse the same token differently), or (c) a key-sourcing bug (the verifier fetches/derives the key from attacker-influenced input). The class pairs perfectly with this skill's existing primitives: any URL-accepting field is a potential `jku`/`x5u` sink, and any leaked signing secret is a forgery primitive.

---

## Generic recipe

### 0. Inventory first (Tier 1 — free)
Decode every captured token (header/payload/signature split, base64url) *without sending anything*: `alg`, `kid`, `jku`, `x5u`, `jwk`, `iss`, `aud`, `azp`, `scope`/`roles`, `exp`/`iat`/`nbf`, custom claims. Build the claim inventory + hypothesis list (Lesson 11 Stage 1-2 — this is mandated analysis, and where most chain value lives). Note which components *consume* which claim (SPA bundle, mobile APK, API 401/403 envelopes) — claim confusion needs two consumers that disagree.

### 1. alg attacks (the classics, cheap to run)
- `alg:none` / empty signature / signature-truncation: re-sign payload with `alg:"none"`, send, compare against baseline 401. Most stacks reject; when one doesn't, it's instant Critical.
- **HS256/RS256 confusion**: if the token is RS256-signed, take the RSA public key (from `/.well-known/jwks.json` — Keycloak/Okta publish it) as an HMAC secret and re-sign with `alg:"HS256"`. Works when the verifier picks the algorithm from the token header. Negative control: same forgery with a *wrong* key must stay 401 — proves the 200 wasn't some parsing artifact.
- `alg` downgrade to a weaker curve/legacy (`RS1`-type combinations) where the library allows odd unions.

### 2. kid injection (the key is looked up, not fixed)
If `kid` flows into a lookup — path (`kid: "../../dev/null"`), SQLi (`kid: "x' UNION SELECT 'secret'--"`), or command substitution in some libraries — the verifier's key choice is attacker-steered. Probe with marker kids first (error-message differentials reveal the lookup backend), then land the injection that points verification at a key you control (e.g. an empty file, a known HMAC value). Record the lookup-backend fingerprint from the error envelope.

### 3. jku / x5u / jwk header → the corpus already has these sinks
If the header carries a URL (`jku`, `x5u`) and the verifier fetches it, that's an **SSRF with a crypto payoff**: point it at your webhook.site receiver (prove fetch + UA fingerprint, two-sided evidence per Lesson 9), then serve a JWKS you hold the private key for → full forgery. Cross-reference the Phase-1 URL-accepting-field sweep: the C2/C4 `jwksUrl` sinks are exactly this bug surfaced through a *body field* instead of a header — if the target validates JWTs with a key fetched from a tenant-controllable URL, forgery + SSRF compose into one chain (report the chain per `report-structure.md` §synthesis).

### 4. Claim confusion
- Duplicate/conflicting claims: two `iss`, two `scope`, JSON type juggling (`"scope":"admin"` vs `"scope":["admin"]` vs `"scope":{"0":"admin"}`) — send both orderings, diff the authorization decision. Any behavioral flip = two parsers disagreeing.
- Audience/issuer substitution: token minted for service A (`aud: service-a`) replayed against service B that only checks signature, not `aud`. The corpus's own taxonomy is the test bed: `hypws-` (install) vs `hypwo-` (WORKSTATION) cross-acceptance was *exactly* this test in F7 — both accepted at the IdP endpoints, random UUID rejected. Run the same matrix across every token type × every endpoint class (`scripts/authz-matrix.sh`).
- Role/scope inflation by *omission*: some verifiers treat missing claims as deny, others as allow — strip claims one at a time and diff.

### 5. Replay windows
- `exp` enforcement: expired token → must 401. If accepted, capture the exact acceptance window (that number is the finding).
- Clock-skew allowance: shift `iat`/`nbf` ±5/±30/±300 s and find the tolerance boundary.
- Revocation: change password / log out / revoke the session, then replay — a bearer that outlives its revocation event is the standing finding (the corpus's install-token "unexpiring, 5 mints, never consumed" property is the extreme case; treat any long-TTL + no-revocation combo as a dormant persistence primitive per Lesson 7/8, scored at *current* impact).
- Magic-link/OOTP single-use enforcement: the corpus's `secondsValid` finding (admin-mintable long-lived magic links) is the pattern — probe every token-issuance field for lifetime control.

---

## Instance

**Corpus (all real):** (1) **F7 token-type matrix** — `hypws-` and `hypwo-` both accepted at the 9 missing-`@PreAuthorize` endpoints, random UUID → 401: claim-confusion §4 with the authz matrix as the harness. (2) **F5 `keycloakSecret` plaintext read** — a leaked realm signing secret; if Keycloak-issued tokens on that realm are HMAC-verified anywhere, §1's forgery is unlocked by Tier-1 material alone. (3) **C2/C4 `jwksUrl` SSRF** — verifier-side key fetching from attacker URLs; §3's full chain (fetch proof → self-hosted JWKS → forged token → Tier-2 read-only validation) is the composition to attempt first on any target that re-exposes this shape. (4) **Magic-link `secondsValid`** — §5's lifetime-control probe, already confirmed as a documented required field.
