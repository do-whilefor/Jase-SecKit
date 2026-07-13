---
name: security-hunt
description: Unified entry point for authorized security testing and vulnerability research. Use whenever the user asks to assess a target, hunt, validate, reproduce, or continue investigating vulnerabilities across Web, APIs, authentication, files, protocols, cryptography, native code, containers, or system boundaries. Routes the task to the smallest relevant internal module, Profile, and Reference, then requires reproducible evidence before reporting a finding.
allowed-tools: Read Grep Glob Bash
---

# Security Hunt

Use this as the only user-facing entry point. Do not ask the user to select an internal module, Profile, or vulnerability category.

## Task

Work from the target, scope, traffic, code, files, credentials, observations, and goals supplied by the user.

User input:

$ARGUMENTS

If the command has no useful arguments and the conversation does not already contain enough context, ask only for the missing target, entry point or anomaly, and available identity or session. Do not repeat information already provided.

## Route Internally

Select one primary module from the actual data flow and security boundary. Read it before planning tests. Add a second module only when evidence crosses a boundary and the additional module is necessary to close the chain.

| Signal | Internal module |
|---|---|
| Files, uploads, imports, archives, object binding, browser parsing, prototype state, logs, headers, or field injection | `${CLAUDE_SKILL_DIR}/modules/input.md` |
| Unicode, paths, duplicate parameters, HTTP framing, URLs, addresses, proxies, origins, or canonicalization differences | `${CLAUDE_SKILL_DIR}/modules/normalize.md` |
| Login, MFA, OAuth/SSO, sessions, tokens, account binding, subdomains, or identity lifecycle | `${CLAUDE_SKILL_DIR}/modules/identity.md` |
| postMessage, WebSockets, GraphQL, caches, cross-origin channels, or shared protocol state | `${CLAUDE_SKILL_DIR}/modules/channels.md` |
| Business workflows, ordering, replay, concurrency, TOCTOU, one-time actions, or mandatory policy enforcement | `${CLAUDE_SKILL_DIR}/modules/state.md` |
| Signatures, proofs, verification context, offline verifier material, SAML/XMLDSig, or cryptographic object binding | `${CLAUDE_SKILL_DIR}/modules/crypto.md` |
| Native values, system calls, file-object identity, resource complexity, sandboxes, containers, or privileged IPC | `${CLAUDE_SKILL_DIR}/modules/system.md` |

### Primary-route rule

Choose the module that owns the earliest security-relevant semantic divergence, not the module with the most matching keywords.

- Cross-stage reinterpretation of input → `input`.
- Different meanings produced by normalization, parsing, routing, or canonicalization → `normalize`.
- Subject, account, session, purpose, audience, or lifecycle binding → `identity`.
- Per-message authorization, cross-subject cache reuse, or shared protocol-state isolation → `channels`.
- Preconditions, ordering, replay, counts, versions, atomicity, or mandatory-policy enforcement → `state`.
- Verification succeeds for the wrong object, context, role, ordering, or consumer → `crypto`.
- The decisive boundary is an inode/handle, system call, native value, resource limit, sandbox, or privileged service → `system`.

Common overlaps:

- File chain vs path vs filesystem identity: cross-stage reinterpretation → `input`; canonicalization changes the target → `normalize`; validation and use reach different filesystem objects → `system`.
- SAML: state/session/account binding → `identity`; signed node and consumed node differ → `crypto`.
- One-time tokens: subject/purpose/lifecycle binding → `identity`; concurrent consumption or atomicity → `state`.
- Cache variants vs shared state: omitted cache-key dimension reuses a response → `channels/cache-variant`; mutable protocol state contaminates later requests → `channels/shared-state`.

Do not load all seven modules or all 32 Profiles by default. Keep one module primary and load only the additional material needed to validate the actual chain. Do not show the routing table unless the user asks about the architecture.

## Execution

1. Read `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md`.
2. Read the selected module.
3. Let that module select one or two Profiles under `${CLAUDE_SKILL_DIR}/profiles/`.
4. Form a concrete hypothesis and establish a baseline before reading the matching Reference under `${CLAUDE_SKILL_DIR}/references/` for additional variants.
5. Follow the value to the final consumer, verify the final effect independently, preserve concise evidence, and clean up test artifacts.

## Operating Rules

- Treat user-provided targets as the authorized scope and remain within that scope.
- Build a concrete hypothesis, establish a baseline, vary one meaningful axis at a time, and verify the final effect independently.
- Continue through downstream consumers, asynchronous jobs, alternate identities, lifecycle changes, and cross-component boundaries when they are part of the hypothesis.
- Do not present scanner output, reflection, errors, theoretical gadgets, or one-off anomalies as confirmed vulnerabilities.
- Use only: `candidate`, `testing`, `confirmed`, `not_reproduced`, `blocked`, `low_roi`.
- Preserve only the state and evidence needed to resume testing without repeating completed work.

## Response Behavior

Start from the user's task rather than listing capabilities. State the selected testing direction briefly, then proceed with discovery and validation. Ask only for information genuinely required to continue.
