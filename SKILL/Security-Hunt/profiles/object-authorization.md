---
id: object-authorization
group: identity
reference: ../references/object-authorization.md
---

# Object Authorization

**Use for:** IDOR/BOLA, direct object references, nested resources, object ownership, sharing, exports, attachments, and object-level read/write/delete actions.

**Misalignment to find:** The server accepts an object identifier or relationship supplied by the client without
proving that the current subject may perform the requested action on that exact object.

## Baseline

- Authentication identifies the caller; it does not authorize access to every object.
- Authorization must be evaluated for the final object, action, tenant, lifecycle state, and parent-child relationship.
- Do not assume UUIDs, opaque IDs, frontend filtering, or indirect lookup provide authorization.
- Record the subject, role, tenant, object ID, owner, parent, action, and final server-side result.

## Validation Order

1. Create or identify equivalent objects owned by account A, account B, and another tenant when available.
2. Replay the same action while changing only the object identifier or relationship field.
3. Test read, update, delete, download, share, export, attachment, and nested-resource endpoints independently.
4. Verify the final object state with the owner, another identity, or a clean server-side read.

## Variant Axes

- Subject: anonymous, owner, collaborator, unrelated user, privileged user, service account
- Object: own/other, parent/child, public/private, active/deleted, current/old version, boundary ID
- Identifier source: path, query, body, header, cookie, GraphQL variable, batch item, indirect reference
- Action: list, read, create under parent, update, delete, restore, download, share, approve, export

## Combination Paths

- `tenant-isolation`: Tenant Isolation
- `role-capability`: Role & Capability Authorization
- `workflow`: Business State Machines
- `params`: Parameter Parsing
