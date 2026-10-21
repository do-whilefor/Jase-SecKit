# Credential capability and its final consumer

## Use signals
Use for a recognized secret that cannot mint, an issued token with no consumer,
a replayed bootstrap credential, or a dormant capability after downstream fixes.
Use the general `flow-chain` card for stages without a credential-capability gap.

## Prerequisites
Separate credential origin, acquisition prerequisites, issue/exchange event,
claimed metadata, actual acceptance, and final restricted business result.
Record issuer, audience, tenant, application, actor, purpose, lifetime, session
generation, and deployment where known. Never copy raw secrets into a method
card or use token prefixes as authority. Decoded claims remain unverified
metadata until signature and acceptance evidence support the interpretation.

## Discriminating test
Retrieve the exact product and the evidence linking it to the next consumer;
correlate secret references or digests rather than exposing the secret. Ask
which necessary stage currently fails: credential recognition, enabled grant,
issuance, audience/scope acceptance, or final action. Compare a valid normal
flow and the blocked branch under compatible conditions. Keep independently
issued credentials separate; one from legitimate enrollment cannot silently
complete a chain beginning with a leaked PIN. Retrieval of methodology does
not authorize using a discovered credential or issuing a new one.

## Valid and invalid observations
Valid: observed issuance plus a linked consumer result, or a demonstrated
rejection of a necessary stage with a valid normal control. Invalid as sole
proof of impact: secret recognition, nonempty bearer, decoded admin claim,
token exchange success, intermediate sessionId, or benign endpoint acceptance.
Several successful replays demonstrate reuse over that observed interval;
they do not prove infinite mintability, no expiry, or future persistence.

## Support / refute / uncertain
Support only the deepest connected capability actually observed. A valid
consumer rejection refutes that consumer branch under its conditions without
erasing a separately demonstrated issuance capability. Missing grant, signing
key, session binding, revocation rule, or final result leaves the chain uncertain.
An expired token is not a dormant refresh capability unless that refresh path
has its own evidence. Current impact and a conditional future chain stay separate.

## Stop and reopen
Stop at a missing necessary dependency or a valid terminal rejection; record
the exact blocker. Reopen only if the dependency, consumer policy, lifetime,
revocation state, or deployed acceptance path changes, not because a new
hypothetical downstream vulnerability can be imagined.

## Source provenance and limitations
Paths are relative to Web-Vulnhunt; hashes are in `catalog.json`.
- `references/methodology-lessons.md`, LESSON 7, lines 120–128; LESSON 10,
  lines 176–188; LESSON 11, lines 204–270: source reports corrected F4/F5/F8
  chains. Their IDs, scores, and durations are historical assertions only.
- `references/http-auth-filter-testing.md`, §10, lines 418–462: recognized
  secret versus unavailable grant is useful; finite mints do not justify the
  source's unexpiring/unlimited labels.
