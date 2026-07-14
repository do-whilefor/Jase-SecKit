# GraphQL/WS Authorization · Reference

Load after selecting the `graphql-websocket-auth` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## HackerOne Case Index

### 241244 · Missing operation-level GraphQL/WebSocket authorization
- Knowledge value: 8/10; authorization bypass / framework-behavior exploitation / authentication bypass.
- Chain: `http://localhost:8153/go/remoting/api/admin/config.xml` → missing operation-level GraphQL/WebSocket authorization → security controls and the final execution point disagree about subject, object, state, or input semantics → access to internal services or cloud metadata.
- Bypass: Directly invoke GraphQL fields or mutations not exposed by the UI, or send messages over an established WebSocket that exceed the current identity’s permissions.
- Defensive anchor: Enforce server-side object- and field-level authorization in every resolver, field, mutation, subscription, and WebSocket message handler; use a unified policy layer and never rely on frontend hiding, connection-level authentication, or client-supplied tenant/user IDs.
