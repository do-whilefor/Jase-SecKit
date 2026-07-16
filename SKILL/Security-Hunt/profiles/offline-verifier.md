---
id: offline-verifier-exposure
group: crypto
reference: ../references/offline-verifier.md
---

# Offline Verifiers

**Use for:** challenge-response authentication, remote-management protocols, VPN/Wi-Fi, custom handshakes, and PAKE pre-flows.

**Misalignment to find:** An unauthenticated handshake exposes stable material that lets an attacker verify password
guesses offline, converting online rate limits and lockouts into offline cracking.

## Baseline

- An attacker should not receive a stable verifier that independently determines whether a password guess is correct.
- Look for salted hashes, MACs, predictable challenges, or replayable material leaked by the handshake.
- Focus on protocols that provide evidence for online authentication while enabling unlimited offline guesses.
- Record unauthenticated messages, password-derivation inputs, challenge randomness, and the offline decision function.

## Validation Order

1. Collect the complete handshake without authenticating.
2. Determine which fields are directly or indirectly derived from the password.
3. Construct offline guesses and verify whether correctness can be decided without server interaction.
4. Test replay, challenge prediction, and user enumeration.
5. Quantify offline cost and the bypass of online policy.

## Variant Axes

- Unauthenticated challenges, responses, salts, MACs, hashes, and identifiers
- Password-derivation inputs and predictable fields
- Existence of a correctness function that requires no server interaction
- Challenge randomness, replay, user enumeration, and cost parameters

## Combination Paths

- `crypto-binding`: Cryptographic Semantic Binding
- `auth-state`: Authentication State
