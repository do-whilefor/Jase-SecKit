# GraphQL — Introspection, Batching, Field-Level Authz, Depth/Cost

Zero corpus instances — the AcmeAuth surface is REST-only (no `/graphql` in the 295-endpoint OpenAPI inventory or the 263-path SPA-bundle extraction). That negative is itself the detection baseline: GraphQL won't announce itself in a REST inventory. Recipe below is the generic battery for any target that runs a graph layer.

---

## Pattern

One endpoint multiplexes the entire API: schema introspection maps it, **field-level authorization** is the only thing standing between a low-priv token and high-priv data (REST's per-route `@PreAuthorize` has no equivalent unless the resolver checks), and batching turns "one request per action" rate limits into "N actions per request". The failure mode is always the same shape: *the schema is wider than the authz coverage*.

---

## Generic recipe

### 1. Find the endpoint
Probe paths: `/graphql`, `/graphiql`, `/api/graphql`, `/api/v2/graphql`, `/graphql/console`, `/<app>/graphql`, plus vendor prefixes from the surface map (`/cc/graphql`, `/ federation` routes). Content probe that doesn't depend on path luck: `POST` with `{"query":"{__typename}"}` to any endpoint that returns `400 "query"`-shaped errors; GET `?query={__typename}` (also tells you GET is enabled — CSRF-relevant). Watch the JS bundle for `graphql`, `__typename`, `apollo`, `urql`, `relay` strings — bundle evidence beats path guessing.

### 2. Map the schema
- Introspection: standard `__schema` query; if blocked, mine **field suggestions** — send `{user{name}}` against a real field parent and read `"Did you mean"`/`Cannot query field` errors, which enumerate valid field names one typo at a time. Also try the whitespace/unicode-bypass variants of the `__` prefix and `/graphql?query=` on GET.
- Save the schema file — it becomes the authz-matrix denominator, same role as the OpenAPI spec in the REST method (`scripts/authz-matrix.sh` logic ports directly: token × resolver matrix).

### 3. Field-level authz matrix (the core test)
For every (token, sensitive resolver) pair from the matrix: query the **exact object graph the resolver exposes**, not just the field. `200` with data = BOLA/IDOR candidate; the empty-`{}` rule inverted: here a well-formed query returning `null`/`errors[].message: "not authorized"` per-field is the *secured* baseline. Graph layers make it trivial to ask for what REST hides: fetch `user(id: "…"){ email ssn roles }` directly — check whether resolvers validate **object ownership** (CWE-639) or merely authentication. Global/sequential IDs: decode base64 node IDs (`Uithreadd:<n>` style), re-encode neighbors, iterate — bounded sweep, record every cross-object read.

### 4. Batching / aliasing abuse
- Array-of-queries batching: `[{query:"mutation{redeem(code:\"X\")}"},{query:"...same..."}]` in one POST — if the executor runs them in one transaction/sequence without dedup, this is the **race-class primitive without a race** (see `race-conditions.md` — the double-exploit set transfers 1:1; serial-vs-batched is your negative-control pair).
- Alias multiplication: `{a: field b: field c: field ...}` ×100 — probes both rate-limit-per-request assumptions and resolver-loop DoS. Cap at bounded volume — a 100-alias probe demonstrating cost-limit absence is the evidence, not a 100k flood.
- Non-null cascade: query a `__typename`-only payload against expensive fields to fingerprint executor behavior cheaply.

### 5. Depth / cost / pagination
Probe depth limits with nested fragments; probe pagination with `first: 100000`-style args; record whether either is enforced. A missing cost limit is a finding (DoS-class, score honestly — usually Medium with AC:H-ish framing unless data proves otherwise), not a reason to actually DoS.

### 6. Transport-layer extras
GET-enabled queries → CSRF (no CSRF token on graph endpoints is typical; a state-changing GET mutation is the jackpot — test cross-origin form/GET PoC with placeholder targets); subscriptions (`ws` upgrade) often skip the HTTP auth middleware entirely — connect and subscribe before assuming the token gate applies; persisted-query formats (APQ) leak the whole operation hash list — probe `/graphql?extensions={"persistedQuery":{...}}`.

---

## Instance

**Corpus:** none — AcmeAuth is the negative control for this class (REST-only, confirmed two ways: OpenAPI inventory + bundle grep). What transfers from the corpus when you *do* meet a graph layer: the token × endpoint matrix method (F7's 246-endpoint sweep, restated as token × resolver), the negative-control discipline (secured-field baseline before claiming bypass — the F25 lesson applies to "field returned null" claims), and the URL-accepting-field sweep (`jwksUrl`/`webhookUrl`-style inputs are *more* common in graph schemas — map them straight onto the C2/C4 SSRF method in `bypass-catalogue.md` §K).

---

