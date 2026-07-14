# Unicode Normalization · Reference

Load after selecting the `unicode-normalization` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## HackerOne Case Index

### 629745 · Unicode/encoding/normalization and boundary-matching difference
- Knowledge value: 10/10; framework-behavior exploitation / protocol-behavior exploitation / XSS.
- Chain: A crafted Starbucks URL with double encoding → Unicode/encoding/normalization and boundary-matching difference → security controls and the final execution point disagree about subject, object, state, or input semantics → script execution in a trusted origin.
- Bypass: Use IDN, Unicode, NUL bytes, case, trailing dots/slashes, double encoding, or regex-boundary defects to bypass string-level validation.
- Defensive anchor: Canonicalize and decode exactly as the final consumer does before applying a structured allowlist; reject multiple encodings and invisible/confusable characters; compare domain labels exactly after IDNA processing; permit only one canonical representation for paths and parameters.

### 716761 · Unicode/encoding/normalization and boundary-matching difference
- Knowledge value: 9/10; framework-behavior exploitation / protocol-behavior exploitation / XSS.
- Chain: `https://hackerone.com/reports/629745` → Unicode/encoding/normalization difference, combined with browser/template/filter parsing differences → the corresponding trust boundary is crossed → script execution in a trusted origin.
- Bypass: Use normalization or encoding ambiguity and combine it with browser-side reparsing or filter differences.
- Defensive anchor: Canonicalize once under final-consumer rules; reject ambiguity; use exact IDNA label matching and one canonical path/parameter form; add browser-parsing cross-component regressions.

### 861940 · Unicode/encoding/normalization and boundary-matching difference
- Knowledge value: 9/10; framework-behavior exploitation / protocol-behavior exploitation / authentication bypass.
- Chain: A crafted OAuth authorization URL → Unicode/encoding/normalization difference, combined with OAuth/SSO callback and credential-lifecycle misbinding → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Use normalization ambiguity to bypass string-level controls, then combine it with OAuth/SSO callback or lifecycle misbinding.
- Defensive anchor: Canonicalize before structured matching, reject ambiguous representations, and add final-consumer regressions for OAuth/SSO callback and credential binding.
