# Authentication State · Reference

Load after selecting the `session-auth-state` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### 5 2FA Bypass Via Mobile Endpoints Misconfiguration

- Source: `doyensec/Doyensec Basecamp HEY Platform Q32020 SAS`
- Source topic: 5 2FA Bypass Via Mobile Endpoints Misconfiguration
- Transferable test ideas:
  - The flow checks only that a verification code or object exists, but not its ownership, purpose, session, and current state, allowing cross-account or cross-step reuse.
- Defensive anchor:
  - Require reauthentication for sensitive state changes.
  - Bind tokens to user, session, purpose, and a one-time nonce.
  - Enforce object-level authorization.
  - Require the old factor and delayed notification for 2FA rebinding.

## Verified HackerOne Index

### HackerOne #138869 · OneLogin authentication bypass on WordPress sites via XML-RPC

- Source: `HackerOne report #138869`
- Source URL: https://hackerone.com/reports/138869
- Source topic: An alternate WordPress XML-RPC path exposed an authentication-bypass condition.
- Transferable test ideas:
  - Compare primary, mobile, XML-RPC, legacy, and administrative authentication entry points.
  - Check whether all entry points enforce the same account state, credential policy, and identity binding.
  - Verify the final authenticated subject and effective permissions instead of relying on a successful login response.
- Defensive anchor:
  - Centralize authentication policy across all entry points.
  - Disable or restrict legacy authentication surfaces that are not required.
  - Bind the resulting session to the identity and assurance state established by the same validated flow.

### HackerOne #241244 · Spring Security configuration allows agent sessions to be hijacked

- Source: `HackerOne report #241244`
- Source URL: https://hackerone.com/reports/241244
- Source topic: A security configuration allowed an agent session to be used outside its intended identity context.
- Transferable test ideas:
  - Map how agent, service, device, or machine sessions are created, authenticated, resumed, and invalidated.
  - Test whether a session identifier can be replayed or rebound across agents, users, or connection contexts.
  - Confirm the effective server-side identity and capabilities attached to the reused session.
- Defensive anchor:
  - Bind sessions to the authenticated principal and intended connection context.
  - Use framework security rules that cover every route and session-resumption path.
  - Rotate or invalidate session material after authentication-state changes.
