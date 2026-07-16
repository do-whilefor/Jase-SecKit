---
id: tenant-isolation
group: identity
reference: ../references/tenant-isolation.md
---

# Tenant Isolation

**Use for:** multi-tenant SaaS, organizations, workspaces, projects, teams, customer partitions, tenant-scoped administration, and shared infrastructure.

**Misalignment to find:** Tenant context is accepted from the client, inferred inconsistently, omitted from a
query/cache/job, or lost between services, allowing data or capabilities to cross tenant boundaries.

## Baseline

- Tenant isolation must be enforced at every data, authorization, cache, queue, storage, and background-processing boundary.
- A valid object ID or role in tenant A does not authorize the same action in tenant B.
- Do not trust tenant IDs, organization headers, subdomains, claims, or routing metadata without server-side membership validation.
- Record the authenticated subject, active tenant, membership, role, object tenant, routing context, and final storage or action.

## Validation Order

1. Establish equivalent identities and objects in at least two tenants when available.
2. Change only tenant selectors, organization IDs, subdomains, headers, claims, parent IDs, or object references.
3. Test direct APIs, search, exports, files, caches, background jobs, invitations, and administrative functions.
4. Verify cross-tenant reads or state changes from both tenant contexts and the final data store or object view.

## Variant Axes

- Tenant context: subdomain, path, header, token claim, session selection, body field, object relationship
- Membership: none, invited, pending, active, removed, suspended, multi-tenant member
- Role: member, manager, tenant admin, global operator, service account
- Shared component: cache, queue, search index, object storage, export, notification, analytics, background job

## Combination Paths

- `object-authorization`: Object Authorization
- `role-capability`: Role & Capability Authorization
- `cache-variant`: Cache Variants
- `shared-state`: Shared Protocol State
- `subdomain-trust`: Subdomain Trust
