---
name: security-hunt
description: >-
  Perform authorized, evidence-driven security testing across Web, APIs,
  identity, authorization, files, protocols, cryptography, native code,
  containers, and system boundaries. Use when the user supplies an authorized
  target, traffic, code, credentials, anomaly, or vulnerability-research goal
  and expects dynamic validation, impact verification, and evidence-based
  rating rather than a checklist or scanner summary.
argument-hint: "<target/scope, entry point, anomaly, identities, or testing goal>"
disable-model-invocation: true
allowed-tools: Read Grep Glob
---

# Security Hunt

Use this as the only user-facing entry point. Route internally; never ask the
user to choose a module, Profile, or vulnerability category.

## Input

$ARGUMENTS

Combine the arguments with the current conversation. Do not ask again for known
information. If execution cannot begin, ask only for the missing target or entry
point and the identity, session, object, or environment needed to test it.

Treat user-supplied targets and accounts as the authorized scope. Do not ask for
proof of authorization unless the scope changes.

## Non-Negotiable Invariants

- Start from a security boundary, not a vulnerability name.
- Validate on the current target through real requests, state, files, logs, or
  system effects. Static clues and historical cases generate hypotheses only.
- Keep technical existence and actual impact as separate evidence gates.
- Keep `rating: unrated` until direct evidence supports every retained impact
  claim and rules out reflection, cache artifacts, and accidental success.
- Let progressive loading limit context consumption, never testing breadth,
  validation depth, or cross-component follow-through.
- Read a matching Reference only after recording a current-target hypothesis
  and baseline. This prevents historical cases from becoming conclusions.

## 1. Model One Boundary Hypothesis

Represent each hypothesis with this contract:

```text
Subject × Entry Point × Object × Relationship × Action × State × Trusted Field
× Security Expectation × Backend Result
```

Write it as one falsifiable sentence:

```text
Given <subject/state> through <entry point>, the server should enforce
<expectation> for <action/object/relationship>; vary <one trusted field or axis>
and verify <backend result> through observable final state.
```

Map the real execution graph before selecting a vulnerability label:

```text
Page/route → component → API/message → credentials → object/relationship
→ action/state → consumer → verifiable boundary
```

## 2. Route by the First Decisive Semantic Divergence

The first decisive divergence is the earliest point in actual execution where:

1. two relevant components assign different security meaning to the same value,
   object, identity, or state; and
2. that disagreement is necessary for the observed effect and can be isolated
   with the available access.

It is not the first suspicious string, the earliest source-code line, or the
vulnerability name with the largest theoretical impact.

| Decisive boundary | Primary module |
|---|---|
| Data becomes control syntax or is reinterpreted by a later consumer | `${CLAUDE_SKILL_DIR}/modules/input.md` |
| Parsing, normalization, routing, URL handling, or proxying changes identity or target | `${CLAUDE_SKILL_DIR}/modules/normalize.md` |
| Subject, role, capability, ownership, tenant, session, purpose, audience, or lifecycle is misbound | `${CLAUDE_SKILL_DIR}/modules/identity.md` |
| Ambient credentials, messages, cache variants, origins, or shared protocol state cross subjects | `${CLAUDE_SKILL_DIR}/modules/channels.md` |
| Preconditions, order, replay, versions, counts, atomicity, or mandatory policy fail | `${CLAUDE_SKILL_DIR}/modules/state.md` |
| Verification succeeds for the wrong object, context, role, order, or consumer | `${CLAUDE_SKILL_DIR}/modules/crypto.md` |
| The decisive object is an inode, handle, syscall, native value, resource budget, sandbox, or privileged IPC | `${CLAUDE_SKILL_DIR}/modules/system.md` |

When boundaries overlap, choose one primary Profile. Load an adjacent Profile
only after its handoff condition is observed; the list below is decision
support, not an instruction to preload or test every neighboring Profile.
Common handoffs:

- File content changes meaning across stages → `input/file-chain`; a canonical
  path resolves elsewhere → `normalize/path`; check and use reach different
  filesystem objects → `system/fs-identity`.
- SAML flow/session/IdP/account binding → `identity/oauth-sso`; the verified XML
  node differs from the consumed node → `crypto/xml-signature`.
- One-time artifact subject/purpose/lifecycle binding → `identity/tokens`;
  concurrent consumption or atomicity → `state/race`.
- Wrong object/relationship → `identity/object-authorization`; wrong function or
  role → `identity/role-capability`; tenant context is lost →
  `identity/tenant-isolation`.
- Cookie-authenticated forged HTTP action → `channels/csrf`; long-lived
  connection or per-message capability → `channels/browser-channel` or
  `channels/graphql-ws`.
- Downstream query/template/expression grammar treats data as control →
  `input/server-interpreters`; protocol delimiters become fields →
  `input/field-injection`.
- A missing cache-key dimension reuses a response → `channels/cache-variant`;
  mutable protocol state contaminates later requests → `channels/shared-state`.

## 3. Load Only What the Current Hypothesis Needs

1. Read `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md`.
2. Read the primary module and Profile.
3. Record a baseline.
4. Read the matching Reference to expand variants, never to establish facts.
5. Load an adjacent Profile when its handoff condition is observed, a coverage
   gap remains, or the value reaches its consumer.

Do not impose a fixed maximum on modules or Profiles.

Resolve a routed `<name>` to
`${CLAUDE_SKILL_DIR}/profiles/<name>.md`; its hypothesis-expansion notes are in
`${CLAUDE_SKILL_DIR}/references/<name>.md`.

Interpret Reference labels strictly:

- `Source topic` is a historical label, not a factual mechanism.
- `Source URL` and `Source locator` make a factual note auditable.
- `Reported boundary` contains only facts checked against a primary source.
- `Transferable test ideas` generate current-target variants, not conclusions.
- `Impact closure` states what the current target still has to prove.
- `Defensive anchor` informs remediation only after validation.

## 4. Execute the Evidence Loop

```text
Read blackboard → map exposure → generate hypotheses → fill coverage gaps
→ select discriminator → validate technical boundary → mark technical_hit/unrated
→ validate each impact claim → Guardian → rate or close → update blackboard
```

1. Establish a baseline using the same identity, object, state, and channel.
2. Change one discriminating dimension and preserve the raw request or input.
3. Follow the value through every relevant consumer to the final effect.
4. Corroborate the technical effect with a fresh reproduction, final-state
   readback, or another signal that rules out reflection and response artifacts.
5. On the first reproducible boundary failure, set
   `finding_status: technical_hit` and keep `rating: unrated`.
6. Validate capability, affected subjects and objects, data/assets, business
   outcome, scope, scalability, prerequisites, and limitations separately.
7. Apply Guardian: reject scanner-only, reflection-only, error-only,
   self-only, public-data-only, or theoretical claims unless their actual
   security impact is directly established.
8. Review blind spots and dynamically test the highest-value uncommon,
   cross-component, legacy, asynchronous, protocol-specific, and
   implementation-specific paths.
9. Preserve concise evidence, update the existing hypothesis entry, and clean
   up test artifacts.

## 5. Persist Only Canonical State

Use only:

- `finding_status`: `lead | technical_hit | impact_verified | closed`
- `rating`: `unrated | info | P3 | P2 | P1`
- terminal result: `VULN_FOUND` | `NOT_REPRODUCED` | `LOW_ROI` |
  `NEED_INPUT`

The full transition gates, per-finding terminal mapping, and multi-hypothesis
precedence live only in
`${CLAUDE_SKILL_DIR}/framework/verify-evidence.md`.

## Operating Rules

- A failed request, error, insensitive object, or invisible result does not
  close a lead. The next attempt must add a new identity, object, entry point,
  state, representation, consumer, or item of evidence.
- Do not repeat equivalent attempts. Merge duplicates in the blackboard.
- Do not stop at “accepted,” “bypassed,” “executed,” or “returned data.” Verify
  the exact capability, final object, affected scope, and prerequisites.
- Do not infer impact or rating from a vulnerability name, scanner, CVSS score,
  framework fingerprint, historical case, or theoretical chain.
- Do not use read-only, low-risk, shallow, lightweight, offline, conservative,
  or avoidance-based language to conceal incomplete validation.
- Stay inside the authorized scope, collect only the minimum sensitive evidence
  needed for the claim, and clean up reversible test state.

## Response Contract

State the selected testing direction briefly, then proceed. Keep every lead and
technical hit `unrated` until the impact gate passes. Ask only for input that is
genuinely required after viable alternatives are exhausted.

At task completion, end the final response with exactly one terminal result on
its own final line.
