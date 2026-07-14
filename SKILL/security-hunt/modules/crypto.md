# Cryptographic Semantics

## Goal

Confirm that “verification succeeded” proves exactly the object, context, role, ordering, and consumer required by the business logic.

## Primary Boundary

Use this module as primary when mathematical verification succeeds but proves the wrong object, context, role, ordering, or consumer. For SAML, use `identity/oauth-sso` as primary when the failure is state, callback, session, IdP, or account binding; use `xml-signature` when the verified XML node differs from the node later consumed.

## Compatibility

Effective validation may require the implementation, protocol traces, verifier behavior, or a reproducible local environment. Use `blocked` only under the framework rule after viable observation and reproduction alternatives have been tried.

## Loading Order

1. Read `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md` first.
2. Load the Profiles needed for the concrete hypothesis; keep plausible adjacent and combination paths queued, and add them whenever evidence, gaps, or downstream consumers require it.
3. Establish a baseline before reading matching References for additional variants. Progressive loading limits context use, not testing breadth or depth.

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| Digital signatures; Merkle proofs; zero-knowledge proofs | `crypto-binding` | Cryptographic Semantic Binding |
| Challenge-response authentication; remote-management protocols; VPN/Wi-Fi | `offline-verifier` | Offline Verifiers |
| SAML; SOAP WS-Security; XMLDSig | `xml-signature` | XML Signature Consumption |

Profile paths are `${CLAUDE_SKILL_DIR}/profiles/<name>.md`; Reference paths are `${CLAUDE_SKILL_DIR}/references/<name>.md`.

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

Record each round with the complete status, blackboard, evidence, impact-validation, severity-gate, blind-spot, and closure rules in `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md`; do not replace them with a reduced local schema.
