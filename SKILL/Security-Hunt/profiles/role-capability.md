---
id: role-capability-authorization
group: identity
reference: ../references/role-capability.md
---

# Role & Capability Authorization

**Use for:** BFLA, horizontal and vertical privilege boundaries, administrative APIs, hidden actions, role management, approval functions, and service-to-service capabilities.

**Misalignment to find:** A route, method, operation, field, or downstream action is reachable by a subject whose role or effective capability does not permit it.

## Baseline

- UI visibility and route discovery are not authorization controls.
- Every sensitive function must enforce authorization at the final handler and downstream capability boundary.
- Role names alone may be insufficient when permissions depend on tenant, object, state, delegation, or temporary elevation.
- Record the caller role, effective permissions, endpoint or operation, target object, and final action.

## Validation Order

1. Build a role-to-capability matrix from observed UI, APIs, code, errors, and successful baseline requests.
2. Replay privileged actions with lower roles, alternate methods, legacy routes, mobile APIs, GraphQL operations, and direct downstream endpoints.
3. Vary action fields, operation names, method overrides, and partial object updates.
4. Verify the resulting permission, configuration, approval, role, or privileged side effect independently.

## Variant Axes

- Subject: anonymous, normal user, manager, tenant admin, global admin, service identity
- Function: hidden route, alternate method, batch action, import/export, approval, role assignment, configuration
- Capability source: static role, scoped permission, delegated grant, feature flag, temporary elevation, service token
- Entry point: Web, mobile, legacy API, GraphQL, background job, direct service, callback

## Combination Paths

- `object-authorization`: Object Authorization
- `tenant-isolation`: Tenant Isolation
- `auth-state`: Authentication State
- `workflow`: Business State Machines
