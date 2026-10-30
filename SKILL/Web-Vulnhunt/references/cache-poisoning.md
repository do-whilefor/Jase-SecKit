# Web Cache Poisoning & Deception — Unkeyed Inputs, Key Normalization, Path Suffix Tricks

Zero confirmed corpus instances — but the AcmeAuth stack is *shaped* for the class and the corpus proves the surfaces exist: CloudFront fronts static assets, `/static/docs/**` serves cacheable HTML error templates, and F18 showed `Host` reflected into the CSP `frame-ancestors` of the Keycloak redirector — a reflection that becomes **stored** the moment any intermediary caches that response. This class is the natural continuation of the skill's edge-behavior obsession: same parser-disagreement method as [bypass-catalogue.md](bypass-catalogue.md), aimed at the cache key instead of the auth filter.

---

## Pattern

The cache stores a response under a **key** (usually method + host + path, sometimes selected query params/headers) but the **response body varies** with inputs that are *not* in the key (unkeyed headers, unkeyed params, normalized-away path segments). Poisoning = make the cache store your content under a key other victims request. Deception = make the cache store *someone else's* private content under a key *you* can read. Both are parser-disagreement bugs: the cache and the origin disagree about what determines the response.

---

## Generic recipe

### 1. Detect the cache before touching it
Fingerprint per host: response headers (`X-Cache: HIT/MISS`, `Age`, `Via`, `CF-Cache-Status`, `X-Served-By`), timing delta (first vs second identical GET), and header-echo behavior (some caches add theirs). Classify each surface-map host: static assets (likely cached), framework error pages (`/static/docs/**`-style — often cached), API JSON (usually not — verify, don't assume). Record which layer: CDN / reverse proxy / app-level (SCG, nginx `proxy_cache`).

### 2. Mine unkeyed inputs
For each cacheable route, probe candidate unkeyed inputs and watch for body reflection on a **cache MISS that persists on the next HIT**:
- Headers: `X-Forwarded-Host`, `X-Forwarded-Scheme`, `X-Forwarded-Proto`, `X-Original-URL`, `X-Rewrite-URL`, `Forwarded`, `X-Host`, plus framework-specifics (`X-HTTP-Method-Override`). One per request, marker value = unique harmless string (e.g. `zmark<rand>`).
- Params: unknown-parameter mining on cacheable GETs (`?zmark<rand>=1`) — some caches key on a params whitelist, so an unknown param is reflected-but-unkeyed by construction.
- A reflection that survives into a second client's HIT = the primitive. A reflection only you ever see = unkeyed but uncacheable, dead end.

### 3. Establish cache persistence
Inject a unique marker into a reflected header or response context and record the path/parameter used. Retrieve the response from a second client (different IP/UA, no cookies) to distinguish shared-cache persistence from client-local reflection. Host-header hooks (F18 pattern): if `X-Forwarded-Host`/`Host` flows into generated URLs (CSP, redirects, canonical links) and the response is cacheable, connect reflection, persistence, and retrieval in the chain evidence.

### 4. Web cache deception (steal, don't plant)
Append a cacheable extension/path to an authenticated endpoint: `/cc/api/settings/profile.js`, `/settings/profile/.css`, `/settings/profile%3fa.js`, WebDAV-style `/settings/profile;x.js` — variants map 1:1 onto the §A bypass ladder (same normalization disagreements, different winner). Test which suffix the *cache* treats as static but the *origin* still routes to the authenticated controller. Compare authenticated and unauthenticated retrievals to identify private response data persisted in the cache, then distinguish the demonstrated persistence from the delivery preconditions.

### 5. Key-normalization disagreement (bridge to §A)
The bypass ladder already documents origin-side normalization; run the same variants against the *cache key*: does `/env` and `/ENV` and `/env;/` share one cache entry or split? Case/decode/split differences between cache and origin = both a poisoning primitive AND an auth-filter bypass amplifier (poison the *unprotected* spelling of a path, victims request the protected one). Record which component owns which normalization step — the two-layer observation from §A (`..;` passes SCG, Spring rejects) is exactly this analysis, done for the router instead of the cache.

### 6. Evidence set (what CONFIRMED requires)
(1) the unkeyed input + its reflection, (2) MISS→HIT persistence proof, (3) second-client retrieval (fresh connection, no cookies), (4) the response headers showing cache ownership. Negative control: same request from the second client *before* poisoning (must MISS/absent), and same poison on a route you've proven is uncached (must not persist). Without (4) you've proven persistence, not cache involvement.

---

## Instance

**Corpus:** no confirmed instance; three live hooks for this stack. (1) **F18 Host reflection** — `Host: evil.attacker.com` reflected into Okta-redirect CSP `frame-ancestors` on all 7 CC tenants; re-test post-patch with `X-Forwarded-Host` on cacheable Keycloak paths (recipe §3). (2) **`/static/docs/**` RFC 7807 HTML templates** — server-rendered, cacheable-looking, and the `type` field embeds user-influenced class names (F27 package-path leak): a class-name reflection persisted into a shared cache entry is the cheapest possible demo. (3) **CloudFront static assets** (`assets.cdn.acmeauth.example`): S3 MRAP deny XML is the response for malformed requests — if the deny XML ever caches under a real asset key, the account-ID leak (row 7a) becomes stored. Each is a one-session probe with the recipe above; record outcomes in [killed-hypotheses.md](killed-hypotheses.md) if negative.

---
