# Role & Capability Authorization · Reference

Load after selecting the `role-capability-authorization` Profile and forming a current-target hypothesis.

## Use Rule

- Use these sources to expand function-level authorization hypotheses, not to infer current-target impact.
- Build the current target's role-to-capability matrix from observed behavior.
- Verify every privileged side effect independently.

## Curated Sources

### OWASP API5:2023 · Broken Function Level Authorization

- Source URL: https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/
- Transferable test ideas:
  - Compare user hierarchies, roles, groups, delegated permissions, and administrative functions.
  - Test alternate methods, routes, API versions, mobile endpoints, GraphQL operations, and direct service paths.
  - Treat hidden UI controls as discovery hints only; authorization must be enforced at the handler and downstream capability.
- Defensive anchor:
  - Deny by default and centralize function-level policy.
  - Evaluate the caller's effective capability for every sensitive operation.
