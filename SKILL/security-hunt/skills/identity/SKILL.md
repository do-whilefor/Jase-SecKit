---
name: Identity State
description: Subject and lifecycle mismatches in login, token, session, subdomain, and account-binding flows. Use for authorized testing of OAuth/SSO, token lifecycles, authentication state, and subdomain trust.
user-invocable: false
allowed-tools: Read Grep Glob Bash
---

# Identity State

## Goal

Check that authentication material remains bound to the initiating subject, current session, target account, client, action, and one lifecycle.

## Loading Order

1. Read `${CLAUDE_PLUGIN_ROOT}/framework/verify-evidence.md` first.
2. Choose one or two Profiles based on the entry point, component, and anomaly; do not load every Profile in the group at once.
3. After forming a testable hypothesis, read the matching Reference for additional cases and variants.
4. When a chain crosses boundaries, load material from other groups according to the Profile’s “Combination Paths.”

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| OAuth/OIDC login; SAML SSO; social-account binding | `oauth-sso` | OAuth/SSO |
| Password reset; email/phone verification; organization invitations | `tokens` | Token Lifecycle |
| Login/MFA; device trust; step-up confirmation for sensitive actions | `auth-state` | Authentication State |
| Multi-subdomain organizations; broad-domain cookies; SSO callbacks | `subdomain-trust` | Subdomain Trust |

Profile paths are `${CLAUDE_PLUGIN_ROOT}/profiles/<name>.md`; Reference paths are `${CLAUDE_PLUGIN_ROOT}/references/<name>.md`.

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

For each round, record only: Profile used, target object, testing identity, hypothesis, baseline, variant, independent verification, evidence path, current status, and next step or combination path. Mark a finding `confirmed` only when it meets the evidence threshold in the unified framework.
