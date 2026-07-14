# Cross-Origin Channels · Reference

Load after selecting the `cross-origin-message-channel` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### cure53/pentest-report-mozilla-vpn-apps-clients-03-2021 · FVP-02-014 General: Cross-site WebSocket hijacking
- Knowledge value: 10/10; authentication bypass / protocol-behavior exploitation / cross-component attack chain.
- Chain: The victim logs in to the target site → visits an attacker page → the page opens a cross-site WebSocket using the victim’s cookies → the attacker invokes local or cloud privileged functions bidirectionally or reads responses.
- Bypass: WebSockets do not automatically inherit traditional CSRF protections; without Origin or handshake-token validation, the victim’s authenticated state is reused.
- Defensive anchor: Strictly allowlist Origin; use one-time, session-bound handshake tokens; do not authenticate solely with cookies; authorize every message at object level and restrict local control interfaces.

## HackerOne Case Index

### 129873 · postMessage/browser-message source and object-semantic mismatch
- Knowledge value: 10/10; XSS / framework-behavior exploitation / authentication bypass.
- Chain: `-1 !== "https://www.digits.com".search(t.origin)` → postMessage/browser-message source and object-semantic mismatch, combined with a Host/Origin/reverse-proxy trust-boundary mismatch → the corresponding trust boundary is crossed → account takeover.
- Bypass: Send crafted messages from an unintended window or source, exploiting origin-boundary matching, an unbound source object, or deserialization differences; combine this with the Host/Origin/reverse-proxy trust mismatch to extend or complete the chain.
- Defensive anchor: Validate `event.origin`, `event.source`, message type, and schema exactly; prohibit wildcard origins; dispatch only minimum capabilities and never directly concatenate messages into DOM/URL/script or invoke privileged APIs. Add cross-component negative tests for the Host/Origin/reverse-proxy trust mismatch, ensuring validation and execution use the same subject, object, state, and normalized semantics.

### 217790 · postMessage/browser-message source and object-semantic mismatch
- Knowledge value: 10/10; XSS / framework-behavior exploitation.
- Chain: `/admin/apps/$id` → postMessage/browser-message source and object-semantic mismatch, combined with browser/template/filter parsing differentials → the corresponding trust boundary is crossed → privilege elevation or administrative capability.
- Bypass: Send crafted messages from an unintended window or source, exploiting origin-boundary matching, an unbound source object, or deserialization differences; combine this with browser/template/filter parsing differences to extend or complete the chain.
- Defensive anchor: Validate `event.origin`, `event.source`, message type, and schema exactly; prohibit wildcard origins; dispatch only minimum capabilities and never directly concatenate messages into DOM/URL/script or invoke privileged APIs. Add cross-component negative tests for browser/template/filter parsing differences.

### 314814 · postMessage/browser-message source and object-semantic mismatch
- Knowledge value: 10/10; XSS / framework-behavior exploitation / authentication bypass.
- Chain: `POST /oauth2/access_token` → postMessage/browser-message source and object-semantic mismatch, combined with OAuth/SSO callback and credential-lifecycle misbinding → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Send crafted messages from an unintended window or source, exploiting origin-boundary matching, an unbound source object, or deserialization differences; combine this with OAuth/SSO lifecycle misbinding to extend or complete the chain.
- Defensive anchor: Validate `event.origin`, `event.source`, message type, and schema exactly; prohibit wildcard origins; dispatch only minimum capabilities and never directly concatenate messages into DOM/URL/script or invoke privileged APIs. Add cross-component negative tests for OAuth/SSO callback and credential-lifecycle binding.
