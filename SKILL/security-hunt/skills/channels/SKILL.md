---
name: Channels & APIs
description: Operation-level authorization and state isolation across windows, long-lived connections, caches, GraphQL, and shared protocol state. Use for authorized testing of cross-origin channels, cache variants, GraphQL/WS authorization, and shared protocol state.
user-invocable: false
allowed-tools: Read Grep Glob Bash
---

# Channels & APIs

## Goal

Decompose “the connection is established” into authorization for each message, operation, field, object, and tenant, then check whether shared state is reused across subjects.

## Loading Order

1. Read `${CLAUDE_PLUGIN_ROOT}/framework/verify-evidence.md` first.
2. Choose one or two Profiles based on the entry point, component, and anomaly; do not load every Profile in the group at once.
3. After forming a testable hypothesis, read the matching Reference for additional cases and variants.
4. When a chain crosses boundaries, load material from other groups according to the Profile’s “Combination Paths.”

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| window.postMessage; cookie-authenticated WebSockets; iframe embedding | `browser-channel` | Cross-Origin Channels |
| CDNs/reverse proxies; page caches; API caches | `cache-variant` | Cache Variants |
| GraphQL Query/Mutation; field-level resolvers; subscriptions | `graphql-ws` | GraphQL/WS Authorization |
| DNS caches; cookie/session stores; proxy caches | `shared-state` | Shared Protocol State |

Profile paths are `${CLAUDE_PLUGIN_ROOT}/profiles/<name>.md`; Reference paths are `${CLAUDE_PLUGIN_ROOT}/references/<name>.md`.

## Workflow

1. Enumerate message listeners, handshake endpoints, GraphQL operations, resolvers, subscriptions, and cache/state write points.
2. Independently vary origin, connection identity, message type, object ID, field, tenant, and ordering.
3. Write or trigger state with an attacker session, then verify cache, subscription, or shared-state effects from an independent session.
4. Use returned data, sensitive actions, cross-user reuse, or contamination of later requests as final evidence.

## Do Not Stop Here

- Treating Origin, cookies, or connection authentication as authorization for every message and object.
- Checking only frontend hiding and route guards without reaching the resolver, handler, or downstream consumer.
- Validating cache poisoning in the same session, which cannot prove cross-subject impact.

## Output

For each round, record only: Profile used, target object, testing identity, hypothesis, baseline, variant, independent verification, evidence path, current status, and next step or combination path. Mark a finding `confirmed` only when it meets the evidence threshold in the unified framework.
