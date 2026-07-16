# Cryptographic Semantics

## Goal

Confirm that “verification succeeded” proves exactly the object, context, role, ordering, and consumer required by the business logic.

## Route Here When

Use this module as primary when mathematical verification succeeds but proves the wrong object, context, role,
ordering, or consumer. For SAML, use `identity/oauth-sso` as primary when the failure is state, callback, session,
IdP, or account binding; use `xml-signature` when the verified XML node differs from the node later consumed.

## Compatibility

Effective validation may require the implementation, protocol traces, verifier behavior, or a reproducible local
environment. Return `NEED_INPUT` only after viable observation and reproduction
alternatives have been tried and the missing capability is recorded.

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| Digital signatures; Merkle proofs; zero-knowledge proofs | `crypto-binding` | Cryptographic Semantic Binding |
| Challenge-response authentication; remote-management protocols; VPN/Wi-Fi | `offline-verifier` | Offline Verifiers |
| SAML; SOAP WS-Security; XMLDSig | `xml-signature` | XML Signature Consumption |

## Workflow

1. Record the algorithm, key type, parameters, domain, version, audience, object type, and protocol role.
2. Separate the signed/proven object from the object ultimately consumed by business code.
3. Test replay, cross-context use, cross-role use, ordering/uniqueness, algorithm/key confusion, and post-verification reparsing.
4. For authentication protocols, determine whether an unauthenticated party receives stable material that supports offline verification of guesses.

## Do Not Stop Here

- Assuming business semantics are safe because the mathematical verification succeeds.
- Checking algorithm strength while ignoring object, domain, role, and lifecycle binding.
- Citing a protocol name instead of reproducing the issue; do not conclude without an actual consumption difference or an offline decision function.
