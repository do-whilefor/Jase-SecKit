# Authentication State · Reference

Load after selecting the `session-auth-state` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### doyensec/Doyensec Basecamp HEY Platform Q32020 SAS · 5 2FA Bypass Via Mobile Endpoints Miscon guration Medium Open
- Knowledge value: 9/10; authentication bypass / state confusion / business logic.
- Chain: The attacker obtains a normal session or controllable identity/object identifier → manipulates a binding, recovery, 2FA/OTP, or reset flow → the server associates an attacker-controlled factor with the victim account → the attacker logs in or performs a sensitive action.
- Bypass: The flow checks only that a verification code or object exists, but not its ownership, purpose, session, and current state, allowing cross-account or cross-step reuse.
- Defensive anchor: Require reauthentication for sensitive state changes; bind tokens to user, session, purpose, and a one-time nonce; enforce object-level authorization; require the old factor and delayed notification for 2FA rebinding.
