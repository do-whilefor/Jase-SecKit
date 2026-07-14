# Values & Lifetimes · Reference

Load after selecting the `low-level-value-lifetime` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### cure53/pentest-report fluent · FLU-01-003 fluent-bit/in_forward: Heap overflow via negative length
- Knowledge value: 8/10; other / framework-behavior exploitation.
- Chain: The attacker supplies a crafted protocol field, file, or message → triggers integer truncation, negative length, out-of-bounds indexing, or use-after-free → out-of-bounds read/write or crash → memory disclosure or code execution under controllable conditions.
- Bypass: Type width, sign, or lifetime differs between the checking stage and allocation/indexing stage, turning a value that passed validation into a dangerous value later.
- Defensive anchor: Use checked arithmetic and explicit upper bounds; standardize signed/unsigned conversions; validate multiply-add overflow before allocation; use ASan/UBSan/TSan, fuzzing, and structured parsers.

### nccgroup/NCC Group O1LabsOperatingCo Report 2022-02-21 v1.0 · Missing Bounds Validation of Signature Values
- Knowledge value: 7/10; protocol-behavior exploitation / type confusion.
- Chain: The attacker obtains or creates a valid signature → encodes a scalar outside the canonical range but equivalent modulo the group order → the verifier reduces and accepts it → deduplication, transaction IDs, caches, or cross-implementation consistency diverge.
- Bypass: The serialization layer accepts non-canonical numeric values while mathematical verification reduces modulo the group order, so multiple byte strings represent the same valid signature value.
- Defensive anchor: Before verification, enforce canonical encoding, range, and subgroup checks for every scalar and point; reject reducible out-of-range values; standardize serialization; add cross-implementation differential tests and signature-byte uniqueness tests.
