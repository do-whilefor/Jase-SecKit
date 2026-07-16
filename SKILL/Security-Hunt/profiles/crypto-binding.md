---
id: crypto-semantic-binding
group: crypto
reference: ../references/crypto-binding.md
---

# Cryptographic Semantic Binding

**Use for:** digital signatures, Merkle proofs, zero-knowledge proofs, batch/aggregate verification, PAKE/OPRF, and secure-update metadata.

**Misalignment to find:** Mathematical verification may be correct while the algorithm, key type, domain, context,
object type, ordering, uniqueness, inclusion, version, or replay state is not bound.

## Baseline

- Cryptographic validity must be bound to the complete business meaning.
- Look for algorithm/key confusion, missing domain separation, unbound object/version/order, missing set inclusion, duplicate counting, or replay.
- Focus on verifiers that return success for an object other than the one the business expects.
- Record message encoding, domain tag, algorithm, key type, set members, nonce, version, and consumed object.

## Validation Order

1. Write down the exact bytes and relationships covered by the verification function.
2. List every context element that the business requires to be bound.
3. Substitute the algorithm, object type, ordering, member, version, and session material.
4. Test duplication, truncation, concatenation, batch cancellation, and replay.
5. Prove that the wrong object is accepted.

## Variant Axes

- Algorithm, parameters, key type, curve/group, and version
- Domain separation, context, object type, ordering, uniqueness, and inclusion
- Signed/proven object versus the object consumed by business logic
- Replay state, randomness, sequence number, audience, and protocol role

## Combination Paths

- `xml-signature`: XML Signature Consumption
- `offline-verifier`: Offline Verifiers
- `tokens`: Token Lifecycle
