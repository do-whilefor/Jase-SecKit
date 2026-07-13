# HTTP Boundaries · Reference


Load on demand after selecting the `http-parser-differential` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## HackerOne Case Index


### 648434 · HTTP message-boundary/protocol parsing differential
- Value: 10/10; protocol-behavior exploitation / cross-component attack chain.
- Chain: `https://packetstormsecurity.com/papers/general/whitepaper_httpresponse.pdf` → HTTP message-boundary/protocol parsing differential, combined with a cache-key/response-variant mismatch → the corresponding trust boundary is crossed → access to or impact on another user’s data/state.
- Bypass: Construct requests that produce different boundaries in layered HTTP parsers and use connection reuse to affect later requests, routing, or caches; combine with a cache-key mismatch.
- Defensive anchor: Align HTTP parsing and normalization across layers; reject ambiguous length indicators, abnormal duplicate headers, and invalid line endings; test H2/H1 conversion consistency; never return anomalous connections to shared pools; add cache-variant cross-component regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 737140 · HTTP message-boundary/protocol parsing differential
- Value: 10/10; protocol-behavior exploitation / cross-component attack chain / authentication bypass.
- Chain: `GET https://<URL> HTTP/1.1` → HTTP message-boundary/protocol parsing differential → security controls and the final execution point disagree about subject, object, state, or input semantics → account takeover.
- Bypass: Construct requests that produce different message boundaries across layers and use connection reuse to affect later requests, routing, or caches.
- Defensive anchor: Align HTTP parsing and normalization across layers; reject ambiguous lengths, abnormal duplicates, and invalid line endings; test H2/H1 conversion; keep anomalous connections out of shared pools.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 771666 · HTTP message-boundary/protocol parsing differential
- Value: 9/10; protocol-behavior exploitation / cross-component attack chain / authentication bypass.
- Chain: `GET /some/other/endpoint` → HTTP message-boundary/protocol parsing differential, combined with OAuth/SSO callback and credential-lifecycle misbinding → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Create cross-layer request-boundary ambiguity and combine it with OAuth/SSO callback or credential-lifecycle misbinding.
- Defensive anchor: Unify parsing, reject ambiguity, test protocol conversion, isolate anomalous connections, and add OAuth/SSO binding regressions at the final consumer.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 0.
- HackerOne reports: 35.
- HackerOne report IDs:
  - 2327341, 1501679, 2032842, 2299692, 2280391, 1524692, 726773, 867577, 965267, 866382, 867952, 1524555, 526880, 771666, 1063627, 922597, 1063493, 777651
  - 648434, 1675191, 713285, 2001873, 1092230, 1665156, 919175, 1238709, 1120982, 715996, 1630336, 737140, 1002188, 2237099, 758445, 1238099, 643225

