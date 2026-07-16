# Token Lifecycle · Reference

Load after selecting the `token-lifecycle` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### LIT-01-016 WP1: Account Takeover via Project Invitation

- Source: `7asecurity/pentest-report-litmuschaos`
- Reported focus: LIT-01-016 WP1: Account Takeover via Project Invitation
- Transferable test ideas:
  - The flow checks only that a verification code or object exists, but not its ownership, purpose, session, and current state, allowing cross-account or cross-step reuse.
- Defensive anchor:
  - Require reauthentication for sensitive state changes.
  - Bind tokens to user, session, purpose, and a one-time nonce.
  - Enforce object-level authorization.
  - Require the old factor and delayed notification for 2FA rebinding.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.

### NK-01-015 Admin Check can be bypassed by resetting Smart Card

- Source: `cure53/pentest-report nitrokey`
- Reported focus: NK-01-015 Admin Check can be bypassed by resetting Smart Card
- Transferable test ideas:
  - A replaceable component is not bound to device security state with an unforgeable, rollback-resistant
    relationship, so a physical state transition is misinterpreted as an authorized initialization.
- Defensive anchor:
  - Store privilege state in protected monotonic storage.
  - Mutually authenticate cards and firmware and prevent rollback.
  - Require old credentials or controlled recovery for sensitive resets.
  - Test hot-plug, reset, and upgrade paths as a state machine.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
