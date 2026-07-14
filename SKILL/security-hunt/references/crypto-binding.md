# Cryptographic Semantic Binding · Reference

Load after selecting the `crypto-semantic-binding` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### consensys/omisego-morevp-audit-2019-10 · 5.5 Merkle - The implementation does not enforce inclusion of leaf nodes.
- Knowledge value: 10/10; protocol-behavior exploitation / authentication bypass.
- Chain: The attacker obtains or constructs formally valid signatures, proofs, or metadata → exploits a gap in algorithm, context, or set validation → verification succeeds while object semantics are replaced, replayed, or omitted → authentication, update, or asset state is broken.
- Bypass: Algorithm confusion, missing domain separation, unverified inclusion, batch-verification cancellation, or replay makes “cryptographically valid” differ from “authorized for this business context.”
- Defensive anchor: Bind algorithms tightly to key types; apply domain separation and context binding; validate complete sets, leaves, and ordering; include nonces, versions, and anti-replay state; add single-item fallback tests for batch verification.

### nccgroup/NCC Group WhatsApp E001000M Report 2021-10-27 v1.2 · Compromised Backend or Infrastructure Can Force Non-Randomized Client Password Value and Weak OPAQUE Keys
- Knowledge value: 10/10; protocol-behavior exploitation / authentication bypass / cross-component attack chain.
- Chain: The attacker controls or compromises backup infrastructure → returns selected or reflected OPRF/group elements → the client continues and derives a non-randomized password value or weak OPAQUE key → offline-guessing cost is reduced or backup-key confidentiality is weakened.
- Bypass: The client does not fully validate OPRF group elements, non-zero constraints, or protocol-message binding, allowing a malicious server to reflect or choose degenerate input and defeat the intended randomization guarantee.
- Defensive anchor: Require canonical encoding, curve/subgroup membership, and non-zero checks for all group elements; bind role, session, version, and message order into the transcript; reject reflectable input; validate with official vectors and a malicious-server model.

### nccgroup/NCC Group EthereumFoundation ETHF002 Report 2021-01-20 v1.0 · Missing Checks in Aggregate Verify
- Knowledge value: 9/10; protocol-behavior exploitation / authentication bypass.
- Chain: The attacker supplies aggregate-signature input with duplicate messages or malicious public-key relationships → the verifier checks count and pairing equations but not message distinctness → rogue-key-style forgery conditions or false acceptance become possible; zero-length boundaries may also trigger panic or undefined behavior.
- Bypass: The implementation omits the message-distinctness condition required by the aggregate-signature security proof, applying a mathematically valid equation to an unsupported input set.
- Defensive anchor: Implement `AggregateVerify` exactly as specified by BLS; require non-empty, equal-length inputs, distinct messages, and subgroup membership; avoid unnecessary unsafe/transmute use; add rogue-key, duplicate-message, and empty-set vectors.

### nccgroup/NCC Group Google EncryptedBackup 2018-10-10 v1.0 · Google Can Force Applications To Restore From Arbitrary Backup
- Knowledge value: 9/10; protocol-behavior exploitation / state confusion / cross-component attack chain.
- Chain: An attacker or privileged platform selects another valid backup or key object → the restore service passes basic cryptographic checks → the application accepts data from the wrong origin, time, or purpose → rollback, data replacement, or invariant failure occurs.
- Bypass: A cryptographically valid backup block or key is reused while unauthenticated context metadata is replaced, separating successful verification from business ownership.
- Defensive anchor: Authenticate all metadata with AEAD; domain-separate keys by application and purpose; enforce versions and monotonic time; show and verify provenance before restore; add negative tests for cross-application, cross-version, and stale backups.
