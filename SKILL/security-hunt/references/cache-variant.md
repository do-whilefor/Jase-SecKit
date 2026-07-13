# Cache Variants · Reference


Load on demand after selecting the `cache-key-variant` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## HackerOne Case Index


### 84601 · Cache-key/response-variant mismatch
- Value: 10/10; cross-component attack chain / protocol-behavior exploitation / XSS.
- Chain: `http://innerht.ml/pocs/twitter-upload-xss` → cache-key/response-variant mismatch → security controls and the final execution point disagree about subject, object, state, or input semantics → token, key, session, or cloud-credential disclosure.
- Bypass: Poison a shared cache with an unkeyed header, cookie, Host value, query parameter, or path variant, then have an independent normal request receive the poisoned object.
- Defensive anchor: Include every dimension that affects a security-relevant response in the cache key; disable shared caching by default for user-, role-, tenant-, and security-sensitive responses; use identical key semantics before and after normalization and verify isolation with an independent session.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 303730 · Cache-key/response-variant mismatch
- Value: 10/10; cross-component attack chain / protocol-behavior exploitation / framework-behavior exploitation.
- Chain: `https://catalog.data.gov/dataset/consumer-complaint-database?dontpoisoneveryone=6` → cache-key/response-variant mismatch, combined with file-processing order and multi-parser semantic differences → the corresponding trust boundary is crossed → access to or impact on another user’s data/state.
- Bypass: Poison a shared cache with an unkeyed header, cookie, Host value, query parameter, or path variant, then have an independent normal request receive it; combine with file-processing and multi-parser differences.
- Defensive anchor: Include every security-relevant response dimension in the cache key; prevent shared caching of sensitive responses; align normalization and key semantics; verify isolation independently and add cross-component negative tests for file-processing order and multi-parser semantics.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 350847 · Cache-key/response-variant mismatch
- Value: 10/10; cross-component attack chain / protocol-behavior exploitation / framework-behavior exploitation.
- Chain: `/embed/job_board/js?for=` → cache-key/response-variant mismatch, combined with Unicode/encoding/normalization and boundary-matching differences → the corresponding trust boundary is crossed → denial of service or resource exhaustion.
- Bypass: Poison a shared cache with an unkeyed input and combine it with normalization or boundary-matching differences to extend or complete the chain.
- Defensive anchor: Include every security-relevant response dimension in the cache key; prevent shared caching of sensitive responses; align normalized and keyed representations; verify with independent sessions and add normalization-focused cross-component regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 0.
- HackerOne reports: 42.
- HackerOne report IDs:
  - 1698316, 1976449, 824753, 350847, 537564, 84601, 1183263, 1173153, 334709, 429747, 593712, 326639, 417453, 439021, 1198434, 753939, 728664, 504514
  - 1010858, 1795197, 397508, 921704, 1346618, 1581454, 977851, 158019, 1160407, 1679969, 301432, 1760213, 1181946, 631589, 737315, 1025575, 1271944, 303730
  - 942629, 260697, 591302, 288912, 409370, 394016

