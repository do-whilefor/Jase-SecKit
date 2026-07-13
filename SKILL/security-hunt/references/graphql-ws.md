# GraphQL/WS Authorization · Reference


Load on demand after selecting the `graphql-websocket-auth` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## HackerOne Case Index


### 241244 · Missing operation-level GraphQL/WebSocket authorization
- Value: 8/10; authorization bypass / framework-behavior exploitation / authentication bypass.
- Chain: `http://localhost:8153/go/remoting/api/admin/config.xml` → missing operation-level GraphQL/WebSocket authorization → security controls and the final execution point disagree about subject, object, state, or input semantics → access to internal services or cloud metadata.
- Bypass: Directly invoke GraphQL fields or mutations not exposed by the UI, or send messages over an established WebSocket that exceed the current identity’s permissions.
- Defensive anchor: Enforce server-side object- and field-level authorization in every resolver, field, mutation, subscription, and WebSocket message handler; use a unified policy layer and never rely on frontend hiding, connection-level authentication, or client-supplied tenant/user IDs.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 0.
- HackerOne reports: 8.
- HackerOne report IDs:
  - 1274695, 241244, 447488, 1574078, 1161141, 1392032, 2382120, 717729

