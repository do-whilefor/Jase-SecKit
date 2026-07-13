# Blackboard

> Only record the information needed to resume testing and avoid repeated verification: what has been tested, the result, and what vulnerability types it can be combined with.

```yaml
tested:
  # - object: ""
  #   identity: ""
  #   result: ""
  #   evidence_path: ""
  #   combo: "none"
  #   next: ""
```

Field descriptions:

* `object`: The tested page, API, parameter, feature, file, or security boundary.
* `identity`: The identity, role, account type, or login state used.
* `result`: A one-sentence result, such as “no unauthorized access found,” “confirmed that favorites cannot be deleted without a token,” or “forged token was accepted.”
* `evidence_path`: Request packet, response packet, screenshot, log, PoC, or script path.
* `combo`: Vulnerability type or attack-chain direction that can be combined with this finding; write `none` if not applicable.
* `next`: Next action, closure reason, or reopening condition.

```
```
