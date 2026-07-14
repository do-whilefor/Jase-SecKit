# Token Lifecycle · Reference

Load after selecting the `token-lifecycle` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### 7asecurity/pentest-report-litmuschaos · LIT-01-016 WP1: Account Takeover via Project Invitation
- Knowledge value: 9/10; authentication bypass / state confusion / business logic.
- Chain: The attacker obtains a normal session or controllable identity/object identifier → manipulates a binding, recovery, 2FA/OTP, or reset flow → the server associates an attacker-controlled factor with the victim account → the attacker logs in or performs a sensitive action.
- Bypass: The flow checks only that a verification code or object exists, but not its ownership, purpose, session, and current state, allowing cross-account or cross-step reuse.
- Defensive anchor: Require reauthentication for sensitive state changes; bind tokens to user, session, purpose, and a one-time nonce; enforce object-level authorization; require the old factor and delayed notification for 2FA rebinding.

### cure53/pentest-report nitrokey · NK-01-015 Admin Check can be bypassed by resetting Smart Card
- Knowledge value: 9/10; authentication bypass / state confusion / cross-component attack chain.
- Chain: The attacker obtains the device and resets/replaces the smart card or triggers a firmware-state transition → the device incorrectly rebuilds or clears authentication state → administrator checks or OTP lock state are lost → protected functions or secrets become accessible.
- Bypass: A replaceable component is not bound to device security state with an unforgeable, rollback-resistant relationship, so a physical state transition is misinterpreted as an authorized initialization.
- Defensive anchor: Store privilege state in protected monotonic storage; mutually authenticate cards and firmware and prevent rollback; require old credentials or controlled recovery for sensitive resets; test hot-plug, reset, and upgrade paths as a state machine.

## HackerOne Case Index

### 1817214 · Reset/verification/invitation token-lifecycle misbinding
- Knowledge value: 9/10; authentication bypass / state confusion / authorization bypass.
- Chain: `https://sorare.com/confirm_device?token=N04J3Zczv1GaFrniJisN1QgsisoJHQ` → reset/verification/invitation token-lifecycle misbinding → security controls and the final execution point disagree about subject, object, state, or input semantics → account takeover.
- Bypass: After token issuance, change the email, account, session, or privilege state, then reuse the stale token to complete an action that should have been revoked.
- Defensive anchor: Tokens must be single-use and short-lived, and bound to subject, target attribute, purpose, session/version; email change, password change, logout, revocation, and reinvitation must atomically revoke old tokens.

### 310946 · Reset/verification/invitation token-lifecycle misbinding
- Knowledge value: 8/10; authentication bypass / state confusion / authorization bypass.
- Chain: `https://hackerone.com/graphql` → reset/verification/invitation token-lifecycle misbinding, combined with missing operation-level GraphQL/WebSocket authorization → the corresponding trust boundary is crossed → the unauthorized access, state change, or availability impact described by the report.
- Bypass: Reuse a stale token after identity or state changes and combine it with missing GraphQL/WebSocket operation authorization.
- Defensive anchor: Use single-use, short-lived, fully bound tokens; revoke them atomically on state changes; add GraphQL/WebSocket authorization regressions that ensure the same subject, object, state, and normalized semantics are used at validation and execution.

### 772886 · Reset/verification/invitation token-lifecycle misbinding
- Knowledge value: 8/10; authentication bypass / state confusion / race condition.
- Chain: `/change-password/` → reset/verification/invitation token-lifecycle misbinding, combined with a TOCTOU/concurrent-state boundary failure → the corresponding trust boundary is crossed → access to or impact on another user’s data/state.
- Bypass: Reuse stale tokens after state changes and combine the flow with a concurrent non-atomic window.
- Defensive anchor: Use single-use, short-lived, fully bound tokens; revoke them atomically on relevant events; add TOCTOU/concurrency regressions at final consumption.
