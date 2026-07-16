# Cross-Site Request Forgery · Reference

Load after selecting the `cross-site-request-forgery` Profile and forming a current-target hypothesis.

## Use Rule

- Use these sources to expand browser-request hypotheses, not to infer current-target exploitability.
- Test the actual browser behavior, cookie policy, request form, and final state change.
- Confirm the affected identity and action independently.

## Curated Sources

### OWASP Cross-Site Request Forgery Prevention Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- Transferable test ideas:
  - Enumerate endpoints that rely on ambient browser credentials and accept browser-reachable request forms.
  - Test token absence, token/session mismatch, Origin/Referer handling, SameSite behavior, alternate content types, and login or account-linking flows.
  - Verify whether the server can distinguish an intended user action from a forged cross-site request.
- Defensive anchor:
  - Use synchronizer or signed double-submit tokens bound to the session where appropriate.
  - Validate request origin and use SameSite cookies as defense in depth.
  - Require reauthentication or explicit confirmation for high-impact actions.
