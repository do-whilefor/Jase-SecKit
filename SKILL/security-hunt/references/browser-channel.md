# Cross-Origin Channels · Reference


Load on demand after selecting the `cross-origin-message-channel` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### cure53/pentest-report-mozilla-vpn-apps-clients-03-2021 · FVP-02-014 General: Cross-site WebSocket hijacking
- Value: 10/10; authentication bypass / protocol-behavior exploitation / cross-component attack chain.
- Chain: The victim logs in to the target site → visits an attacker page → the page opens a cross-site WebSocket using the victim’s cookies → the attacker invokes local or cloud privileged functions bidirectionally or reads responses.
- Bypass: WebSockets do not automatically inherit traditional CSRF protections; without Origin or handshake-token validation, the victim’s authenticated state is reused.
- Defensive anchor: Strictly allowlist Origin; use one-time, session-bound handshake tokens; do not authenticate solely with cookies; authorize every message at object level and restrict local control interfaces.


## HackerOne Case Index


### 129873 · postMessage/browser-message source and object-semantic mismatch
- Value: 10/10; XSS / framework-behavior exploitation / authentication bypass.
- Chain: `-1 !== "https://www.digits.com".search(t.origin)` → postMessage/browser-message source and object-semantic mismatch, combined with a Host/Origin/reverse-proxy trust-boundary mismatch → the corresponding trust boundary is crossed → account takeover.
- Bypass: Send crafted messages from an unintended window or source, exploiting origin-boundary matching, an unbound source object, or deserialization differences; combine this with the Host/Origin/reverse-proxy trust mismatch to extend or complete the chain.
- Defensive anchor: Validate `event.origin`, `event.source`, message type, and schema exactly; prohibit wildcard origins; dispatch only minimum capabilities and never directly concatenate messages into DOM/URL/script or invoke privileged APIs. Add cross-component negative tests for the Host/Origin/reverse-proxy trust mismatch, ensuring validation and execution use the same subject, object, state, and normalized semantics.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 217790 · postMessage/browser-message source and object-semantic mismatch
- Value: 10/10; XSS / framework-behavior exploitation.
- Chain: `/admin/apps/$id` → postMessage/browser-message source and object-semantic mismatch, combined with browser/template/filter parsing differentials → the corresponding trust boundary is crossed → privilege elevation or administrative capability.
- Bypass: Send crafted messages from an unintended window or source, exploiting origin-boundary matching, an unbound source object, or deserialization differences; combine this with browser/template/filter parsing differences to extend or complete the chain.
- Defensive anchor: Validate `event.origin`, `event.source`, message type, and schema exactly; prohibit wildcard origins; dispatch only minimum capabilities and never directly concatenate messages into DOM/URL/script or invoke privileged APIs. Add cross-component negative tests for browser/template/filter parsing differences.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 314814 · postMessage/browser-message source and object-semantic mismatch
- Value: 10/10; XSS / framework-behavior exploitation / authentication bypass.
- Chain: `POST /oauth2/access_token` → postMessage/browser-message source and object-semantic mismatch, combined with OAuth/SSO callback and credential-lifecycle misbinding → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Send crafted messages from an unintended window or source, exploiting origin-boundary matching, an unbound source object, or deserialization differences; combine this with OAuth/SSO lifecycle misbinding to extend or complete the chain.
- Defensive anchor: Validate `event.origin`, `event.source`, message type, and schema exactly; prohibit wildcard origins; dispatch only minimum capabilities and never directly concatenate messages into DOM/URL/script or invoke privileged APIs. Add cross-component negative tests for OAuth/SSO callback and credential-lifecycle binding.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 1.
- HackerOne reports: 54.
- Full report IDs:
  - cure53/pentest-report-mozilla-vpn-apps-clients-03-2021
- HackerOne report IDs:
  - 894518, 463915, 423218, 1758132, 269349, 870615, 92472, 1031644, 398054, 217790, 869831, 422279, 1436558, 470553, 203912, 691977, 1567186, 129873
  - 1238528, 389108, 513105, 341925, 603764, 168116, 387544, 389076, 461308, 899954, 353784, 997198, 231053, 481472, 381356, 422043, 470519, 993670
  - 576532, 29328, 314814, 665722, 2089042, 499030, 110467, 662083, 868615, 1727221, 217745, 1851818, 646505, 602767, 56800, 207042, 1081167, 2371019

