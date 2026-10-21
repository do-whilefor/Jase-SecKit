# Business baseline and authorization comparison

## Use
Use when identity, ownership, sharing, request validity, or a response envelope
could explain a suspected access difference. This card supplies a method, not
evidence about the current target.

## Test
Read the expected actor-action-object rule and its source. Identify the request
actor, object owner, tenant or sharing relation, session generation, and actual
business operation. Mark missing conditions as unknown.

Retrieve the owner's successful request and the requesting actor's own valid
business baseline. Compare the same relevant operation and input under the
chosen identity or object change. Preserve method, body, content type, deployment,
and timing conditions needed to interpret the comparison. Returned job or file
IDs are products; their difference alone is not a changed input variable.

Inspect response content and any necessary independent business readback. A
status code, body length, tool exit code, or nonempty credential alone cannot
establish request validity or an access decision. Repeated sampling needs a
stated noise question and a bounded budget.

## Confirm
Support a narrowly stated boundary violation only when a valid actor obtained
the restricted business result, the applicable rule disallows it, and the
comparison and evidence locate that result under the stated conditions.

## Refute
A valid normal baseline together with an explicit business rejection and no
restricted result can refute the specific tested claim. Keep the tested action,
actor, object, and conditions attached; other operations remain separate.

## Unknown
An expired session, invalid template, unclear sharing rule, incomplete response,
or missing owner baseline leaves the corresponding inference unresolved.
Retrieve or rebuild that prerequisite before interpreting an access difference.
