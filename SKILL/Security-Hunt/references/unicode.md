# Unicode Normalization · Reference

Load after selecting the `unicode-normalization` Profile and forming a current-target hypothesis.

## Use Rule

- Use Unicode specifications to identify equivalence, normalization, case, script, and identifier assumptions.
- Record raw code points and every normalized representation used by validation, storage, lookup, routing, and display.
- Prove a security-relevant identity, boundary, route, or policy difference independently.

## Curated Sources

### Unicode Standard Annex #15 · Unicode Normalization Forms

- Source URL: https://www.unicode.org/reports/tr15/
- Transferable test ideas:
  - Compare NFC, NFD, NFKC, and NFKD handling across validators, databases, filesystems, frameworks, and final consumers.
  - Test normalization order relative to case folding, decoding, allowlist matching, storage, and lookup.
  - Use code-point-level evidence instead of relying only on visual appearance.
- Defensive anchor:
  - Choose one documented normalization policy and apply it before security-sensitive comparison and storage.
  - Preserve the original value separately only when required and never mix comparison policies across layers.

### Unicode Technical Standard #39 · Unicode Security Mechanisms

- Source URL: https://www.unicode.org/reports/tr39/
- Transferable test ideas:
  - Test confusable identifiers, mixed scripts, invisible characters, identifier restrictions, and display-versus-lookup differences.
  - Compare registration, login, search, routing, allowlists, certificates, domains, and audit display.
- Defensive anchor:
  - Apply identifier profiles, script restrictions, confusable detection, and unambiguous security displays where appropriate.
