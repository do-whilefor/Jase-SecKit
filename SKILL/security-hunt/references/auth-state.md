# Authentication State · Reference


Load on demand after selecting the `session-auth-state` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### doyensec/Doyensec Basecamp HEY Platform Q32020 SAS · 5 2FA Bypass Via Mobile Endpoints Miscon guration Medium Open
- Value: 9/10; authentication bypass / state confusion / business logic.
- Chain: The attacker obtains a normal session or controllable identity/object identifier → manipulates a binding, recovery, 2FA/OTP, or reset flow → the server associates an attacker-controlled factor with the victim account → the attacker logs in or performs a sensitive action.
- Bypass: The flow checks only that a verification code or object exists, but not its ownership, purpose, session, and current state, allowing cross-account or cross-step reuse.
- Defensive anchor: Require reauthentication for sensitive state changes; bind tokens to user, session, purpose, and a one-time nonce; enforce object-level authorization; require the old factor and delayed notification for 2FA rebinding.


## Source Coverage

- Full reports: 1.
- HackerOne reports: 0.
- Full report IDs:
  - doyensec/Doyensec Basecamp HEY Platform Q32020 SAS

