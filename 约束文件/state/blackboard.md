# Blackboard

> One record per independent security hypothesis. Update the existing item; do not log each request, full traffic, reasoning, or report text.

```yaml
tested:
  # - target: ""
  #   finding_status: "lead"
  #   rating: "unrated"
  #   evidence: ""
  #   next: ""
```

- `target`: One-line minimum description of identity, entry point, object/relationship, action, state, and key variable.
- `finding_status`: `lead | technical_hit | impact_verified | closed`.
- `rating`: `unrated | info | P3 | P2 | P1`; only set after `impact_verified`.
- `evidence`: Decisive comparison, observable result, and original evidence reference.
- `next`: One next action; if closed, record the reason and reopening condition.

```text
impact_verified + P1/P2/P3 → VULN_FOUND
impact_verified + info     → LOW_ROI
closed + unrated           → NOT_REPRODUCED
lead/technical_hit + unrated + missing requirement → NEED_INPUT
```
