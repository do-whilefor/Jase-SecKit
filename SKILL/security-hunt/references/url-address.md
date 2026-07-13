# URLs & Addresses · Reference


Load on demand after selecting the `ssrf-url-address` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### doyensec/Doyensec Gravitational Teleport CloudTesting Q12021 · TEL-Q121-7. Server-Side Request Forgery via OpenID Connect
- Value: 8/10; SSRF / cross-component attack chain.
- Chain: The attacker supplies a controllable URL or host → the server parses it and makes a request → redirects, DNS behavior, or protocol differences reach internal, local, or cloud-metadata services → sensitive information is read or internal capabilities are invoked.
- Bypass: URL parsing, redirects, DNS rebinding, or unauthenticated internal services let external input acquire the server’s network identity.
- Defensive anchor: Use destination allowlists; validate IP addresses after every resolution and redirect; block private, loopback, link-local, and metadata ranges; restrict schemes and ports; enforce outbound network isolation.


## HackerOne Case Index


### 541169 · SSRF URL/address semantic difference
- Value: 10/10; SSRF / framework-behavior exploitation / race condition.
- Chain: `/lib/gitlab/url_blocker.rb` → SSRF URL/address semantic difference, combined with a TOCTOU/concurrent-state boundary failure → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Use URL canonicalization, redirects, DNS resolution, IPv4/IPv6 representations, userinfo, or layered-parser differences so the validated target differs from the final connection target; combine with a race.
- Defensive anchor: Use one strict parser; validate the final IP and address family after DNS resolution; reapply scheme, host, and address policy at every redirect and immediately before connection; block private, loopback, link-local, and metadata ranges; restrict egress; add TOCTOU regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 632101 · SSRF URL/address semantic difference
- Value: 10/10; SSRF / framework-behavior exploitation / business logic.
- Chain: `http://990.hacker1.xyz` → SSRF URL/address semantic difference → security controls and the final execution point disagree about subject, object, state, or input semantics → isolation is crossed and host or privileged resources become accessible.
- Bypass: Use URL normalization, redirects, DNS behavior, alternate IP forms, userinfo, or multiple parsers so the validated destination differs from the final connection.
- Defensive anchor: Use one strict parser; validate resolved addresses; reapply policy on every redirect and final connection; block private, loopback, link-local, and metadata destinations; restrict outbound access.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 1068433 · SSRF URL/address semantic difference
- Value: 10/10; SSRF / framework-behavior exploitation / XSS.
- Chain: `GET /people-rater/entry?id=eyJpZCI6Mn0=` → SSRF URL/address semantic difference, combined with browser/template/filter parsing differences → the corresponding trust boundary is crossed → access to internal services or cloud metadata.
- Bypass: Use URL/address ambiguity and combine it with browser/template/filter parsing differences.
- Defensive anchor: Use strict parsing and resolved-address validation, reapply policy at redirects and final connect, block internal ranges, restrict egress, and add browser-parsing cross-component regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 2.
- HackerOne reports: 21.
- Full report IDs:
  - doyensec/Doyensec Gravitational Teleport CloudTesting Q12021
  - doyensec/Doyensec Gravitational Teleport Testing Q42020
- HackerOne report IDs:
  - 1069487, 541169, 386292, 632101, 704621, 1691501, 1115139, 61312, 1608039, 925527, 1141623, 1702864, 2301565, 187520, 879803, 1068433, 178184, 1747596
  - 2493548, 1049624, 1553841

