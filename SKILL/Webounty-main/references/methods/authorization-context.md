# Authorization scope and operation semantics

## Use signals
Use for token scope versus endpoint namespace, missing-annotation allegations,
method-dependent access, or an unexplained outlier in an authorization matrix.
Use `baseline-authz` for ordinary owner-versus-requester comparisons.

## Prerequisites
Retrieve the actual actor-action-object rule, including tenant, application,
sharing, identity class, and allowed operation. Establish each credential's
validity on its own permitted operation in the same deployment. Prefixes,
endpoint names, JWT text, and a neighboring controller's rules are candidate
context, not a specification of the tested operation's permissions.

## Discriminating test
Choose one matrix cell whose outcome distinguishes a scope error from an
invalid identity, public endpoint, request-schema failure, or intended sharing.
Use a valid operation template and compare the questioned identity against
an authorized actor and the relevant invalid/absent identity control. Include
only methods and object relations needed to resolve the gap. Preserve method,
path parameters, query, body, media type, session generation, and business
readback. Compare effective scopes from verified evidence, not only their
labels. A ratio of neighboring 403s to a single 200 prioritizes investigation;
it does not establish a missing annotation or access violation.

## Valid and invalid observations
Valid: identity validity, applicable rule, completed business result for the
specific operation, and compatible normal/rejection controls. Invalid: all
requests sent with `{}`, arbitrary path placeholders, expired tokens,
200 empty/default configuration, 403 tagged secure, or 404 tagged no route.
A GET label is not evidence of no side effects; method selection is constrained
by the current task's actual operation semantics and scope.

## Support / refute / uncertain
Support a scope violation when a valid actor obtains the result that the
applicable rule forbids under the observed conditions. Support a missing
annotation explanation only with deployed implementation linkage. A valid
business denial refutes the tested operation's violation, not every method in
the namespace. An unknown permission rule, identity, or request validity leaves
the cell uncertain and excluded from secured/vulnerable coverage totals.

## Stop and reopen
Stop expansion when the shared validity prerequisite fails or the selected
cell is answered. Reopen only for changed effective scope, method policy,
object sharing, template, or deployment. Keep untested cells visibly untested;
do not infer class-wide protection from a sampled namespace.

## Source provenance and limitations
Paths are relative to Web-Vulnhunt; hashes are in `catalog.json`.
- `references/http-auth-filter-testing.md`, §3, lines 62–116: source reports
  the F5/F7/F9 token matrix. Its namespace ratio and 200 status do not prove
  the current target's policy or implementation.
- `scripts/authz-matrix.sh`, extraction, request and classification,
  lines 53–128: static inspection found placeholder parameters, `{}` for all
  methods, incomplete operation coverage, and status-only verdicts. The card
  retains the comparison idea and requires evidence the script does not collect.
