# Cache Variants · Reference

Load after selecting the `cache-key-variant` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## HackerOne Case Index

### 84601 · Cache-key/response-variant mismatch
- Knowledge value: 10/10; cross-component attack chain / protocol-behavior exploitation / XSS.
- Chain: `http://innerht.ml/pocs/twitter-upload-xss` → cache-key/response-variant mismatch → security controls and the final execution point disagree about subject, object, state, or input semantics → token, key, session, or cloud-credential disclosure.
- Bypass: Poison a shared cache with an unkeyed header, cookie, Host value, query parameter, or path variant, then have an independent normal request receive the poisoned object.
- Defensive anchor: Include every dimension that affects a security-relevant response in the cache key; disable shared caching by default for user-, role-, tenant-, and security-sensitive responses; use identical key semantics before and after normalization and verify isolation with an independent session.

### 303730 · Cache-key/response-variant mismatch
- Knowledge value: 10/10; cross-component attack chain / protocol-behavior exploitation / framework-behavior exploitation.
- Chain: `https://catalog.data.gov/dataset/consumer-complaint-database?dontpoisoneveryone=6` → cache-key/response-variant mismatch, combined with file-processing order and multi-parser semantic differences → the corresponding trust boundary is crossed → access to or impact on another user’s data/state.
- Bypass: Poison a shared cache with an unkeyed header, cookie, Host value, query parameter, or path variant, then have an independent normal request receive it; combine with file-processing and multi-parser differences.
- Defensive anchor: Include every security-relevant response dimension in the cache key; prevent shared caching of sensitive responses; align normalization and key semantics; verify isolation independently and add cross-component negative tests for file-processing order and multi-parser semantics.

### 350847 · Cache-key/response-variant mismatch
- Knowledge value: 10/10; cross-component attack chain / protocol-behavior exploitation / framework-behavior exploitation.
- Chain: `/embed/job_board/js?for=` → cache-key/response-variant mismatch, combined with Unicode/encoding/normalization and boundary-matching differences → the corresponding trust boundary is crossed → denial of service or resource exhaustion.
- Bypass: Poison a shared cache with an unkeyed input and combine it with normalization or boundary-matching differences to extend or complete the chain.
- Defensive anchor: Include every security-relevant response dimension in the cache key; prevent shared caching of sensitive responses; align normalized and keyed representations; verify with independent sessions and add normalization-focused cross-component regressions.
