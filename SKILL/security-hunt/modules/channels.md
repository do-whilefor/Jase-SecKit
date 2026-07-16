# Channels & APIs

## Goal

Decompose browser and long-lived channels into authorization for each request, message, operation, field, object, and
tenant, then check whether ambient credentials or shared state are reused across subjects.

## Primary Boundary

Use this module as primary when authorization or isolation fails across browser-triggered requests, messages, operations, connections, caches, or shared protocol state.

Choose the narrower Profile when possible:

- Use `cache-variant` when an attacker-created response is reused because the cache key omits a varying dimension.
- Use `shared-state` when mutable protocol state is polluted and affects later independent requests, sessions, or consumers.

## Loading Order

1. Read `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md` first.
2. Load the Profiles needed for the concrete hypothesis; keep plausible adjacent and combination paths queued, and add
   them whenever evidence, gaps, or downstream consumers require it.
3. Establish a baseline before reading matching References for additional variants. Progressive loading limits context use, not testing breadth or depth.

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| window.postMessage; cookie-authenticated WebSockets; iframe embedding | `browser-channel` | Cross-Origin Channels |
| Cookie-authenticated state-changing HTTP actions; browser-forged requests | `csrf` | Cross-Site Request Forgery |
| CDNs/reverse proxies; page caches; API caches | `cache-variant` | Cache Variants |
| GraphQL Query/Mutation; field-level resolvers; subscriptions | `graphql-ws` | GraphQL/WS Authorization |
| DNS caches; cookie/session stores; proxy caches | `shared-state` | Shared Protocol State |

Profile paths are `${CLAUDE_SKILL_DIR}/profiles/<name>.md`; Reference paths are `${CLAUDE_SKILL_DIR}/references/<name>.md`.

## Workflow

1. Enumerate state-changing browser endpoints, message listeners, handshakes, GraphQL operations, resolvers, subscriptions, and cache or shared-state write points.
2. Independently vary origin, request form, credential behavior, connection identity, message type, object ID, field, tenant, and ordering.
3. Trigger state with an attacker origin or session, then verify CSRF, cache, subscription, or shared-state effects from an independent view.
4. Use final state changes, returned data, sensitive actions, cross-user reuse, or contamination of later requests as evidence.

## Do Not Stop Here

- Treating ambient cookies, Origin, or connection authentication as proof of user intent or authorization for every request, message, and object.
- Checking only frontend hiding and route guards without reaching the resolver, handler, or downstream consumer.
- Validating cache poisoning in the same session, which cannot prove cross-subject impact.

## Output

Record each round with the complete status, blackboard, evidence, impact-validation, severity-gate, blind-spot, and
closure rules in `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md`; do not replace them with a reduced local schema.
