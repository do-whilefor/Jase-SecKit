# Browser Parsing · Reference

Load after selecting the `browser-parser-sanitizer` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### cure53/pentest-report bitwarden · BWN-01-004 Desktop: Bypassable CSP rules in place
- Knowledge value: 9/10; XSS / framework-behavior exploitation.
- Chain: The attacker submits crafted HTML/SVG/XML, attributes, or content types → the sanitizer/CSP treats the input as safe → the browser reparses, mutates, or moves it into another context → script execution or UI takeover.
- Bypass: Use namespaces, mXSS, `srcdoc`, content-type differences, context switching, or policy gaps so the structure seen by the filter differs from the structure executed by the browser.
- Defensive anchor: Use a continuously updated sanitizer with a constrained configuration; encode for the final output context; deploy strict CSP, Trusted Types, and isolated iframes; add browser-differential and mutation-XSS regression corpora.

### cure53/pentest-report mailvelope · MV-01-007 Features in showModalDialog Branch expose Mailer to XSS
- Knowledge value: 9/10; XSS / cross-component attack chain.
- Chain: The attacker sends malicious Web/email/message content → a client extension or WebView renders it in a privileged context → script executes → extension APIs are called, local data is read, or further code executes.
- Bypass: Rendered content shares an origin, DOM, or bridge API with the privileged host, bypassing the ordinary Web sandbox.
- Defensive anchor: Use process/site isolation and a minimal bridge; disable Node integration and dangerous WebView capabilities; sanitize the final DOM strictly; enforce CSP/Trusted Types and minimize extension permissions.

## HackerOne Case Index

### 265943 · Browser/template/filter parsing differential bypass
- Knowledge value: 9/10; XSS / framework-behavior exploitation / cross-component attack chain.
- Chain: `https://snappublisher.snapchat.com/snaps/create/new` → browser/template/filter parsing differential bypass, combined with file-processing order and multi-parser semantic differences → the corresponding trust boundary is crossed → script execution in a trusted origin.
- Bypass: Use template expressions, SVG/HTML contexts, DOM mutation, JSONP, or encoding differences to bypass filtering/CSP and execute in a trusted origin; combine this with file-processing and multi-parser differences to extend or complete the chain.
- Defensive anchor: Encode for the final output context; use a mature structural sanitizer and prohibit string concatenation after sanitization; tighten CSP with nonces/hashes and remove unnecessary third-party scripts; regression-test the browser-parsed DOM and add cross-component negative tests for file-processing order and multi-parser semantics.

### 429298 · Browser/template/filter parsing differential bypass
- Knowledge value: 9/10; XSS / framework-behavior exploitation / subdomain takeover.
- Chain: `https://*.highwebmedia.com` → browser/template/filter parsing differential bypass → security controls and the final execution point disagree about subject, object, state, or input semantics → persistent script execution on a trusted page.
- Bypass: Use template expressions, SVG/HTML contexts, DOM mutation, JSONP, or encoding differences to bypass filtering/CSP and execute in a trusted origin.
- Defensive anchor: Encode for the final output context; use a mature structural sanitizer and prohibit string concatenation after sanitization; tighten CSP with nonces/hashes and remove unnecessary third-party scripts; regression-test the browser-parsed DOM.

### 1342009 · Browser/template/filter parsing differential bypass
- Knowledge value: 8/10; XSS / framework-behavior exploitation / authentication bypass.
- Chain: `https://gitlab.com/projects/new#blank_project` → browser/template/filter parsing differential bypass, combined with OAuth/SSO callback and credential-lifecycle misbinding → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Use template expressions, SVG/HTML contexts, DOM mutation, JSONP, or encoding differences to bypass filtering/CSP; combine this with OAuth/SSO callback and lifecycle misbinding.
- Defensive anchor: Encode for the final output context; use a mature structural sanitizer; prohibit string concatenation after sanitization; tighten CSP; regression-test the final DOM and add negative tests for OAuth/SSO binding.
