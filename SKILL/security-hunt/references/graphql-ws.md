# GraphQL/WS Authorization · Reference

Load after selecting the `graphql-operation-authorization` Profile and forming a current-target hypothesis.

## Use Rule

- Use these sources to expand operation, resolver, subscription, and message-level hypotheses.
- Do not treat a successful handshake or authenticated connection as authorization for every later action.
- Verify final objects, fields, events, and side effects independently.

## Curated Sources

### OWASP GraphQL Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html
- Transferable test ideas:
  - Enumerate queries, mutations, fields, resolvers, aliases, batching, introspection, and subscriptions.
  - Vary object IDs, tenant context, fields, and operation names under different identities and roles.
  - Check authorization at the resolver and final object rather than relying on schema visibility or frontend controls.
- Defensive anchor:
  - Enforce object, field, and function authorization at each resolver or equivalent downstream boundary.
  - Bound query complexity and disable unnecessary development features in production.

### OWASP WebSocket Security Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html
- Transferable test ideas:
  - Separate handshake authentication from authorization for every message type, object, subscription, and tenant.
  - Test session expiry, logout, reconnect, replay, origin handling, and permission changes while the connection remains open.
- Defensive anchor:
  - Validate origin and authenticate the connection, then authorize every message against current server-side state.
