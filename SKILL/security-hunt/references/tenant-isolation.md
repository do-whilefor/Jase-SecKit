# Tenant Isolation · Reference

Load after selecting the `tenant-isolation` Profile and forming a current-target hypothesis.

## Use Rule

- Use these sources to expand tenant-boundary hypotheses, not to infer current-target impact or scope.
- Verify tenant context at every service and storage boundary reached by the tested action.
- Confirm any cross-tenant effect from independent tenant identities.

## Curated Sources

### OWASP Multi-Tenant Security Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html
- Transferable test ideas:
  - Trace tenant context through authentication, authorization, queries, caches, queues, storage, logs, and background jobs.
  - Test missing, conflicting, stale, and attacker-controlled tenant selectors.
  - Compare direct object access with search, export, file, notification, analytics, and administrative paths.
- Defensive anchor:
  - Resolve tenant membership from trusted server-side identity context.
  - Include tenant constraints in every data-access and shared-component boundary.
