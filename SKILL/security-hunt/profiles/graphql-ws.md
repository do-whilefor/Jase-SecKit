---
id: graphql-websocket-auth
group: channels
reference: ../references/graphql-ws.md
---

# GraphQL/WS Authorization

**Use for:** GraphQL queries/mutations, field-level resolution, subscriptions, Socket.IO/WebSocket messages, and batched/aliased queries.

**Misalignment to find:** Connection establishment, route protection, or frontend hiding is mistaken for final authorization, while fields, resolvers, mutations, subscriptions, or message handlers lack object-, field-, or tenant-level checks.

## Baseline

- Authorization must be enforced at the final resolver/message handler and on the concrete object.
- Connection authentication, route protection, frontend hiding, or list filtering does not cover nested fields and actions.
- Focus on authenticated entry points whose final object or field is not authorized.
- Record the subject, tenant, resolver, object ID, field, and message type.

## Validation Order

1. Enumerate schema elements or message types as anonymous, low-privilege, cross-tenant, and high-privilege identities.
2. Substitute the object and tenant for every resolver, field, mutation, and subscription.
3. Test aliases, batching, fragments, subscription reconnects, and identity changes after connection establishment.
4. Compare returned fields and final state.

## Variant Axes

- Layer: connection, route, operation, field/resolver, object, field data
- Identity: anonymous, low privilege, high privilege, tenant, subscription session
- Operation: query, mutation, subscription, batch, alias, fragment
- Object ID, field selection, variables, message type, and reconnect behavior

## Combination Paths

- `browser-channel`: Cross-Origin Channels
- `auth-state`: Authentication State
- `workflow`: Business State Machines
