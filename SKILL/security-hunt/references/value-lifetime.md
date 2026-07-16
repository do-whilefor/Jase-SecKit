# Values & Lifetimes · Reference

Load after selecting the `low-level-value-lifetime` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### FLU-01-003 fluent-bit/in_forward: Heap overflow via negative length

- Source: `cure53/pentest-report fluent`
- Reported focus: FLU-01-003 fluent-bit/in_forward: Heap overflow via negative length
- Transferable test ideas:
  - Type width, sign, or lifetime differs between the checking stage and allocation/indexing stage, turning a value that passed validation into a dangerous value later.
- Defensive anchor:
  - Use checked arithmetic and explicit upper bounds.
  - Standardize signed/unsigned conversions.
  - Validate multiply-add overflow before allocation.
  - Use ASan/UBSan/TSan, fuzzing, and structured parsers.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.

### Missing Bounds Validation of Signature Values

- Source: `nccgroup/NCC Group O1LabsOperatingCo Report 2022-02-21 v1.0`
- Reported focus: Missing Bounds Validation of Signature Values
- Transferable test ideas:
  - The serialization layer accepts non-canonical numeric values while mathematical verification reduces modulo the
    group order, so multiple byte strings represent the same valid signature value.
- Defensive anchor:
  - Before verification, enforce canonical encoding, range, and subgroup checks for every scalar and point.
  - Reject reducible out-of-range values.
  - Standardize serialization.
  - Add cross-implementation differential tests and signature-byte uniqueness tests.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
