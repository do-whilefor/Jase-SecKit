# Object Authorization · Reference

Load after selecting the `object-authorization` Profile and forming a current-target hypothesis.

## Use Rule

- Use these sources to expand object-level authorization hypotheses, not to assign impact or severity.
- Reproduce every object, action, identity, and tenant boundary on the current target.
- Verify the final object through an independent identity or server-side read.

## Curated Sources

### OWASP API1:2023 · Broken Object Level Authorization

- Source URL: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- Transferable test ideas:
  - Identify every client-controlled object identifier regardless of whether it is sequential, opaque, or embedded in a nested structure.
  - Replay the same operation across owner, non-owner, and cross-tenant objects.
  - Test each action separately because read, update, delete, share, export, and attachment access may use different checks.
- Defensive anchor:
  - Authorize the current subject for the exact action on the final object at the server-side data-access boundary.
  - Derive ownership and tenant relationships from trusted server-side state.
