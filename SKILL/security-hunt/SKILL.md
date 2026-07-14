---
name: security-hunt
description: Unified entry point for authorized security testing and vulnerability research across Web, APIs, identity, files, protocols, cryptography, native code, containers, and system boundaries. Routes the task internally, performs dynamic validation, and requires independent technical and impact evidence before severity assignment.
allowed-tools: Read Grep Glob Bash
---

# Security Hunt

Use this as the only user-facing entry point. Do not ask the user to choose an internal module, Profile, or vulnerability category.

## Task

Work from the target, scope, traffic, code, files, credentials, observations, and goals supplied by the user.

User input:

$ARGUMENTS

If the command and conversation do not contain enough context, ask only for the missing target, entry point or anomaly, and available identity or session. Do not repeat known information.

## Internal Routing

Select the primary module from the earliest security-relevant semantic divergence. Read it before planning tests.

| Boundary | Module |
|---|---|
| Cross-stage reinterpretation of files, objects, browser content, logs, headers, or fields | `${CLAUDE_SKILL_DIR}/modules/input.md` |
| Different meanings after normalization, parsing, routing, canonicalization, URL handling, or proxying | `${CLAUDE_SKILL_DIR}/modules/normalize.md` |
| Subject, account, session, purpose, audience, client, or lifecycle binding | `${CLAUDE_SKILL_DIR}/modules/identity.md` |
| Per-message authorization, cache variants, cross-origin channels, or shared protocol state | `${CLAUDE_SKILL_DIR}/modules/channels.md` |
| Preconditions, ordering, replay, versions, counts, atomicity, or mandatory policy | `${CLAUDE_SKILL_DIR}/modules/state.md` |
| Verification succeeds for the wrong object, context, role, ordering, or consumer | `${CLAUDE_SKILL_DIR}/modules/crypto.md` |
| Inodes, handles, system calls, native values, resource limits, sandboxes, or privileged IPC | `${CLAUDE_SKILL_DIR}/modules/system.md` |

Common overlaps:

- File chain vs path vs filesystem identity: reinterpretation across stages → `input`; canonicalization changes the target → `normalize`; validation and use reach different filesystem objects → `system`.
- SAML: state, session, IdP, or account binding → `identity`; verified and consumed XML nodes differ → `crypto`.
- One-time artifacts: subject, purpose, or lifecycle binding → `identity`; concurrent consumption or atomicity → `state`.
- Cache variants vs shared state: an omitted key dimension reuses a response → `channels/cache-variant`; mutable protocol state contaminates later requests → `channels/shared-state`.

Start with the smallest relevant material, but do not impose a fixed maximum on modules or Profiles. Maintain plausible adjacent and combination paths, and load them whenever the hypothesis, observed behavior, unexplained result, coverage gap, or downstream consumer requires it. Progressive loading limits context use, not testing breadth or depth.

## Execution

1. Read `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md`.
2. Read the primary module and the Profiles needed for the current hypothesis.
3. Establish a baseline before reading matching References for additional variants.
4. Follow the value through every relevant consumer and verify the final technical effect independently.
5. On the first reproducible PoC or security-boundary failure, set the finding to `unrated`; a technical hit is not an end condition.
6. Enter independent impact validation and actively test permissions, subjects, objects, data, assets, business outcomes, scope, scalability, prerequisites, and combination paths.
7. Assign severity only after the claimed impact is independently evidenced and the impact gate is complete.
8. Before closing, review blind spots and dynamically test the highest-value uncommon, cross-component, framework-specific, protocol-specific, and expert-level routes.
9. Preserve concise evidence and clean up test artifacts.

## Operating Rules

- Treat user-provided targets as authorized scope and remain within that scope.
- Do not reduce testing depth by defaulting to read-only, low-risk, shallow, lightweight, offline, conservative, or avoidance-based checks.
- Build concrete hypotheses, establish baselines, vary meaningful axes, and verify final effects independently.
- Do not stop because one request fails, one endpoint errors, one object is insensitive, one path has no visible result, or the first impact attempt fails. Vary identity, object, entry point, state, representation, channel, timing, and downstream consumer.
- Do not present scanner output, reflection, errors, theoretical gadgets, historical cases, or one-off anomalies as vulnerability facts.
- Use only: `candidate`, `testing`, `unrated`, `impact_testing`, `confirmed`, `not_reproduced`, `blocked`.
- Before `confirmed`, do not output, record, imply, or estimate severity. Never inherit severity or impact from a vulnerability name, scanner, CVSS score, historical case, or theoretical maximum.
- Every claimed impact requires its own independent physical evidence. Do not use one PoC to support additional untested claims.
- Preserve only the state and evidence needed to resume without repeating completed work.

## Response Behavior

Start from the user's task, state the selected testing direction briefly, and proceed with discovery and validation. Ask only for information genuinely required to continue. Keep technical hits explicitly `unrated` until impact validation is complete.
