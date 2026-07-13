# Unicode Normalization · Reference


Load on demand after selecting the `unicode-normalization` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## HackerOne Case Index


### 629745 · Unicode/encoding/normalization and boundary-matching difference
- Value: 10/10; framework-behavior exploitation / protocol-behavior exploitation / XSS.
- Chain: A crafted Starbucks URL with double encoding → Unicode/encoding/normalization and boundary-matching difference → security controls and the final execution point disagree about subject, object, state, or input semantics → script execution in a trusted origin.
- Bypass: Use IDN, Unicode, NUL bytes, case, trailing dots/slashes, double encoding, or regex-boundary defects to bypass string-level validation.
- Defensive anchor: Canonicalize and decode exactly as the final consumer does before applying a structured allowlist; reject multiple encodings and invisible/confusable characters; compare domain labels exactly after IDNA processing; permit only one canonical representation for paths and parameters.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 716761 · Unicode/encoding/normalization and boundary-matching difference
- Value: 9/10; framework-behavior exploitation / protocol-behavior exploitation / XSS.
- Chain: `https://hackerone.com/reports/629745` → Unicode/encoding/normalization difference, combined with browser/template/filter parsing differences → the corresponding trust boundary is crossed → script execution in a trusted origin.
- Bypass: Use normalization or encoding ambiguity and combine it with browser-side reparsing or filter differences.
- Defensive anchor: Canonicalize once under final-consumer rules; reject ambiguity; use exact IDNA label matching and one canonical path/parameter form; add browser-parsing cross-component regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 861940 · Unicode/encoding/normalization and boundary-matching difference
- Value: 9/10; framework-behavior exploitation / protocol-behavior exploitation / authentication bypass.
- Chain: A crafted OAuth authorization URL → Unicode/encoding/normalization difference, combined with OAuth/SSO callback and credential-lifecycle misbinding → the corresponding trust boundary is crossed → token, key, session, or cloud-credential disclosure.
- Bypass: Use normalization ambiguity to bypass string-level controls, then combine it with OAuth/SSO callback or lifecycle misbinding.
- Defensive anchor: Canonicalize before structured matching, reject ambiguous representations, and add final-consumer regressions for OAuth/SSO callback and credential binding.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 0.
- HackerOne reports: 39.
- HackerOne report IDs:
  - 184857, 781265, 260938, 2054184, 1553301, 1354335, 979204, 317931, 232174, 716761, 240886, 185794, 278095, 1102764, 185957, 1591412, 1565615, 268984
  - 1086108, 271324, 302997, 836649, 1285245, 1046630, 1223565, 861940, 170310, 223625, 629745, 385145, 2416725, 449617, 1557449, 1891474, 184661, 172933
  - 395845, 942146, 251572

