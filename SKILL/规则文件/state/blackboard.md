# Blackboard

> Only record the information needed to resume testing, avoid repeated verification, and track impact verification. Do not record full reasoning, theoretical impact, or report content.

```yaml
tested:
  # - object: ""
  #   identity: ""
  #   result: ""
  #   vuln_evidence: ""
  #   impact_status: "unverified"
  #   impact: ""
  #   impact_evidence: ""
  #   combo: "none"
  #   next: ""
```

Field descriptions:

* `object`: Tested page, API, parameter, feature, file, business object, or security boundary.
* `identity`: Identity, role, account type, tenant, or login state used during verification.
* `result`: One-sentence technical result. After a vulnerability is first confirmed, mark it as `UNRATED`; do not write P1, P2, or P3 here.
* `vuln_evidence`: Request, response, screenshot, log, PoC, script, file, or other evidence proving the security boundary failure.
* `impact_status`: `unverified`, `verifying`, or `verified`. Grading is prohibited unless this field is `verified`.
* `impact`: Actual demonstrated impact only, including affected identity, data, permission, asset, business action, scope, and prerequisites. Do not record assumptions or theoretical maximum impact.
* `impact_evidence`: Independent physical evidence proving each stated impact, such as cross-account differences, state changes, sensitive data, permission results, files, logs, or backend outcomes.
* `combo`: Vulnerability type or attack-chain direction that may combine with the finding; write `none` if not applicable.
* `next`: Next impact-verification action, closure reason, missing input, or reopening condition.

Rules:

* A technical hit means `UNRATED`, not graded.
* After a hit, continue impact verification until the actual capability, affected target, observable result, scope, scalability, and prerequisites are proven or required input is genuinely unavailable.
* Do not change `impact_status` to `verified` unless the impact is supported by independent physical evidence.
* Do not record P1, P2, or P3 before `impact_status: verified`.
* Theoretical attack chains, scanner ratings, CVSS, vulnerability names, and model assumptions are not impact evidence.

