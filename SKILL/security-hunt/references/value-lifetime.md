# Values & Lifetimes · Reference


Load on demand after selecting the `low-level-value-lifetime` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### cure53/pentest-report fluent · FLU-01-003 fluent-bit/in_forward: Heap overflow via negative length
- Value: 8/10; other / framework-behavior exploitation.
- Chain: The attacker supplies a crafted protocol field, file, or message → triggers integer truncation, negative length, out-of-bounds indexing, or use-after-free → out-of-bounds read/write or crash → memory disclosure or code execution under controllable conditions.
- Bypass: Type width, sign, or lifetime differs between the checking stage and allocation/indexing stage, turning a value that passed validation into a dangerous value later.
- Defensive anchor: Use checked arithmetic and explicit upper bounds; standardize signed/unsigned conversions; validate multiply-add overflow before allocation; use ASan/UBSan/TSan, fuzzing, and structured parsers.

### nccgroup/NCC Group O1LabsOperatingCo Report 2022-02-21 v1.0 · Missing Bounds Validation of Signature Values
- Value: 7/10; protocol-behavior exploitation / type confusion.
- Chain: The attacker obtains or creates a valid signature → encodes a scalar outside the canonical range but equivalent modulo the group order → the verifier reduces and accepts it → deduplication, transaction IDs, caches, or cross-implementation consistency diverge.
- Bypass: The serialization layer accepts non-canonical numeric values while mathematical verification reduces modulo the group order, so multiple byte strings represent the same valid signature value.
- Defensive anchor: Before verification, enforce canonical encoding, range, and subgroup checks for every scalar and point; reject reducible out-of-range values; standardize serialization; add cross-implementation differential tests and signature-byte uniqueness tests.


## Source Coverage

- Full reports: 6.
- HackerOne reports: 0.
- Full report IDs:
  - cure53/pentest-report fluent
  - x41-d-sec/X41-RandomX-Audit-2019-Final-Report-Public
  - cure53/pentest-report dovecot
  - cure53/pentest-report openpgpjs
  - nccgroup/NCC Group O1LabsOperatingCo Report 2022-02-21 v1.0
  - nccgroup/NCC Group Zephyr MCUboot Research Report 2020-05-26 v1.0

