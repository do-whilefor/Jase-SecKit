---
id: unicode-normalization
group: normalize
reference: ../references/unicode.md
---

# Unicode Normalization

**Use for:** domain/Origin allowlists, paths and filenames, keyword filters, account identifiers, protocol fields, and signature inputs.

**Misalignment to find:** A security control operates on one character, encoding, or boundary representation while a later component derives a different meaning after decoding, case folding, IDNA processing, truncation, or normalization.

## Baseline

- One logical identifier may have multiple character or byte representations.
- Unicode normalization, IDNA, case conversion, percent decoding, truncation, NUL bytes, and different character sets can change meaning.
- Focus on differences between the validation view and the final consumer view.
- Record raw code points, encoded bytes, canonical values at each stage, and the final object.

## Validation Order

1. Enumerate character sets, decode counts, and normalization forms at every layer.
2. Construct representations that are equivalent, visually similar, or become equivalent after truncation.
3. When signatures or caches are involved, compare keys and values before and after normalization.
4. Judge the result from the final consumer’s parse.

## Variant Axes

- Encoding: UTF-8/16, percent encoding, entities, Punycode, IDNA
- Normalization: NFC/NFD/NFKC/NFKD, case folding, full-width/half-width conversion
- Boundary: byte length, character length, truncation, NUL, invisible characters
- Comparison point: registration, validation, storage, query, routing, display

## Combination Paths

- `path`: Path Canonicalization
- `params`: Parameter Parsing
- `browser-parse`: Browser Parsing
