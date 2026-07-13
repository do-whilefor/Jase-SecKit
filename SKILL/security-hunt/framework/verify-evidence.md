# Validation and Evidence

This file is the common execution foundation for all seven primary Skills. Profiles define what to look for; this framework turns leads into reproducible conclusions.

## 1. Status

Use only these statuses:

- `candidate`: a clear hypothesis exists but has not yet been dynamically validated.
- `testing`: baseline, variant, or chained validation is in progress.
- `confirmed`: the security boundary failed and the impact is independently reproducible.
- `not_reproduced`: not reproduced under the current conditions; this does not mean the vulnerability does not exist.
- `blocked`: required identity, environment, dependency, or observability is unavailable.
- `low_roi`: the main variants have been covered and further work has low marginal value.

Do not use `not_vulnerable`. Failure to reproduce describes only the current test conditions and coverage.

## 2. Minimum Validation Loop

Complete at least one full loop for every candidate:

```text
Security expectation → baseline request/action → single-variable variant → server-side or downstream result → independent verification → cleanup
```

A finding is established only when all of the following are true:

1. The control point can be triggered reliably by the testing identity.
2. The server, a downstream component, or a system object reaches an unexpected state.
3. The conclusion is not based only on frontend display, tool output, error text, or inference.
4. A second session, a fresh read, a state query, logs, a file hash, an object version, or another independent signal confirms the result.
5. The affected subject, object, state, or trust boundary can be identified.

## 3. Validation Order

### 3.1 Establish a Baseline

Record the identity, object, state, request, response, and final side effect of the normal flow first. Do not judge a difference without a baseline.

### 3.2 Change One Dimension at a Time

Prioritize negative tests along these dimensions:

- Subject: anonymous, account A, account B, low privilege, high privilege, different tenant.
- Object: own object, another user's object, parent/child object, deleted object, old version, boundary ID.
- State: not started, in progress, completed, revoked, expired, after rollback.
- Representation: encoding, case, duplicate values, paths, types, protocol version, parsing order.
- Time: replay, concurrency, reordering, delay, timeout, failure recovery.
- Channel: Web, API, mobile, legacy endpoint, long-lived connection, import/export, background job.

Confirm a single-variable effect before combining variants. Do not stack many transformations at once and obscure the root cause.

### 3.3 Follow the Value to the Final Consumer

Do not stop at “validation was bypassed,” “the error changed,” or “a rule matched.” Continue tracing:

```text
Input → validation/normalization → persistence/forwarding → downstream parsing → privilege change → final object or action
```

Record the actual value, parser, identity, working directory, object version, and side effect at every hop.

### 3.4 Verify Independently

Preferred order:

1. Read the final object using another identity or a clean session.
2. Query server-side state again instead of trusting the submission response.
3. Compare object state, permissions, balance, version, file hash, or cache hit before and after.
4. Use server logs, job state, audit records, or system-call results.
5. Re-run the minimum PoC when necessary to confirm stability and conditions.

## 4. Evidence Directory

Write evidence inside the target project, not inside the Skill directory:

```text
evidence/<profile>/<case-id>/
├── baseline.txt
├── variant.txt
├── result.txt
├── verify.txt
└── cleanup.txt
```

Extensions may be changed to `.http`, `.json`, `.log`, `.png`, or `.pcap` as appropriate. Keep only evidence required for reproduction and do not retain unrelated sensitive data.

Keep one blackboard entry per candidate:

```yaml
- profile:
  object:
  identity:
  hypothesis:
  result:
  evidence:
  status:
  combo:
  next:
```

## 5. Evidence Requirements

A `confirmed` finding must include at least:

- Complete preconditions and the identity used.
- A minimum replayable request, command, or operation.
- The key difference between baseline and variant.
- The server-side or downstream result.
- The independent verification result.
- The actual affected object and boundary.
- Cleanup action and result.

For race conditions, also record concurrency, success rate, timing window, and failed samples. For parsing differentials, record the raw and normalized value seen by every layer. For cross-component chains, record the permissions and consumer at every hop.

## 6. Reporting Threshold

The final report contains only:

1. Affected object.
2. Reproduction steps.
3. Minimum PoC.
4. Actual impact.
5. Severity and justification for resisting severity reduction.

Do not present tool hits, missing security headers, ordinary version disclosure, theoretical attack chains, or anomalies without independent verification as vulnerability facts.

## 7. Chained Validation

A single Profile explains only one segment of a boundary. Load related Profiles when:

- A validation result is consumed by a different parser downstream.
- Identity material crosses sessions, channels, or lifecycle stages.
- Shared caches, protocol state, or background jobs amplify a single input.
- A check and its use are separated by concurrency, reparsing, or object replacement.
- Low-privilege input ultimately reaches a privileged service, system call, or cryptographic verifier.

Validate every segment of a chain with the minimum loop. If any segment remains inferential, keep the entire chain at `candidate`.
