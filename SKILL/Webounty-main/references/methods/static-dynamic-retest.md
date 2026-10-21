# Static-dynamic linkage and conditional retesting

## Use
Use when source, interface definitions, page code, policy, and observed traffic
appear inconsistent, or when a deployment or request condition has changed.
This card supplies a method, not evidence that an implementation is deployed.

## Test
Locate each static claim in its actual artifact and version. Match it to the
observed operation using method, host, port, path, and relevant media type or
operation name. A matching string is a candidate connection; seek evidence of
the executing route and final consumer before attributing runtime behavior.

Compare actor, object state, session generation, request template, deployment,
configuration, and relevant time conditions. Retrieve changes and newly
registered observations even when older pages did not cite them. Preserve
historical observations with their original conditions.

For a changed condition or proposed fix, identify which previous claim depends
on it. Rebuild the current legitimate baseline and check the original invariant
plus affected normal behavior. Scope additional checks to supported dependency
changes; unrelated text edits do not establish a new experiment requirement.

## Confirm
Support a runtime interpretation when the evidence connects the inspected
implementation or configuration to the actual observed operation. Support a
fix only to the extent the current evidence demonstrates the original boundary
and the necessary legitimate behavior under the changed conditions.

## Refute
An observed alternate route, incompatible version, or controlled current
counterexample can refute the proposed static-to-runtime connection or fix
claim. This does not erase what an older deployment actually did.

## Unknown
Source without deployment evidence, a missing response, a changed error
envelope, or an unexplained 404 leaves reachability and behavior unresolved.
Request the specific version, route, or current observation needed to decide;
do not convert a static candidate or an untested condition into coverage.
