# HTTP Boundaries · Reference

Load after selecting the `http-parser-differential` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## HackerOne Case Index

### 648434 · HTTP message-boundary/protocol parsing differential
- Knowledge value: 10/10; protocol-behavior exploitation / cross-component attack chain.
- Chain: `https://packetstormsecurity.com/papers/general/whitepaper_httpresponse.pdf` → HTTP message-boundary/protocol parsing differential, combined with a cache-key/response-variant mismatch → the corresponding trust boundary is crossed → access to or impact on another user’s data/state.
- Bypass: Construct requests that produce different boundaries in layered HTTP parsers and use connection reuse to affect later requests, routing, or caches; combine with a cache-key mismatch.
- Defensive anchor: Align HTTP parsing and normalization across layers; reject ambiguous length indicators, abnormal duplicate headers, and invalid line endings; test H2/H1 conversion consistency; never return anomalous connections to shared pools; add cache-variant cross-component regressions.

### 737140 · HTTP message-boundary/protocol parsing differential
- Knowledge value: 10/10; protocol-behavior exploitation / cross-component attack chain / authentication bypass.
- Chain: `GET https://<URL> HTTP/1.1` → HTTP message-boundary/protocol parsing differential → security controls and the final execution point disagree about subject, object, state, or input semantics → account takeover.
- Bypass: Construct requests that produce different message boundaries across layers and use connection reuse to affect later requests, routing, or caches.
- Defensive anchor: Align HTTP parsing and normalization across layers; reject ambiguous lengths, abnormal duplicates, and invalid line endings; test H2/H1 conversion; keep anomalous connections out of shared pools.

### 771666 · HTTP message-boundary/protocol parsing differential
- Knowledge value: 9/10; protocol-behavior exploitation / cross-component attack chain / authentication bypass.
- Chain: `GET /some/other/endpoint` → HTTP message-boundary/protocol parsing differential, combined with OAuth/SSO callback and credential-lifecycle misbinding → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Create cross-layer request-boundary ambiguity and combine it with OAuth/SSO callback or credential-lifecycle misbinding.
- Defensive anchor: Unify parsing, reject ambiguity, test protocol conversion, isolate anomalous connections, and add OAuth/SSO binding regressions at the final consumer.
