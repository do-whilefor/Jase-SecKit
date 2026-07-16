---
id: cross-origin-message-channel
group: channels
reference: ../references/browser-channel.md
---

# Cross-Origin Channels

**Use for:** window.postMessage, cookie-authenticated WebSockets, iframe embedding, browser-extension messages, and desktop WebView bridges.

**Misalignment to find:** postMessage, WebSocket, iframe, extension messaging, or cross-window bridges perform only
connection-level authentication or incomplete source validation, allowing message-level capabilities to be invoked
from an unintended source.

## Baseline

- Establishing a connection does not authorize every message.
- Look for incorrect origin/source matching, automatic cookie authentication, wildcard targets, unconstrained message types, or overly broad capabilities.
- Focus on trusted sources whose message subject, object, and capability are not bound together.
- Record the sending window, origin, source, connection identity, message schema, and final action.

## Validation Order

1. Enumerate every message listener and handshake endpoint.
2. Send messages from sibling subdomains, popups, iframes, navigated stale windows, and third-party sites.
3. Vary origin, source, message type, object ID, and ordering.
4. Prove impact through a privileged action or returned data.

## Variant Axes

- Sender: origin, source, window lifecycle, extension/page identity
- Channel: postMessage, WebSocket, iframe, WebView, extension bridge
- Message: type, schema, object ID, ordering, replay
- Capability: data read, navigation, DOM access, account action, privileged API

## Combination Paths

- `subdomain-trust`: Subdomain Trust
- `graphql-ws`: GraphQL/WS Authorization
- `browser-parse`: Browser Parsing
