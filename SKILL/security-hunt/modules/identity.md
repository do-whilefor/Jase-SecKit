# Identity State

## Goal

Check that authentication material remains bound to the initiating subject, current session, target account, client, action, and one lifecycle.

## Primary Boundary

Use this module as primary when the failure concerns who an artifact belongs to, what action or account it authorizes, or when it should expire or be invalidated. For SAML, use `crypto/xml-signature` as primary when the signed node and the node consumed by business logic differ. For one-time artifacts, use `state/race` as primary when the failure is atomicity, concurrent consumption, or count enforcement rather than identity binding.

## Loading Order

1. Read `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md` first.
2. Load the Profiles needed for the concrete hypothesis; keep plausible adjacent and combination paths queued, and add them whenever evidence, gaps, or downstream consumers require it.
3. Establish a baseline before reading matching References for additional variants. Progressive loading limits context use, not testing breadth or depth.

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| OAuth/OIDC login; SAML SSO; social-account binding | `oauth-sso` | OAuth/SSO |
| Password reset; email/phone verification; organization invitations | `tokens` | Token Lifecycle |
| Login/MFA; device trust; step-up confirmation for sensitive actions | `auth-state` | Authentication State |
| Multi-subdomain organizations; broad-domain cookies; SSO callbacks | `subdomain-trust` | Subdomain Trust |

Profile paths are `${CLAUDE_SKILL_DIR}/profiles/<name>.md`; Reference paths are `${CLAUDE_SKILL_DIR}/references/<name>.md`.

## Workflow

1. Record cookies, tokens, accounts, devices, assurance levels, and callback parameters before and after every step.
2. Test across accounts, sessions, devices, clients, IdPs, flows, and replay order.
3. For every sensitive artifact, check issuance, consumption, revocation, rebinding, concurrency, and invalidation events.
4. Confirm impact through the final logged-in account, binding relationship, token audience, or sensitive action.

## Do Not Stop Here

- Checking only whether a token is random while ignoring binding dimensions and invalidation events.
- Treating a successful callback as proof that the authenticated subject is correct.
- Testing only the primary Web entry point while ignoring mobile, legacy endpoints, deep links, and account-binding flows.

## Output

Record each round with the complete status, blackboard, evidence, impact-validation, severity-gate, blind-spot, and closure rules in `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md`; do not replace them with a reduced local schema.
