---
id: token-lifecycle
group: identity
reference: ../references/tokens.md
---

# Token Lifecycle

**Use for:** password reset, email/phone verification, organization invitations, 2FA enrollment/recovery, and account rebinding.

**Misalignment to find:** Sensitive-flow tokens are not bound to the current session, target account, action type,
version, use count, and invalidation events, enabling replay, rebinding, cross-flow use, or concurrent takeover.

## Baseline

- A token is a one-time authorization for one subject to perform one action on one object.
- Look for missing object binding, mixed actions, stale-token survival, concurrent use, session switching, or alternate entry points.
- Focus on formally valid tokens whose authorization context has changed.
- Record the token, session, target account, action, version, use count, and invalidation events.

## Validation Order

1. Obtain tokens for multiple accounts, devices, and points in time.
2. Swap subject, object, action, session, and entry point.
3. Test replay, concurrency, stale tokens after changes, and invitation/registration mixing.
4. Verify final account control and binding state.

## Variant Axes

- Token type: reset, verification, invitation, binding, recovery, API/refresh token
- Binding dimension: session, account, target address, action, tenant, version
- Invalidation event: use, password change, rebinding, revocation, logout, privilege change
- Concurrency, replay, cross-endpoint use, and old token versions

## Combination Paths

- `oauth-sso`: OAuth/SSO
- `auth-state`: Authentication State
- `workflow`: Business State Machines
