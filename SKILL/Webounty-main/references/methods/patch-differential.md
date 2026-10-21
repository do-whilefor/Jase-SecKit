# Patch differential and deployment conditions

## Use signals
Use for a feature toggle called a fix, cross-tenant rollout disagreement,
version-dependent 404, or a patched claim with only rejection status codes.
Use `static-dynamic-retest` for general static-to-runtime revision questions.

## Prerequisites
Locate the original boundary violation and its complete request/response,
normal behavior, deployment/configuration, actor, object, and acceptance rule.
State what changed and what a fix must preserve. Each tenant or deployment
needs its own valid identity and normal baseline; a token minted in one tenant
does not establish a valid control in another. The comparison set comes from
the current scope and affected dependency, not all discovered hosts.

## Discriminating test
Compare the original invariant before and after the change, with normal
business behavior observed under the current conditions. Store each matrix
cell's actor, tenant, version, configuration, raw references, observer validity,
and assessment separately. Distinguish deployed code, feature configuration,
and observed boundary behavior; retrieve deployment/configuration evidence if
the mechanism matters. A secure configuration can enforce the required
boundary even without a code change. State durability and rollout gaps
explicitly rather than declaring either universal closure or inevitable failure.

## Valid and invalid observations
Valid: an original reproducer known to detect the issue, current evidence of
the corrected boundary, and a passing legitimate operation in the same relevant
conditions. Invalid as sole proof: uniform 403, changed error text, 200 with
`status:failed`, 404, invalid cross-tenant token, or a placeholder operation.
A fake object may bypass lookup-dependent behavior or still trigger state
changes; it neither proves a safe operation nor reproduces the original case.

## Support / refute / uncertain
Support a fix only for the cells with valid attack and normal controls. A
current disallowed result refutes closure for that cell. Missing baseline,
route/deployment mismatch, or unavailable post-operation readback means
uncertain. Endpoint disappearance does not prove removal or vendor awareness;
response uniformity does not locate a WAF or annotation. Preserve old facts
under their original versions instead of rewriting history.

## Stop and reopen
Stop when the affected cells are answered or a required deployment/control
observation is unavailable. Reopen only cells affected by a rollout, feature
toggle, route, identity policy, or consumer change. Keep surviving capabilities
and broken chain edges separate rather than reopening every old variant.

## Source provenance and limitations
Paths are relative to Web-Vulnhunt; hashes are in `catalog.json`.
- `references/methodology-lessons.md`, LESSON 3, lines 38–59; LESSON 8,
  lines 132–150: source supplies historical patch and rollout comparisons;
  its status-only and vendor-awareness conclusions are not inherited.
- `scripts/patch-verify.sh`, token reuse and verdict, lines 67–127: static
  inspection found one token reused across tenants and 403 classified as
  patched without a normal control. No external script is executed by this card.
