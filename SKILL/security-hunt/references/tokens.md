# Token Lifecycle · Reference


Load on demand after selecting the `token-lifecycle` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### 7asecurity/pentest-report-litmuschaos · LIT-01-016 WP1: Account Takeover via Project Invitation
- Value: 9/10; authentication bypass / state confusion / business logic.
- Chain: The attacker obtains a normal session or controllable identity/object identifier → manipulates a binding, recovery, 2FA/OTP, or reset flow → the server associates an attacker-controlled factor with the victim account → the attacker logs in or performs a sensitive action.
- Bypass: The flow checks only that a verification code or object exists, but not its ownership, purpose, session, and current state, allowing cross-account or cross-step reuse.
- Defensive anchor: Require reauthentication for sensitive state changes; bind tokens to user, session, purpose, and a one-time nonce; enforce object-level authorization; require the old factor and delayed notification for 2FA rebinding.

### cure53/pentest-report nitrokey · NK-01-015 Admin Check can be bypassed by resetting Smart Card
- Value: 9/10; authentication bypass / state confusion / cross-component attack chain.
- Chain: The attacker obtains the device and resets/replaces the smart card or triggers a firmware-state transition → the device incorrectly rebuilds or clears authentication state → administrator checks or OTP lock state are lost → protected functions or secrets become accessible.
- Bypass: A replaceable component is not bound to device security state with an unforgeable, rollback-resistant relationship, so a physical state transition is misinterpreted as an authorized initialization.
- Defensive anchor: Store privilege state in protected monotonic storage; mutually authenticate cards and firmware and prevent rollback; require old credentials or controlled recovery for sensitive resets; test hot-plug, reset, and upgrade paths as a state machine.


## HackerOne Case Index


### 1817214 · Reset/verification/invitation token-lifecycle misbinding
- Value: 9/10; authentication bypass / state confusion / authorization bypass.
- Chain: `https://sorare.com/confirm_device?token=N04J3Zczv1GaFrniJisN1QgsisoJHQ` → reset/verification/invitation token-lifecycle misbinding → security controls and the final execution point disagree about subject, object, state, or input semantics → account takeover.
- Bypass: After token issuance, change the email, account, session, or privilege state, then reuse the stale token to complete an action that should have been revoked.
- Defensive anchor: Tokens must be single-use and short-lived, and bound to subject, target attribute, purpose, session/version; email change, password change, logout, revocation, and reinvitation must atomically revoke old tokens.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 310946 · Reset/verification/invitation token-lifecycle misbinding
- Value: 8/10; authentication bypass / state confusion / authorization bypass.
- Chain: `https://hackerone.com/graphql` → reset/verification/invitation token-lifecycle misbinding, combined with missing operation-level GraphQL/WebSocket authorization → the corresponding trust boundary is crossed → the unauthorized access, state change, or availability impact described by the report.
- Bypass: Reuse a stale token after identity or state changes and combine it with missing GraphQL/WebSocket operation authorization.
- Defensive anchor: Use single-use, short-lived, fully bound tokens; revoke them atomically on state changes; add GraphQL/WebSocket authorization regressions that ensure the same subject, object, state, and normalized semantics are used at validation and execution.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 772886 · Reset/verification/invitation token-lifecycle misbinding
- Value: 8/10; authentication bypass / state confusion / race condition.
- Chain: `/change-password/` → reset/verification/invitation token-lifecycle misbinding, combined with a TOCTOU/concurrent-state boundary failure → the corresponding trust boundary is crossed → access to or impact on another user’s data/state.
- Bypass: Reuse stale tokens after state changes and combine the flow with a concurrent non-atomic window.
- Defensive anchor: Use single-use, short-lived, fully bound tokens; revoke them atomically on relevant events; add TOCTOU/concurrency regressions at final consumption.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 4.
- HackerOne reports: 18.
- Full report IDs:
  - 7asecurity/pentest-report-litmuschaos
  - 7asecurity/pentest-report-securedrop
  - cure53/pentest-report nitrokey
  - mnemonic/watchout-rapport-october-2017
- HackerOne report IDs:
  - 67660, 331691, 685007, 15166, 290930, 92251, 244642, 1245762, 283550, 220185, 66151, 1615790, 263672, 310946, 1401891, 244612, 772886, 1817214

