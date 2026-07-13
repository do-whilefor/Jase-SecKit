---
name: Cryptographic Semantics
description: Binding between mathematical verification results and business objects, protocol context, offline-verification material, or the final consumer. Use for authorized testing of cryptographic semantic binding, offline verifiers, and XML signature consumption.
user-invocable: false
allowed-tools: Read Grep Glob Bash
---

# Cryptographic Semantics

## Goal

Confirm that “verification succeeded” proves exactly the object, context, role, ordering, and consumer required by the business logic.

## Loading Order

1. Read `${CLAUDE_PLUGIN_ROOT}/framework/verify-evidence.md` first.
2. Choose one or two Profiles based on the entry point, component, and anomaly; do not load every Profile in the group at once.
3. After forming a testable hypothesis, read the matching Reference for additional cases and variants.
4. When a chain crosses boundaries, load material from other groups according to the Profile’s “Combination Paths.”

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| Digital signatures; Merkle proofs; zero-knowledge proofs | `crypto-binding` | Cryptographic Semantic Binding |
| Challenge-response authentication; remote-management protocols; VPN/Wi-Fi | `offline-verifier` | Offline Verifiers |
| SAML; SOAP WS-Security; XMLDSig | `xml-signature` | XML Signature Consumption |

Profile paths are `${CLAUDE_PLUGIN_ROOT}/profiles/<name>.md`; Reference paths are `${CLAUDE_PLUGIN_ROOT}/references/<name>.md`.

## Workflow

1. Record the algorithm, key type, parameters, domain, version, audience, object type, and protocol role.
2. Separate the signed/proven object from the object ultimately consumed by business code.
3. Test replay, cross-context use, cross-role use, ordering/uniqueness, algorithm/key confusion, and post-verification reparsing.
4. For authentication protocols, determine whether an unauthenticated party receives stable material that supports offline verification of guesses.

## Do Not Stop Here

- Assuming business semantics are safe because the mathematical verification succeeds.
- Checking algorithm strength while ignoring object, domain, role, and lifecycle binding.
- Citing a protocol name instead of reproducing the issue; do not conclude without an actual consumption difference or an offline decision function.

## Output

For each round, record only: Profile used, target object, testing identity, hypothesis, baseline, variant, independent verification, evidence path, current status, and next step or combination path. Mark a finding `confirmed` only when it meets the evidence threshold in the unified framework.
