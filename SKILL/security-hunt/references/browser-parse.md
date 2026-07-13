# Browser Parsing · Reference


Load on demand after selecting the `browser-parser-sanitizer` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### cure53/pentest-report bitwarden · BWN-01-004 Desktop: Bypassable CSP rules in place
- Value: 9/10; XSS / framework-behavior exploitation.
- Chain: The attacker submits crafted HTML/SVG/XML, attributes, or content types → the sanitizer/CSP treats the input as safe → the browser reparses, mutates, or moves it into another context → script execution or UI takeover.
- Bypass: Use namespaces, mXSS, `srcdoc`, content-type differences, context switching, or policy gaps so the structure seen by the filter differs from the structure executed by the browser.
- Defensive anchor: Use a continuously updated sanitizer with a constrained configuration; encode for the final output context; deploy strict CSP, Trusted Types, and isolated iframes; add browser-differential and mutation-XSS regression corpora.

### cure53/pentest-report mailvelope · MV-01-007 Features in showModalDialog Branch expose Mailer to XSS
- Value: 9/10; XSS / cross-component attack chain.
- Chain: The attacker sends malicious Web/email/message content → a client extension or WebView renders it in a privileged context → script executes → extension APIs are called, local data is read, or further code executes.
- Bypass: Rendered content shares an origin, DOM, or bridge API with the privileged host, bypassing the ordinary Web sandbox.
- Defensive anchor: Use process/site isolation and a minimal bridge; disable Node integration and dangerous WebView capabilities; sanitize the final DOM strictly; enforce CSP/Trusted Types and minimize extension permissions.


## HackerOne Case Index


### 265943 · Browser/template/filter parsing differential bypass
- Value: 9/10; XSS / framework-behavior exploitation / cross-component attack chain.
- Chain: `https://snappublisher.snapchat.com/snaps/create/new` → browser/template/filter parsing differential bypass, combined with file-processing order and multi-parser semantic differences → the corresponding trust boundary is crossed → script execution in a trusted origin.
- Bypass: Use template expressions, SVG/HTML contexts, DOM mutation, JSONP, or encoding differences to bypass filtering/CSP and execute in a trusted origin; combine this with file-processing and multi-parser differences to extend or complete the chain.
- Defensive anchor: Encode for the final output context; use a mature structural sanitizer and prohibit string concatenation after sanitization; tighten CSP with nonces/hashes and remove unnecessary third-party scripts; regression-test the browser-parsed DOM and add cross-component negative tests for file-processing order and multi-parser semantics.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 429298 · Browser/template/filter parsing differential bypass
- Value: 9/10; XSS / framework-behavior exploitation / subdomain takeover.
- Chain: `https://*.highwebmedia.com` → browser/template/filter parsing differential bypass → security controls and the final execution point disagree about subject, object, state, or input semantics → persistent script execution on a trusted page.
- Bypass: Use template expressions, SVG/HTML contexts, DOM mutation, JSONP, or encoding differences to bypass filtering/CSP and execute in a trusted origin.
- Defensive anchor: Encode for the final output context; use a mature structural sanitizer and prohibit string concatenation after sanitization; tighten CSP with nonces/hashes and remove unnecessary third-party scripts; regression-test the browser-parsed DOM.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 1342009 · Browser/template/filter parsing differential bypass
- Value: 8/10; XSS / framework-behavior exploitation / authentication bypass.
- Chain: `https://gitlab.com/projects/new#blank_project` → browser/template/filter parsing differential bypass, combined with OAuth/SSO callback and credential-lifecycle misbinding → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Use template expressions, SVG/HTML contexts, DOM mutation, JSONP, or encoding differences to bypass filtering/CSP; combine this with OAuth/SSO callback and lifecycle misbinding.
- Defensive anchor: Encode for the final output context; use a mature structural sanitizer; prohibit string concatenation after sanitization; tighten CSP; regression-test the final DOM and add negative tests for OAuth/SSO binding.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 6.
- HackerOne reports: 37.
- Full report IDs:
  - cure53/pentest-report bitwarden
  - cure53/pentest-report frame
  - cure53/pentest-report mailvelope
  - cure53/pentest-report telekube
  - cure53/pentest-report dompurify
  - cure53/pentest-report remembear
- HackerOne report IDs:
  - 780285, 781281, 1404804, 779113, 630265, 845832, 781295, 1665658, 1103258, 250837, 1051029, 10373, 1694173, 1066007, 636278, 1010132, 1342009, 1693150
  - 942103, 1212822, 164224, 222692, 776684, 382625, 141463, 265943, 361951, 271007, 199779, 1805873, 983331, 429298, 1736317, 259100, 1212067, 632017
  - 1893186

