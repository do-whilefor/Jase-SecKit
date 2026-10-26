# Race Conditions — Single-Packet Parallelism, Double-Exploits, Limit Overdraw

Zero corpus instances from the AcmeAuth engagement — the class was never triggered there. Closest corpus evidence: F24's `/api/send-code` accepted 6 sequential POSTs with no `429`, no `Retry-After`, no `X-RateLimit-*` (a rate-limit gap, not a race) — the kind of endpoint where a race battery is the natural next probe. Everything below is the generic recipe; record your own instances per the standard evidence rules.

---

## Pattern

A vulnerability exists only **while two or more requests are in flight simultaneously**: the target does check-then-act across a window (read state → decide → write state) with no lock, idempotency key, or transaction isolation covering the gap. Single-request testing can never find it, and a naive parallel flood mostly proves the target has a queue, not that the window is exploitable.

High-value sub-patterns, in reward order:
- **Double-exploit** — one operation, two effects: redeem coupon/gift-card twice, transfer twice against one balance, 2FA bypass (code-check races session-flag set), vote/like inflation, double refund.
- **Limit overdraw** — N operations where M allowed: rate-limit buckets that increment after the act, quota checks racing quota writes, "one free trial per account".
- **Security-flag toggles** — `is_admin`, `email_verified`, password-reset single-use token consumed twice.

---

## Generic recipe

### 1. Select targets (hypothesis first)
Grep the endpoint inventory (Phase-1 surface map) for check-then-act shapes: redeem/apply/claim/transfer/vote/verify/activate/consume + any endpoint whose response contains a counter, quota, or single-use token. Each candidate = one hypothesis with a predicted state effect ("2 concurrent redemptions → balance decremented once, coupon applied twice").

### 2. Serial baseline = the negative control (mandatory)
Run the identical request **serially** N times and record the state after each. If the state flips the same way serially (e.g. coupon is simply reusable), there is no race — it's a plain logic bug, report it as one. The race claim is specifically: *serial → blocked/once, parallel → N times*. Without this baseline the finding is unfalsifiable (Lesson 1 discipline applies here too).

### 3. Synchronize, don't flood
The skill of the class is arrival-time precision, not volume:
- **Last-byte sync** (HTTP/1.1): send N connections where every request is pre-written except the final byte; release them in one loop iteration. 20–40 connections is enough.
- **Single-packet attack** (HTTP/2): N requests in one SETTINGS-frames packet — the server's `select()` wakes once and they execute back-to-back with ~1 ms skew. First choice when the target speaks h2.
- Estimate server sync first: fire 20 no-op requests, cluster the receive timestamps, adjust offset — if arrival skew > the state-write window (~ms), re-align before concluding "not vulnerable".
- Endpoints that **fork per-request state** (sessions, tokens) need the state to be shared for the race to matter: use one session/token across all racing requests when the check is per-account, separate sessions when the check is per-session (e.g. reset-token consumption).

### 4. Verify state, not responses
A 200×N means nothing; the exploit is the **end state**: re-fetch balance/redemption count/role and diff against the serial baseline. Response bodies during the race are noise (half may be 500s from the collision — sometimes itself evidence of the window).

### 5. Escalation framing
A confirmed race is a finding candidate, not a license — what you do with the duplicated access is still Tier-bound (read-only verification vs placeholder-target demonstration). CVSS note: exploitability is AC:H-adjacent only if timing is genuinely fragile; a reproducible single-packet win with state proof is usually AC:L. Do not credit "hypothetical mass exploitation by many attackers" (narrative impact — Pattern 4 in `cvss-scoring-methodology.md`).

---

### Killed-hypothesis signatures (record these when negative)
- Queued/serialized backend (all requests process ~sequentially — timestamps prove it) → class dead for that endpoint, say so with the timestamp evidence.
- Idempotency keys / dedup tokens accepted and enforced → try omitting/garbling the key header first; if enforced server-side, class dead.
- Row-level locks / `SELECT ... FOR UPDATE` (collision manifests as 500/timeout but final state is correct once) → window closed, document.
- Client-side dedup only (serial via fresh sessions bypasses) → that's a logic bug, not a race; reclassify.

---

## Instance

**Corpus:** none confirmed. Nearest artifacts for a future engagement on this stack: F24's unbounded `/api/send-code` (no rate-limit counters to race, but proves the limit layer is thin) and F8's `/cc/install/token/exchange` mint surface (check-then-act on token issuance — a mint-count race is the canonical first probe if that surface ever reappears). When you run the battery anywhere, the evidence set to capture is: serial baseline states, parallel run request timing cluster, end-state diff, and the exact N achieved per single allowed op.
