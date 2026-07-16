---
id: oauth-sso-lifecycle
group: identity
reference: ../references/oauth-sso.md
---

# OAuth/SSO

**Use for:** OAuth/OIDC login, SAML SSO, social-account binding, multiple identity providers, and mobile/desktop authorization.

**Misalignment to find:** Authorization codes, tokens, state, redirect_uri, identity providers, callback sessions, or
external accounts are not strongly bound to the initiating subject, client, and single flow.

## Baseline

- Every credential must be bound to the initiating session, client, callback target, identity provider, and one-time state.
- Look for reusable authorization codes, weak state, callback drift, IdP confusion, account-binding mismatch, or shared context in an embedded user agent.
- Focus on protocol material that is valid but belongs to a different flow or subject.
- Record the initiation request, browser session, state/nonce, code, redirect_uri, and final account.

## Validation Order

1. Record every identifier and cookie before and after authorization.
2. Substitute client, session, IdP, callback, account, and temporal order.
3. Test code/link replay, concurrent redemption, cross-endpoint redemption, and mixing of login and binding flows.
4. Prove impact through the final logged-in account, token audience, and binding relationship.

## Variant Axes

- Subject: browser session, client, IdP, external account, final local account
- Material: state, nonce, code, token, RelayState, SAMLResponse
- Callback: redirect_uri, deep link, cross-domain relay, mobile/desktop handler
- Lifecycle: one-time use, concurrent redemption, replay, rebinding, cross-flow consumption

## Combination Paths

- `tokens`: Token Lifecycle
- `auth-state`: Authentication State
- `subdomain-trust`: Subdomain Trust
- `browser-channel`: Cross-Origin Channels
- `proxy-origin`: Proxies & Origins
- `xml-signature`: XML Signature Consumption
