# Identity & Authorization

## Goal

Check that authentication material, object access, roles, capabilities, and tenant context remain bound to the correct subject, session, account, action, and lifecycle.

## Primary Boundary

Use this module as primary when the failure concerns who a subject is, which object or tenant an action belongs to,
what role or capability authorizes it, or when an authentication artifact should expire or be invalidated.

Choose the narrower module when the decisive boundary is elsewhere:

- For SAML, use `crypto/xml-signature` when the signed node and the node consumed by business logic differ.
- For one-time artifacts, use `state/race` when the failure is atomicity, concurrent consumption, or count enforcement rather than identity binding.

## Loading Order

1. Read `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md` first.
2. Load the Profiles needed for the concrete hypothesis; keep plausible adjacent and combination paths queued, and add
   them whenever evidence, gaps, or downstream consumers require it.
3. Establish a baseline before reading matching References for additional variants. Progressive loading limits context use, not testing breadth or depth.

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| OAuth/OIDC login; SAML SSO; social-account binding | `oauth-sso` | OAuth/SSO |
| Password reset; email/phone verification; organization invitations | `tokens` | Token Lifecycle |
| Login/MFA; device trust; step-up confirmation for sensitive actions | `auth-state` | Authentication State |
| Multi-subdomain organizations; broad-domain cookies; SSO callbacks | `subdomain-trust` | Subdomain Trust |
| Direct object IDs; nested resources; ownership and sharing | `object-authorization` | Object Authorization |
| Administrative routes; hidden functions; role or capability checks | `role-capability` | Role & Capability Authorization |
| Organizations; workspaces; tenant selectors; shared infrastructure | `tenant-isolation` | Tenant Isolation |

Profile paths are `${CLAUDE_SKILL_DIR}/profiles/<name>.md`; Reference paths are `${CLAUDE_SKILL_DIR}/references/<name>.md`.

## Workflow

1. Record identities, sessions, roles, tenant context, object relationships, tokens, devices, assurance levels, and callback parameters.
2. Test across accounts, roles, tenants, sessions, devices, clients, IdPs, objects, actions, and replay order.
3. For every sensitive artifact or action, check ownership, function permission, tenant membership, issuance, consumption, revocation, rebinding, concurrency, and invalidation.
4. Confirm impact through the final object, effective permission, tenant boundary, logged-in account, token audience, or sensitive action.

## Do Not Stop Here

- Checking only whether a token is random while ignoring ownership, role, tenant, purpose, and invalidation dimensions.
- Treating authentication as authorization for every object, function, property, or tenant.
- Treating a successful callback as proof that the authenticated subject and target account are correct.
- Testing only the primary Web entry point while ignoring mobile, legacy, direct API, background, and account-binding paths.

## Output

Record each round with the complete status, blackboard, evidence, impact-validation, severity-gate, blind-spot, and
closure rules in `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md`; do not replace them with a reduced local schema.
