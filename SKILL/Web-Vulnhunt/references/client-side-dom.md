# Client-Side / DOM — Source→Sink Sweeps, Prototype Pollution, postMessage, WebView Bridges

The corpus does half this class: SPA bundle mining for *endpoints* is a documented Phase-1 technique (263 API paths from `loggedIn.js`, 3.1 MB Angular bundle). What was never run on the corpus is the **code-level pass** — sources, sinks, gadgets — and the skill honestly lists client-side bugs as a known weakness. This file is the battery that closes the gap; the bundle you already download for endpoint mining is the same artifact it consumes.

---

## Pattern

The SPA ships application code to every visitor — the client is an attack surface the server-side sweep never touches. Three sub-classes: **DOM XSS** (attacker-controlled source reaches an executing sink), **client-side prototype pollution** (a merge/parse gadget reachable from URL/JSON), and **postMessage/bridge confusion** (privileged operations gated on unvalidated origin/message or exposed native objects). Verification follows the same two-sided rule as mobile (Lesson 9): static identification is a hypothesis; a canary executing in the real browser context is the proof.

---

## Generic recipe

### 1. Acquire the corpus
Same artifacts as Phase 1: main bundle + lazy chunks (`loggedIn.js`-style, sitemap-driven), plus any `/static/js/*` map files (source maps, if published, turn grep into reading). Save per-version — post-patch client diffs are a Phase-3 technique.

### 2. Static source→sink sweep (Tier 1 — free, exhaustive)
Grep the bundle for the sink catalog, then walk backwards to the source:
- **HTML/execution sinks**: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write(ln)`, `eval(`, `new Function(`, `setTimeout("/…")`-string form, `angular.element(...)` raw, `$compile(`, `v-html`, `dangerouslySetInnerHTML`.
- **URL/ navigation sinks**: `location =`, `location.href=`, `window.open(`, `src=`/`action=` assignments from variables — combined with `javascript:` scheme checks.
- **JQuery-era**: `$(location.hash…)`-style selector injection, `.html(` calls.
- **Source inventory** (what feeds them): `location.*` (hash especially — never server-logged), `document.referrer`, `postMessage` event data, URL params decoded by the router, `window.name`, storage keys, fetch/XHR responses reflected from attacker-controllable fields.
A reachable source→sink pair = hypothesis; record with the minified function name + line so the dynamic step can target it.

### 3. Framework reality check (the corpus is Angular — check first, not last)
- **Angular**: interpolation `{{ }}` is auto-escaped — template-injection only matters where the app compiles user strings (`$compile`, bypassSecurityTrustHtml/Url/ResourceUrl — grep `bypassSecurityTrust*` first, it's the whole Angular XSS story); the corpus SSTI probes (`{{7*7}}` reflected raw, never evaluated) were *server-side* negatives — client-side compilation of reflected strings is a different, still-open question.
- **React/Vue equivalents**: `dangerouslySetInnerHTML`, `v-html`, `:href` with user data.
- Server-reflected `{{7*7}}`/`${7*7}` in *client-compiled* contexts: re-test reflection targets against client-side template compilation before marking dead.

### 4. Client-side prototype pollution
Query-param pollution batteries against JS-heavy pages: `?__proto__[ppmarker]=1`, `?__proto__[ppmarker][x]=1`, `?constructor[prototype][ppmarker]=1`, `?constructor%5Bprototype%5D%5Bppmarker%5D=1`, JSON-body variants on client-side merge endpoints. **Detection needs a known gadget**: grep the bundle for pollution-consuming patterns (`Object.assign(..., JSON.parse(...))`, recursive merge utils like `lodash.merge`/`deepmerge`, `for (x in obj)` copies onto config objects), then test the gadget's observable effect (config flip, new keys appearing, 500-vs-200 in client-side rendering). A marker key appearing in `Object.keys` via a console/factory hook is the cleanest proof. Server-side PP was already in the old corpus battery (`{"__proto__":{"ppmarker":1}}` on merge-looking endpoints) — the client-side half is this file's addition.

### 5. postMessage / bridge audit
- Grep `addEventListener("message"` → for each handler, check origin validation (`e.origin ===` allowlist) before sensitive use; a handler that accepts `*` or parses without origin checks is the hypothesis. Verify two-sided: post the crafted message from an attacker-origin page hosted anywhere, observe the privileged effect in the console/DOM.
- `window.open`-returned references, `iframe.contentWindow` writes, and name-collision global leaks (`window.<callback>` JSONP-style) complete the set.
- **WebView bridge (mobile companion)**: `addJavascriptInterface` exposure is already on the mobile watchlist — the JS-side half is grepping the bundle for the interface name and testing which page origins can reach it (F3/F10's deep-link `rpUrl` surface is the corpus's adjacent mobile entry).

### 6. Dynamic verification (mandatory before claiming)
The lesson-9 loop, browser edition: canary string → sink (unique marker `<img src=x onerror="window.__pp=1">`-style non-network proof for XSS claims), observed in the actual target origin context (browser console hook or debug build), plus the exact URL/payload a third party would need. Client-only PoCs that depend on console-crafted objects are Tier-1 findings — say so, don't inflate to "exploitable" until the entry URL exists. `postMessage`/PP proofs run against the operator's own browser sessions and test accounts.

---

## Instance

**Corpus:** no DOM-sink instance (the pass below was never run — that's the gap this file closes). Real corpus anchors: (1) **`loggedIn.js` 3.1 MB Angular bundle** — already downloaded for endpoint mining; run recipe §2-§4 on the same artifact, starting with `bypassSecurityTrust*` and `lodash.merge`-shaped greps. (2) **SPA fallback behavior** (200 + `index.html`, 405 on non-GET) — confirms which routes ship the bundle where, i.e. which URLs an attacker can hand a victim to land on any client route. (3) **F18 CSP `frame-ancestors` reflection** — client-side framing/context questions (which origins may embed what) have a confirmed corpus reflection to build on. Record every negative at sink granularity (`sink → source reachable? → dynamic proof? → why dead`) so the next bundle diff starts from the map, not from zero.
