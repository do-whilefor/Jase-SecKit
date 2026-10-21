# Filter, route, and controller reach

## Use signals
Use for an empty-body 400, case-variant HTML, apparent path-filter bypass,
generic 405, or disagreement between gateway and controller explanations.
This method supplies hypotheses, not evidence of the current stack.

## Prerequisites
Obtain the deployed operation's host, method, path, content type, request schema,
and a successful normal request. Locate the applicable access rule and a
same-deployment route or handler observation when available. OpenAPI describes
a candidate template; it does not establish deployment or business validity.

## Discriminating test
Trace only the relevant transformation from sent path to effective route,
validation, access decision, and business result. Compare a schema-valid
baseline with the questioned variant, preserving actor and other relevant
inputs. Use existing gateway logs, application traces, controller-specific
outputs, and the known static-page baseline to distinguish layers. Record
which layer is observed and which is inferred. Select a variant only when it
distinguishes an identified normalization or routing disagreement; do not
equate exhausting a historical payload list with coverage.

## Valid and invalid observations
Valid: a completed request tied to its effective handler and expected operation,
or a demonstrated pre-handler rejection with a working normal control.
Invalid as sole proof: 200 JSON, 200 HTML, 400, 405, an exception class, or the
text `Ensure the URL is valid`. Controllers can serve HTML, JSON can wrap
failure, and 405 has causes other than a static handler. Validation and
authorization order depends on the deployed configuration, not the framework
name. A failed final request can still have triggered earlier side effects.

## Support / refute / uncertain
Support controller reach when evidence links the actual request to that
handler; support unauthorized impact only with the disallowed business result
and access rule. A traced static fallback or pre-controller rejection refutes
controller reach for this variant. Without such linkage, report an ambiguous
envelope and the missing route evidence, not a secured endpoint or bypass.

## Stop and reopen
Stop variants sharing a demonstrated pre-controller failure. Reopen only when
the normal request, route map, normalization rule, handler evidence, or
deployment changes. A new status alone does not reopen all route variants.

## Source provenance and limitations
Paths are relative to Web-Vulnhunt; hashes are in `catalog.json`.
- `references/http-auth-filter-testing.md`, §1, lines 7–38: source describes the
  F7 malformed-body correction and historical SPA trap; categorical response
  table verdicts are deliberately weakened to candidates here.
- `references/bypass-catalogue.md`, §A, lines 13–54: the reported negative
  variants apply to the historical deployment, not every similar stack.
- `scripts/path-bypass-fuzzer.sh`, request and verdict heuristic, lines 80–130:
  static inspection shows status/content-type heuristics without route proof.
