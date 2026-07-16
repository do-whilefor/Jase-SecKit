# Cryptographic Semantic Binding · Reference

Load after selecting the `crypto-semantic-binding` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### 5.5 Merkle - The implementation does not enforce inclusion of leaf nodes.

- Source: `consensys/omisego-morevp-audit-2019-10`
- Source topic: 5.5 Merkle - The implementation does not enforce inclusion of leaf nodes.
- Transferable test ideas:
  - Algorithm confusion, missing domain separation, unverified inclusion, batch-verification cancellation, or replay
    makes “cryptographically valid” differ from “authorized for this business context.”
- Defensive anchor:
  - Bind algorithms tightly to key types.
  - Apply domain separation and context binding.
  - Validate complete sets, leaves, and ordering.
  - Include nonces, versions, and anti-replay state.
  - Add single-item fallback tests for batch verification.

### opaque-ke: Identity Element Accepted During Deserialization

- Source URL: https://www.nccgroup.com/media/0uspzge5/_ncc_group_whatsappllc_opaque_report_2021-12-10_v13.pdf
- Source locator: pp. 4-6, NCC-E001000K-004.
- Reported boundary:
  - The public audit reports that a deserialized group element was not rejected
    when it was the identity element. Later operations could collapse to
    identity-derived results and could make `export_key` known.
- Transferable test ideas:
  - Test canonical decoding, curve and subgroup membership, and identity
    rejection separately at every untrusted group-element input.
  - Trace an accepted degenerate element to the exact derived key or
    authentication decision; parser acceptance alone is not the impact.
- Impact closure:
  - Prove which derived key becomes predictable, where that key is consumed,
    and what protected object or action it exposes.
- Defensive anchor:
  - Reject the identity element after deserialization and before every protocol
    operation that assumes a non-identity group member.
  - Add negative vectors for non-canonical, off-curve, wrong-subgroup, and
    identity encodings.

### opaque-ke: Reflected OPRF Input Removes Password Randomization

- Source URL: https://www.nccgroup.com/media/0uspzge5/_ncc_group_whatsappllc_opaque_report_2021-12-10_v13.pdf
- Source locator: pp. 6-8, NCC-E001000K-010; pp. 18-19, NCC-E001000K-005.
- Reported boundary:
  - The public audit reports that a malicious server could reflect a client
    OPRF value and force a non-randomized client password value.
- Transferable test ideas:
  - Treat role and message provenance as cryptographic context: replay or
    reflect each peer-supplied element into every structurally compatible slot.
  - Compare honest-server, reflected-input, and fresh-session transcripts at
    the derived-value boundary.
- Distinguishing condition:
  - Do not merge this adversarial reflection with the separate negligible-
    probability case of an honestly generated random scalar being zero.
- Impact closure:
  - Prove the changed password-derived material and the capability it enables;
    loss of an intended randomization property is not by itself the final harm.
  - Record whether an envelope nonce, authentication tag, ciphertext,
    `export_key`, or `auth_key` is exposed and measure the slow-hash cost; without
    a usable guess-verification path, the password-impact chain is incomplete.
- Defensive anchor:
  - Bind role, message type, session, version, and order into the transcript.
  - Reject reflected values where the protocol requires independent peer input,
    and include malicious-server reflection vectors.

### Missing Checks in Aggregate Verify

- Source: `nccgroup/NCC Group EthereumFoundation ETHF002 Report 2021-01-20 v1.0`
- Source topic: Missing Checks in Aggregate Verify
- Transferable test ideas:
  - The implementation omits the message-distinctness condition required by the aggregate-signature security proof,
    applying a mathematically valid equation to an unsupported input set.
- Defensive anchor:
  - Implement `AggregateVerify` exactly as specified by BLS.
  - Require non-empty, equal-length inputs, distinct messages, and subgroup membership.
  - Avoid unnecessary unsafe/transmute use.
  - Add rogue-key, duplicate-message, and empty-set vectors.

### Google Can Force Applications To Restore From Arbitrary Backup

- Source URL: https://www.nccgroup.com/media/2biaan4n/_final_public_report_ncc_group_google_encryptedbackup_2018-10-10_v10.pdf
- Source locator: GmsCore Table of Findings, finding 027.
- Reported boundary:
  - The public report lists a finding that Google could force applications to
    restore arbitrary backup data, but its public finding text does not expose
    enough mechanics to support a metadata-specific reproduction recipe.
- Transferable test ideas:
  - Separate ciphertext integrity from restore authority. Vary application,
    account, device, backup generation, version, age, and provider-selected
    manifest while observing which provenance the client authenticates.
- Source limitation:
  - Do not cite “unauthenticated metadata replacement” as a fact from this
    public report unless another primary source establishes it.
- Impact closure:
  - Prove which unauthorized backup the provider can select, which application
    accepts it, what state changes after restore, and what user or device
    authorization is bypassed.
- Defensive anchor:
  - Authenticate the restore manifest, application identity, owner, purpose,
    version, and freshness together with the encrypted data.
  - Require an explicit authorized restore decision and add cross-application,
    cross-account, cross-version, rollback, and stale-backup tests.
