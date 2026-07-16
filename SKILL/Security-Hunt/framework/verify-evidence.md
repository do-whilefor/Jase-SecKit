# Validation and Evidence

This file is the single source of truth for hypothesis shape, dynamic
validation, evidence, impact, rating, closure, and terminal results. Modules
choose where to test; Profiles choose useful discriminators; References expand
variants only after a current-target baseline exists.

## 1. Canonical Hypothesis Contract

Do not begin from a vulnerability label. Model one independent security
hypothesis as:

```text
Subject × Entry Point × Object × Relationship × Action × State × Trusted Field
× Security Expectation × Backend Result
```

The hypothesis must identify:

- the subject and current identity, role, tenant, session, device, or client;
- the entry point and credential or ambient authority it carries;
- the exact object, relationship, action, and lifecycle state;
- the client-controlled or cross-component field the server trusts;
- the server-side security property expected to hold; and
- a backend, downstream, or system result that can falsify the expectation.

Use one blackboard entry per hypothesis. Merge equivalent requests and repeated
failures into that entry instead of treating every payload as a new lead.

## 2. Operating Loop

```text
Read blackboard → map exposure → generate hypotheses → fill coverage gaps
→ select one discriminator → validate technical boundary → technical_hit/unrated
→ validate impact claims → Guardian → rate or close → update blackboard
```

Every validation round must answer four questions:

1. What does the server or final consumer trust?
2. What single subject, object, relationship, state, representation, time, or
   channel dimension changed from the baseline?
3. What final security property changed?
4. What corroborating observation proves that result and rules out an artifact?

## 3. Canonical State Model

Persist finding state and rating as separate fields.

### 3.1 Finding Status

Use only these values:

- `lead`: a concrete hypothesis exists, but a security-boundary failure has not
  passed the technical evidence gate.
- `technical_hit`: a reproducible boundary failure passed the technical gate;
  impact validation is incomplete.
- `impact_verified`: the obtained capability, affected subjects or objects,
  observable outcome, scope, prerequisites, and limitations are directly
  evidenced.
- `closed`: reasonable comparative validation did not reproduce the boundary
  failure, or a suspected technical hit was disproved by stronger evidence.

Allowed transitions:

```text
lead → technical_hit → impact_verified
lead → closed
technical_hit → closed       # only when the technical interpretation is disproved
```

Testing activity is not a finding status. Record the current discriminator in
`next`; do not invent status values such as `candidate`, `testing`,
`impact_testing`, `confirmed`, `blocked`, or `not_vulnerable`.

### 3.2 Rating

Use only `unrated | info | P3 | P2 | P1`.

- Keep `rating: unrated` for every `lead`, `technical_hit`, and `closed` item.
- Assign `info`, `P3`, `P2`, or `P1` only with
  `finding_status: impact_verified`.
- Derive rating only from demonstrated current-target impact, never from the
  vulnerability name, CVSS, scanner output, historical cases, or a theoretical
  maximum.

### 3.3 Terminal Result

End a completed task with exactly one of these markers:

| Terminal result | Finding status | Rating | Additional gate |
|---|---|---|---|
| `VULN_FOUND` | `impact_verified` | `P1`, `P2`, or `P3` | Reproducible PoC and original verifiable evidence exist |
| `NOT_REPRODUCED` | `closed` | `unrated` | At least one hypothesis was tested; all in-scope hypotheses are closed after reasonable comparison |
| `LOW_ROI` | `impact_verified` | `info` | No reportable finding or material unresolved hypothesis remains |
| `NEED_INPUT` | `lead` or `technical_hit` | `unrated` | A named identity, object, permission, environment, or input is unavailable after viable alternatives were tried |

For multiple hypotheses, evaluate the task-level terminal result in this exact
precedence order:

1. If any finding qualifies for `VULN_FOUND`, return `VULN_FOUND` and list
   unresolved gaps separately.
2. Otherwise, if a material unresolved hypothesis qualifies for `NEED_INPUT`,
   return `NEED_INPUT`.
3. Otherwise, if any finding qualifies for `LOW_ROI`, return `LOW_ROI`.
4. Return `NOT_REPRODUCED` only when at least one concrete hypothesis was
   tested and every in-scope hypothesis qualifies for it.

Do not convert incomplete impact validation into `LOW_ROI` or
`NOT_REPRODUCED`. Use `NEED_INPUT` only when the exact missing capability and
the viable alternatives already tried are recorded.

## 4. Technical Evidence Gate

Complete at least one full loop for every lead:

```text
Security expectation → baseline → one discriminating variant
→ final server/downstream result → corroborating verification → cleanup
```

Set `finding_status: technical_hit` only when all conditions hold:

1. The testing identity can reach and trigger the control point reliably.
2. Baseline and variant differ in one security-relevant dimension, or stacked
   transformations are individually controlled and necessary.
3. The server, downstream consumer, or system object reaches an unexpected
   security-relevant state.
4. The result is not inferred only from UI display, status code, reflection,
   error text, timing noise, scanner output, or a theoretical gadget.
5. A clean session, second identity, fresh reproduction, server-side read,
   state query, log, file hash, object version, process result, network
   observation, or another corroborating signal confirms the effect and rules
   out reflection, cache artifacts, stale state, and accidental success.
6. The affected subject, object, relationship, action, state, capability, or
   trust boundary is identified.
7. The minimum PoC and its preconditions reproduce reliably.

A successful technical PoC proves existence only. It does not prove the
maximum capability, affected scope, scalability, persistence, business impact,
or rating.

## 5. Comparative Validation Method

### 5.1 Establish a Comparable Baseline

Record the normal identity, role, tenant, session, object, relationship, state,
request or action, response, and final side effect. A response difference has no
meaning until the normal path and final state are known.

### 5.2 Select One Discriminator

Prioritize meaningful negative comparisons across:

- **Subject:** anonymous, account A/B, low/high privilege, different tenant,
  session, device, client, service identity, or IdP.
- **Object:** own/other, parent/child, public/private, active/deleted, current/old
  version, boundary ID, or a different object class.
- **Relationship:** ownership, membership, invitation, sharing, delegation,
  parent-child, binding, reference, or job ownership.
- **Action:** read, write, delete, export, upload, approve, pay, bind, callback,
  batch, cancel, restore, or retry.
- **State:** unstarted, pending, completed, revoked, expired, rolled back,
  failed, retried, or asynchronously processed.
- **Representation:** method, content type, encoding, case, duplicate values,
  parameter location, scalar/array/object type, path form, or parse order.
- **Time:** replay, concurrency, reordering, delay, timeout, retry, rollback,
  recovery, or version skew.
- **Channel:** Web, API, mobile, legacy route, long-lived connection,
  import/export, callback, background job, or direct downstream interface.

Confirm the root effect before stacking transformations. When a chain requires
multiple variants, preserve a control for every segment.

### 5.3 Follow the Final Consumer

Do not stop at “validation bypassed,” “accepted,” “rule matched,” “query
changed,” or “command ran.” Trace actual execution:

```text
Raw input → parsing/normalization → persistence/forwarding → downstream parse
→ authorization/capability decision → final object/action → corroborating readback
```

At every relevant hop, record the actual value, parser, identity, privilege,
working directory, object version, consumer, and side effect.

### 5.4 Prefer Corroborating Verification

Use the strongest available corroborating signal:

1. Read the final object with its owner, another identity, or a clean session.
2. Query server-side state instead of trusting the submission response.
3. Compare permission, balance, inventory, object version, file hash, cache
   state, process, socket peer, or other final state before and after.
4. Use audit logs, job state, traces, system calls, or persistent artifacts.
5. Re-run the minimum PoC with a fresh object to confirm reproducibility.

“Corroborating” does not always mean a different channel. If a response directly
contains the final disclosed asset or observable outcome, that response can
support the observation. Use a fresh controlled reproduction, owner readback,
or other check when needed to exclude reflection, caching, stale state, or a
one-off artifact. Never let one ambiguous response silently prove multiple
technical or impact claims.

### 5.5 Cross-Case Invariant Prompts

Use these prompts to generate discriminators, never as current-target facts:

- **Consumer meaning:** Do stored or forwarded bytes become control syntax in
  the final parser, terminal, template, query engine, shell, or protocol peer?
- **Capability destination:** Does authentication complete securely but deliver
  its token, session, file, callback, or approval to the wrong destination?
- **Object continuity:** Are validation, authorization, signature verification,
  and use bound to the same node, file object, immutable version, and digest?
- **Context completeness:** Does correlation bind every identity field, or only
  one nonce, ID, signature, key tag, hostname, tenant, audience, or purpose?
- **Work conservation:** Can a small valid input multiply candidates, retries,
  recursion, verification pairs, fan-out, CPU, memory, or persistent state?

## 6. Claim-Level Impact Gate

After `technical_hit`, create one impact claim per capability or business
outcome. Test each claim as a separate proposition; do not let one PoC silently
support account takeover, cross-tenant reach, code execution, persistence, or
mass impact that it did not demonstrate.

For each claim, determine and prove:

```text
Capability obtained → affected subject/object/asset → observable outcome
→ evidenced scope/scalability → prerequisites → limitations/recovery
```

Record an impact ledger:

| Field | Required content |
|---|---|
| `claim` | One exact read, write, delete, execute, takeover, or business-rule outcome |
| `capability` | The effective permission or action actually obtained |
| `affected` | Subjects, objects, tenants, data, assets, or processes evidenced |
| `observation` | Final state or result, not a theoretical consequence |
| `evidence` | Direct evidence for this exact claim; add readback or fresh reproduction when needed to rule out an artifact |
| `scope` | One object, bounded set, scalable set, bulk reach, or unknown |
| `prerequisites` | Identity, knowledge, interaction, timing, privileges, and environment |
| `limitations` | Reliability, lifecycle, recovery, detection, and failed boundaries |

Set `finding_status: impact_verified` only when every impact statement retained
for reporting has a complete ledger row. Remove unsupported claims instead of
softening them with “possibly,” “theoretically,” or “could.”

Claim-level independence means that each retained claim has evidence that
directly proves that claim. The same artifact may support more than one claim
only when it visibly establishes each one; shared citation is not a substitute
for missing capability, scope, or outcome evidence.

### 6.1 Evidence-Based Rating

- `info`: impact is proven to affect only the tester, test data, public or
  masked data, or another low-value condition without reportable security harm.
- `P3`: limited but real impact is proven; scope, privilege, sensitivity, or
  business value remains low.
- `P2`: proven impact affects other users, sensitive data, important
  permissions, critical assets, or important business processes.
- `P1`: proven control of core systems or critical assets, large-scale exposure
  of highly sensitive data, major financial impact, or systemic business harm.

Data type, object count, credential name, or vulnerability class is an impact
factor, not a rating by itself.

## 7. Evidence and Blackboard

Store state and evidence in the target project, never in the Skill directory:

```text
state/
└── blackboard.md
evidence/
└── <profile>/<case-id>/
    ├── baseline.<ext>
    ├── variant.<ext>
    ├── technical-result.<ext>
    ├── technical-corroboration.<ext>
    ├── impact-<claim-id>.<ext>
    └── cleanup.<ext>
```

Use `${CLAUDE_SKILL_DIR}/framework/blackboard-template.yaml` as the canonical
field layout for `state/blackboard.md`. Keep one entry per independent
hypothesis and update it in place.

The blackboard is a recovery index, not a report or traffic dump. Retain only:

- the hypothesis tuple, selected Profile, and security expectation;
- baseline/variant distinction and the final corroborated result;
- evidence paths and one row per impact claim;
- tested identities, objects, relationships, states, representations, channels,
  times, and consumers;
- remaining gaps, the next discriminating action, cleanup, and reopening rule;
- `finding_status` and `rating` under the gates above.

Keep full request/response bodies, captures, logs, screenshots, and files in the
evidence directory. Collect the minimum sensitive content needed to prove the
claim; label identity/session aliases consistently and preserve timestamps or
object versions needed for reproduction.

For races, record concurrency, success rate, timing window, final invariant,
and failed samples. For parser differentials, record raw and normalized values
at each layer. For cross-component chains, record every consumer, identity,
permission, object, segment status, and evidence reference separately.

## 8. Chained Validation

Treat every segment as an independent hypothesis:

```yaml
- segment_id:
  expectation:
  result:
  evidence: []
  finding_status: lead
  rating: unrated
  next:
```

An unverified downstream segment remains `lead`; a proven upstream segment
remains `technical_hit`. The overall chain cannot claim downstream impact or a
rating until every required segment and every retained impact claim passes its
own gate.

Load an adjacent Profile when:

- a value is reparsed by a new consumer;
- identity crosses sessions, tenants, devices, clients, or lifecycle stages;
- shared state amplifies input across requests or subjects;
- check and use are separated by time or object replacement; or
- low-privilege input reaches a privileged interpreter, service, or system call.

## 9. Guardian

Record these as `lead` by default and upgrade only after dynamic evidence proves
a security-boundary failure and actual impact:

- headers, CORS observations, versions, banners, TLS details, and ordinary
  errors;
- routes, JavaScript, source maps, Swagger/GraphQL schemas, comments, field
  names, and hidden interfaces;
- frontend-only restrictions when backend authorization still holds;
- self-XSS, standalone redirects, clickjacking, and CSRF with no meaningful
  state or identity impact;
- missing rate limits without demonstrated harm;
- uploads without execution, dangerous parsing, object binding, or an
  authorization consequence;
- public, masked, tester-owned, low-sensitivity, or unusable data and tokens;
- scanner findings, CVE fingerprints, historical outcomes, and theoretical
  chains without current-target evidence.

For disclosed data or credentials, prove sensitivity, validity, usable
privileges, affected assets, and business consequence while collecting only the
minimum evidence required.

## 10. Coverage, Closure, and Reopening

One failure or unproductive path never closes a lead. A follow-up attempt must
add at least one new identity, object, relationship, entry point, state,
representation, timing condition, downstream consumer, or corroborating item of
evidence. Merge attempts that add no new information.

Before closure:

1. Review assumptions that were never dynamically tested.
2. List untested identities, objects, relationships, states, channels,
   consumers, legacy paths, asynchronous jobs, protocols, and trust boundaries.
3. Generate uncommon, cross-component, framework-specific,
   implementation-specific, and expert-level hypotheses.
4. Dynamically test the highest-value new discriminators.
5. Apply the technical and impact gates again.

Set `finding_status: closed` only after key variables are reasonably covered,
no boundary failure remains reproducible, and further attempts would repeat
already tested conditions rather than add a meaningful discriminator. Record:

- the exact conditions tested;
- why the evidence did not establish the boundary failure; and
- a concrete `reopen_when` condition, such as a new identity, object class,
  environment, consumer, implementation version, or observable signal.

If a required identity, object, permission, environment, or input is genuinely
unavailable, retain `lead` or `technical_hit`, keep `rating: unrated`, record the
missing requirement and attempted alternatives, and return `NEED_INPUT`.

## 11. Cleanup

Use reversible test objects when they provide equivalent evidence, but do not
substitute safety language for incomplete validation. Stay within authorized
scope, avoid collecting unrelated sensitive data, record every created or
modified artifact, and verify cleanup through a fresh read or final state check.
