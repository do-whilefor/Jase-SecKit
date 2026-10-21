# Execution linkage and fingerprint uncertainty

## Use signals
Use for static code claimed dynamically verified, outbound UA attribution,
shared-backend claims, different problem envelopes, or direct method invocation
being treated as proof of a normal entry path.

## Prerequisites
Locate the inspected artifact's version and its relation to the actual
deployment. State the claimed chain: reachable entry, transformation, runtime
execution, network/state effect, response consumption, and business consequence.
Identify which observations are independent and which repeat one capture.
Use existing authorized logs, traces, files, tests, and captures; this method
does not require installing hooks or external receivers.

## Discriminating test
Retrieve a correlation that ties the exact input and attempt to the claimed
effect, with compatible actor, time, deployment, and product identifiers.
Check both producer and consumer when the claim requires both. Compare the
strongest alternative: another caller, shared HTTP client, cached response,
generic exception handler, load balancer, or an unexecuted static route. Treat
UA, egress address, package path, TLS fingerprint, and nearby time as clues;
seek independent operation or runtime evidence before attributing execution
or service separation. A controlled invocation can demonstrate that method's
behavior while leaving ordinary UI reachability and prerequisites unknown.

## Valid and invalid observations
Valid: version-linked execution or state/traffic evidence with an attempt
correlation and a working observation control. Invalid as sole proof: source
string match, a generic UA, same configuration JSON, different error envelopes,
one receiver hit, or direct invocation claimed equivalent to a login-gated UI.
An outbound request followed by API 400 may prove an earlier network effect;
it does not establish response consumption or the impact of an internal target.

## Support / refute / uncertain
Support only the observed linked edges. A demonstrated alternate origin or
incompatible deployed version refutes the proposed attribution; it does not
erase a separately observed effect. Missing entry, correlation, receiver,
consumer, or independent state evidence leaves those edges uncertain. Repeated
reports of the same capture count as one source, not multiple confirmations.

## Stop and reopen
Stop when attribution is resolved, a required observer is unavailable, or the
candidate execution path is disproved. Reopen for a new version, proven route,
correlated runtime observation, or consumer evidence. Preserve rejected
attributions and their reasons so retrieval cannot silently restore them.

## Source provenance and limitations
Paths are relative to Web-Vulnhunt; hashes are in `catalog.json`.
- `references/methodology-lessons.md`, LESSON 9, lines 154–168: the two-sided
  observation idea is retained; its claim that direct invocation proves UI
  equivalence and that UA decisively identifies origin is not inherited.
- `references/http-auth-filter-testing.md`, §6 architectural signal,
  lines 236–238; §7 fetch signatures, lines 269–291: the former correctly
  retains alternate explanations, while the latter overstates UA separation.
- `references/fido-webauthn-testing.md`, architectural signal, lines 193–195:
  its categorical separate-service claim conflicts with the qualified HTTP
  account. This card preserves the uncertainty instead of choosing by repetition.
