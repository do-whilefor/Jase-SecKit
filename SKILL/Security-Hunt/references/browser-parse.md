# Browser Parsing · Reference

Load after selecting the `browser-parser-sanitizer` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### BWN-01-004 Desktop: Bypassable CSP rules in place

- Source: `cure53/pentest-report bitwarden`
- Source topic: BWN-01-004 Desktop: Bypassable CSP rules in place
- Transferable test ideas:
  - Use namespaces, mXSS, `srcdoc`, content-type differences, context switching, or policy gaps so the structure seen
    by the filter differs from the structure executed by the browser.
- Defensive anchor:
  - Use a continuously updated sanitizer with a constrained configuration.
  - Encode for the final output context.
  - Deploy strict CSP, Trusted Types, and isolated iframes.
  - Add browser-differential and mutation-XSS regression corpora.

### MV-01-007 Features in showModalDialog Branch expose Mailer to XSS

- Source: `cure53/pentest-report mailvelope`
- Source topic: MV-01-007 Features in showModalDialog Branch expose Mailer to XSS
- Transferable test ideas:
  - Rendered content shares an origin, DOM, or bridge API with the privileged host, bypassing the ordinary Web sandbox.
- Defensive anchor:
  - Use process/site isolation and a minimal bridge.
  - Disable Node integration and dangerous WebView capabilities.
  - Sanitize the final DOM strictly.
  - Enforce CSP/Trusted Types and minimize extension permissions.
