# Cryptographic Semantic Binding · Reference


Load on demand after selecting the `crypto-semantic-binding` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### consensys/omisego-morevp-audit-2019-10 · 5.5 Merkle - The implementation does not enforce inclusion of leaf nodes.
- Value: 10/10; protocol-behavior exploitation / authentication bypass.
- Chain: The attacker obtains or constructs formally valid signatures, proofs, or metadata → exploits a gap in algorithm, context, or set validation → verification succeeds while object semantics are replaced, replayed, or omitted → authentication, update, or asset state is broken.
- Bypass: Algorithm confusion, missing domain separation, unverified inclusion, batch-verification cancellation, or replay makes “cryptographically valid” differ from “authorized for this business context.”
- Defensive anchor: Bind algorithms tightly to key types; apply domain separation and context binding; validate complete sets, leaves, and ordering; include nonces, versions, and anti-replay state; add single-item fallback tests for batch verification.

### nccgroup/NCC Group WhatsApp E001000M Report 2021-10-27 v1.2 · Compromised Backend or Infrastructure Can Force Non-Randomized Client Password Value and Weak OPAQUE Keys
- Value: 10/10; protocol-behavior exploitation / authentication bypass / cross-component attack chain.
- Chain: The attacker controls or compromises backup infrastructure → returns selected or reflected OPRF/group elements → the client continues and derives a non-randomized password value or weak OPAQUE key → offline-guessing cost is reduced or backup-key confidentiality is weakened.
- Bypass: The client does not fully validate OPRF group elements, non-zero constraints, or protocol-message binding, allowing a malicious server to reflect or choose degenerate input and defeat the intended randomization guarantee.
- Defensive anchor: Require canonical encoding, curve/subgroup membership, and non-zero checks for all group elements; bind role, session, version, and message order into the transcript; reject reflectable input; validate with official vectors and a malicious-server model.

### nccgroup/NCC Group EthereumFoundation ETHF002 Report 2021-01-20 v1.0 · Missing Checks in Aggregate Verify
- Value: 9/10; protocol-behavior exploitation / authentication bypass.
- Chain: The attacker supplies aggregate-signature input with duplicate messages or malicious public-key relationships → the verifier checks count and pairing equations but not message distinctness → rogue-key-style forgery conditions or false acceptance become possible; zero-length boundaries may also trigger panic or undefined behavior.
- Bypass: The implementation omits the message-distinctness condition required by the aggregate-signature security proof, applying a mathematically valid equation to an unsupported input set.
- Defensive anchor: Implement `AggregateVerify` exactly as specified by BLS; require non-empty, equal-length inputs, distinct messages, and subgroup membership; avoid unnecessary unsafe/transmute use; add rogue-key, duplicate-message, and empty-set vectors.

### nccgroup/NCC Group Google EncryptedBackup 2018-10-10 v1.0 · Google Can Force Applications To Restore From Arbitrary Backup
- Value: 9/10; protocol-behavior exploitation / state confusion / cross-component attack chain.
- Chain: An attacker or privileged platform selects another valid backup or key object → the restore service passes basic cryptographic checks → the application accepts data from the wrong origin, time, or purpose → rollback, data replacement, or invariant failure occurs.
- Bypass: A cryptographically valid backup block or key is reused while unauthenticated context metadata is replaced, separating successful verification from business ownership.
- Defensive anchor: Authenticate all metadata with AEAD; domain-separate keys by application and purpose; enforce versions and monotonic time; show and verify provenance before restore; add negative tests for cross-application, cross-version, and stale backups.


## Source Coverage

- Full reports: 21.
- HackerOne reports: 0.
- Full report IDs:
  - consensys/omisego-morevp-audit-2019-10
  - cure53/pentest-report openkeychain
  - cure53/pentest-report Subrosa-may2014
  - isec-partners/ncc docker notary audit 2015 07 31
  - nccgroup/NCC Group Keybase KB2018 Public Report 2019-02-27 v1.3
  - nccgroup/NCC Group Qredo Apache Milagro MPC Cryptographic Review 2020-07-16 v1.3
  - nccgroup/NCC Group WhatsApp E001000M Report 2021-10-27 v1.2
  - nccgroup/NCC Group WhatsAppLLC OPAQUE Report 2021-12-10 v1.3
  - nccgroup/NCC Group ZenBlockchainFoundation E001741 Report 2021-11-29 v1.2
  - nccgroup/NCC-Group-Public-Report-VPN-by-Google-One-v1.0
  - trailofbits/nucypher
  - x41-d-sec/X41-go-tuf-Audit-2023-Final-Report-PUBLIC
  - x41-d-sec/X41-in-toto-Audit-2023-Final-Report-PUBLIC
  - nccgroup/NCC Group EthereumFoundation ETHF002 Report 2021-01-20 v1.0
  - nccgroup/NCC Group Google EncryptedBackup 2018-10-10 v1.0
  - nccgroup/NCC Group ProtocolLabs PRLB007 Report 2020-10-20 v1.0
  - nccgroup/NCC Group Zcash ZCHX006 Report 2020-09-03 v2.0
  - nettitude/technical report linux foundation iroha march 2018 v1
  - cure53/pentest-report cyph
  - nccgroup/NCC Group ProtocolLabs FilecoinGroth16 Report 2021-06-02
  - quarkslab/OSTIF-QuarksLab-Monero-Bulletproofs-Final2

