# Protocol challenge, principal, and consumer binding

## Use signals
Use for WebAuthn attestation/assertion gaps, rpAppId versus rpId confusion,
session preconditions, replay, or a client-controlled sessionId echo. This is
an evidence method, not a payload recipe or a current-target vulnerability.

## Prerequisites
Locate the legitimate ceremony and its policy: challenge issuance, freshness,
single-use requirement if applicable, principal/session, relying party,
origin, credential ownership, permitted user-presence/verification policy,
assertion verification, and final session creation. Distinguish protocol RP ID
from a vendor's application ID. Record unknown bindings rather than assuming
the historical vendor's session or nonce design applies here.

## Discriminating test
Build a binding ledger from existing raw messages and server state: which
stage creates each value, which stage may change it, and which consumer checks
it. Compare one binding axis only after a valid normal ceremony is established.
Follow the exact challenge and credential through registration persistence and
the appropriate assertion consumer; legacy, login, and conformance endpoints
can have different prerequisites. A response echo is a candidate only: determine
whether the echoed value becomes authoritative authenticated state and whether
the questioned actor can use that state. Record missing authenticators, session
context, or signing material as explicit blockers.

## Valid and invalid observations
Valid: a linked, policy-violating binding change with independent persistence
or final session evidence, plus normal and rejected controls. Invalid as sole
proof: `status:ok`, inventory count increase without the exact credential,
sessionId echo, a challenge, a 500 UUID, or acceptance of `fmt:none`. None
attestation can be a legitimate policy choice; the issue must concern account
authorization or verification requirements. An opaque credential ID alone
does not identify the authenticator model.

## Support / refute / uncertain
Support the particular missing binding only when the changed value is consumed
against policy. Credential persistence proves that stage, not account takeover;
the authentication consumer and usable session require separate evidence.
A valid binding rejection refutes that transition while preserving other
observed stages. Invalid protocol syntax or an unavailable normal ceremony
leaves the binding claim uncertain, not protected or exploitable.

## Stop and reopen
Stop when an evidenced required binding blocks the branch or the observer
cannot complete the normal ceremony. Reopen for changed challenge storage,
RP/application policy, session establishment, credential availability, or a
new evidenced consumer; do not reopen on an unrelated endpoint error.

## Source provenance and limitations
Paths are relative to Web-Vulnhunt; hashes are in `catalog.json`.
- `references/fido-webauthn-testing.md`, rpAppId binding and blocker triad,
  lines 106–146; Generic FIDO methodology, lines 203–247: source reports the
  F13 registration-to-login blocker. The card corrects echo/fmt:none/500
  shortcuts and does not adopt its severity or vendor-wide conclusions.
- `references/methodology-lessons.md`, LESSON 10, lines 176–188: source reports
  missing device/key dependencies and the withdrawal of a takeover claim.
