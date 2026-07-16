# Validation and Evidence

This is the common execution framework for every module and Profile. Profiles define where to test; this file controls validation, impact, status, evidence, closure, and severity.

## 1. Status Model

Use only these statuses:

- `candidate`: a concrete hypothesis exists but has not been dynamically validated.
- `testing`: baseline, variant, or chain validation is in progress.
- `unrated`: a reproducible PoC or security-boundary failure is independently verified; actual impact is not yet fully validated. Severity is prohibited.
- `impact_testing`: the technical finding is established and independent impact validation is in progress. Severity is prohibited.
- `confirmed`: claimed impact, affected scope, prerequisites, and limiting conditions are independently evidenced; severity may now be assigned.
- `not_reproduced`: not reproduced under documented conditions and coverage; this does not mean the vulnerability does not exist.
- `blocked`: a specifically identified identity, permission, object, input, environment, dependency, or observability
  capability is unavailable after viable alternatives have been tried.

Do not use `not_vulnerable`, `low_roi`, or convenience-based blockers. A technical hit must enter `unrated`; it must not jump directly to `confirmed`.

## 2. Technical Validation

Complete at least one full loop for every candidate:

```text
Security expectation → baseline → single-variable variant → server-side/downstream result → independent verification → cleanup
```

A technical finding reaches `unrated` only when all are true:

1. The testing identity can trigger the control point reliably.
2. The server, downstream component, or system object reaches an unexpected state.
3. The conclusion is not based only on frontend display, tool output, error text, or inference.
4. A clean session, second identity, fresh read, state query, log, file hash, object version, system result, or another independent signal confirms the effect.
5. The affected subject, object, state, capability, or trust boundary is identified.
6. The minimum PoC and its preconditions are reproducible.

A successful technical PoC proves existence, not severity, maximum impact, scope, scalability, or business consequence. It is never an end condition.

## 3. Validation Method

### 3.1 Establish the Baseline

Record the normal identity, object, state, request or action, response, and final side effect. Do not judge a difference without a baseline.

### 3.2 Vary One Dimension at a Time

Prioritize negative tests across:

- Subject: anonymous, account A/B, low/high privilege, different tenant, session, device, client, or IdP.
- Object: own/other object, parent/child, public/private, deleted, old version, boundary ID, or different object class.
- State: not started, pending, completed, revoked, expired, rolled back, failed, retried, or asynchronously processed.
- Representation: encoding, case, duplicate values, paths, types, content type, parameter source, protocol version, or parse order.
- Time: replay, concurrency, reordering, delay, timeout, retry, rollback, or recovery.
- Channel: Web, API, mobile, legacy endpoint, long-lived connection, import/export, callback, background job, or direct downstream interface.

Confirm the root effect before stacking transformations. Combine variants when needed to reach the final consumer or validate impact.

### 3.3 Follow the Final Consumer

Do not stop at “validation bypassed,” “error changed,” “rule matched,” or “request accepted.” Trace the actual execution path:

```text
Input → validation/normalization → persistence/forwarding → downstream parsing → authorization/capability change → final object or action
```

At each relevant hop, record the actual value, parser, identity, privilege, working directory, object version, consumer, and side effect.

### 3.4 Verify Independently

Prefer, in order:

1. Read the final object using another identity or clean session.
2. Query server-side state instead of trusting the submission response.
3. Compare permissions, balance, inventory, version, file hash, cache state, process, network target, or other final state before and after.
4. Use logs, job state, audit records, traces, system calls, or persistent artifacts.
5. Re-run the minimum PoC to confirm repeatability and conditions.

## 4. Independent Impact Validation

After `unrated`, move to `impact_testing` and actively validate:

- Effective permissions or capabilities gained.
- Affected subjects, identities, roles, tenants, sessions, devices, or clients.
- Affected objects and object classes.
- Data read, modified, created, deleted, disclosed, or corrupted.
- Files, processes, hosts, networks, credentials, secrets, infrastructure, or other assets affected.
- Persistent state, privilege, authentication, authorization, financial, operational, or business outcomes.
- Quantity, tenant reach, affected population, and maximum evidenced scope.
- Repeatability, automation potential, enumeration, reliability, concurrency, and amplification.
- Preconditions, required knowledge, user interaction, privileges, timing, and environmental dependencies.
- Limiting conditions, recovery behavior, detection, cleanup, and combination paths.

Every impact statement needs separate physical evidence mapped to that exact claim. One request or PoC must not be
reused to claim untested account takeover, code execution, cross-tenant reach, mass impact, persistence, or other
escalation.

When an impact attempt fails, do not stop. Vary the dimensions that could change the result:

- Identity, privilege, tenant, session, object, object class, and ownership.
- Lifecycle state, entry point, legacy path, channel, and parameter source.
- Representation, ordering, replay, concurrency, timing, downstream consumer, and asynchronous stage.

Continue until the impact is closed or a specific required input, permission, object, identity, environment, or observability capability is genuinely unavailable.

## 5. Evidence and Blackboard

Write evidence inside the target project, never inside the Skill directory:

```text
evidence/
├── blackboard.yaml
└── <profile>/<case-id>/
    ├── baseline.txt
    ├── variant.txt
    ├── technical-result.txt
    ├── technical-verify.txt
    ├── impact.txt
    └── cleanup.txt
```

Use `.http`, `.json`, `.log`, `.png`, `.pcap`, or another suitable extension. Keep only reproduction evidence and avoid unrelated sensitive data.

Use `${CLAUDE_SKILL_DIR}/framework/blackboard-template.yaml` as the canonical field layout. Copy it to
`evidence/blackboard.yaml` in the target project when a persistent blackboard is needed. Keep one entry per candidate
and update the existing entry instead of creating competing state sources.

The blackboard must preserve:

- Candidate identity: `case_id`, Profile, target, hypothesis, and security expectation.
- Testing context: subject, role, tenant, session, baseline, variant, final result, and independent verification.
- Impact evidence: affected subjects, objects, capabilities, data or assets, business outcomes, scope, scalability, prerequisites, and limitations.
- Coverage: tested identities, objects, states, channels, consumers, remaining gaps, blockers, and next action.
- Cleanup: required actions, completion result, and evidence.
- Severity gate: `severity.gate` remains `prohibited` until the item reaches `confirmed`; only then may it become `allowed` with an evidence-based rationale.

For race conditions, record concurrency, success rate, timing window, final invariant, and failed samples. For parser
differentials, record raw and normalized values at each layer. For cross-component chains, record each consumer,
identity, permission, object, and evidence separately.

## 6. Severity Gate and Reporting

Before `confirmed`:

- Do not output, record, imply, estimate, or reserve P1, P2, P3, P4, CVSS, or another severity.
- Do not derive impact or severity from the vulnerability category, scanner output, tool rating, historical case, framework behavior, CVSS, or theoretical maximum.
- Do not use speculative language to fill missing impact evidence.

A finding may become `confirmed` only when the report can show:

1. Affected subject, object, capability, and boundary.
2. Complete preconditions and testing identity.
3. Reproduction steps and minimum PoC.
4. Baseline, variant, technical result, and independent technical verification.
5. Each claimed impact with its own independent evidence.
6. Evaluable scope, scalability, prerequisites, and limitations.
7. Cleanup action and result.
8. Evidence-based severity justification derived only from validated impact.

An `unrated` or `impact_testing` item may be recorded as a technical finding, but it must contain no severity and no
unsupported impact claim. `blocked` must name the exact missing capability and the alternatives already attempted.

Do not present tool hits, missing headers, ordinary version disclosure, theoretical chains, anomalous responses, or historical outcomes as vulnerability facts.

## 7. Chained Validation

Treat every chain segment independently. Each segment keeps its own status and evidence; do not downgrade proven
segments to `candidate` because a later segment remains inferential.

Load adjacent Profiles when a value is reparsed, identity crosses sessions or lifecycle stages, shared state amplifies
input, check and use are separated, or low-privilege input reaches a privileged consumer.

For each segment, record:

```yaml
- segment:
  expectation:
  result:
  evidence:
  status: candidate|testing|unrated|impact_testing|confirmed|not_reproduced|blocked
```

An unverified downstream segment remains `candidate`; the proven technical segment remains `unrated` or
`impact_testing`. The overall chain cannot claim the downstream impact or receive severity until every required
segment and impact is independently evidenced.

## 8. Blind-Spot Expansion and Closure

Before closing testing or producing the final report:

1. Review assumptions not dynamically tested.
2. Identify untested identities, objects, states, channels, consumers, protocols, legacy paths, async jobs, trust boundaries, and combination paths.
3. Generate uncommon, cross-component, framework-specific, protocol-specific, implementation-specific, and expert-level hypotheses.
4. Dynamically test the highest-value new routes.
5. Record remaining coverage gaps and exact blockers.

Routine checklist completion, one failed path, or low expected return is not an end condition. Close only when impact
is confirmed, current hypotheses are not reproduced under documented coverage, or a specific blocker prevents further
validation.
