---
id: session-auth-state
group: identity
reference: ../references/auth-state.md
---

# Authentication State

**Use for:** login/MFA, device trust, step-up confirmation for sensitive actions, session elevation/demotion, and cross-device login.

**Misalignment to find:** Authentication steps, devices, sessions, privilege elevation, or step-up state are not bound to the same subject and session lifecycle.

## Baseline

- Every authentication factor and privilege state must be bound to the current subject, device, session, and target action.
- Look for inherited state, session switching, cross-endpoint reuse, downgrade paths, or stale authentication state.
- Focus on cases where a completed authentication step does not prove that the current session or action is authenticated.
- Record the session ID, subject, device, factor, assurance level, and target action.

## Validation Order

1. Record cookies, tokens, and assurance levels before and after every step.
2. Switch accounts, devices, entry points, sessions, and actions.
3. Test skipped steps, replay, downgrade endpoints, and concurrent state changes.
4. Verify through the final sensitive action and the identity of the session that performed it.

## Variant Axes

- Subject: account, device, browser, session, sub-session
- Assurance level: anonymous, logged in, MFA, step-up confirmation, administrator elevation
- Step: initiation, challenge, verification, consumption, downgrade, recovery
- Switching: cross-account, cross-device, cross-entry-point, concurrent, and stale sessions

## Combination Paths

- `tokens`: Token Lifecycle
- `oauth-sso`: OAuth/SSO
- `csrf`: Cross-Site Request Forgery
- `role-capability`: Role & Capability Authorization
- `workflow`: Business State Machines
