# Cryptographic Semantic Binding · Reference

Load after selecting the `crypto-semantic-binding` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### 5.5 Merkle - The implementation does not enforce inclusion of leaf nodes.

- Source: `consensys/omisego-morevp-audit-2019-10`
- Reported focus: 5.5 Merkle - The implementation does not enforce inclusion of leaf nodes.
- Transferable test ideas:
  - Algorithm confusion, missing domain separation, unverified inclusion, batch-verification cancellation, or replay
    makes “cryptographically valid” differ from “authorized for this business context.”.
- Defensive anchor:
  - Bind algorithms tightly to key types.
  - Apply domain separation and context binding.
  - Validate complete sets, leaves, and ordering.
  - Include nonces, versions, and anti-replay state.
  - Add single-item fallback tests for batch verification.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.

### Compromised Backend or Infrastructure Can Force Non-Randomized Client Password Value and Weak OPAQUE Keys

- Source: `nccgroup/NCC Group WhatsApp E001000M Report 2021-10-27 v1.2`
- Reported focus: Compromised Backend or Infrastructure Can Force Non-Randomized Client Password Value and Weak OPAQUE Keys
- Transferable test ideas:
  - The client does not fully validate OPRF group elements, non-zero constraints, or protocol-message binding,
    allowing a malicious server to reflect or choose degenerate input and defeat the intended randomization guarantee.
- Defensive anchor:
  - Require canonical encoding, curve/subgroup membership, and non-zero checks for all group elements.
  - Bind role, session, version, and message order into the transcript.
  - Reject reflectable input.
  - Validate with official vectors and a malicious-server model.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.

### Missing Checks in Aggregate Verify

- Source: `nccgroup/NCC Group EthereumFoundation ETHF002 Report 2021-01-20 v1.0`
- Reported focus: Missing Checks in Aggregate Verify
- Transferable test ideas:
  - The implementation omits the message-distinctness condition required by the aggregate-signature security proof,
    applying a mathematically valid equation to an unsupported input set.
- Defensive anchor:
  - Implement `AggregateVerify` exactly as specified by BLS.
  - Require non-empty, equal-length inputs, distinct messages, and subgroup membership.
  - Avoid unnecessary unsafe/transmute use.
  - Add rogue-key, duplicate-message, and empty-set vectors.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.

### Google Can Force Applications To Restore From Arbitrary Backup

- Source: `nccgroup/NCC Group Google EncryptedBackup 2018-10-10 v1.0`
- Reported focus: Google Can Force Applications To Restore From Arbitrary Backup
- Transferable test ideas:
  - A cryptographically valid backup block or key is reused while unauthenticated context metadata is replaced, separating successful verification from business ownership.
- Defensive anchor:
  - Authenticate all metadata with AEAD.
  - Domain-separate keys by application and purpose.
  - Enforce versions and monotonic time.
  - Show and verify provenance before restore.
  - Add negative tests for cross-application, cross-version, and stale backups.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
