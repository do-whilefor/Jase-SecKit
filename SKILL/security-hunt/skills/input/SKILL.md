---
name: Input Chains
description: Inputs are reinterpreted as they move across files, objects, browsers, logs, or protocol components. Use for authorized testing of file processing chains, objects and types, browser parsing, prototype pollution, terminal escapes, and protocol field injection.
user-invocable: false
allowed-tools: Read Grep Glob Bash
---

# Input Chains

## Goal

Trace semantic changes as the same input crosses multiple consumers, and locate where upstream treats it as data while downstream treats it as control content.

## Loading Order

1. Read `${CLAUDE_PLUGIN_ROOT}/framework/verify-evidence.md` first.
2. Choose one or two Profiles based on the entry point, component, and anomaly; do not load every Profile in the group at once.
3. After forming a testable hypothesis, read the matching Reference for additional cases and variants.
4. When a chain crosses boundaries, load material from other groups according to the Profile’s “Combination Paths.”

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| File upload/import/export; archive extraction and dependency handling; configuration, repository metadata, and package installation | `file-chain` | File Processing Chain |
| Polymorphic deserialization; object merge/deep copy; automatic parameter binding | `object-types` | Objects & Types |
| HTML/SVG/MathML sanitization; rich-text editors; frontend templates | `browser-parse` | Browser Parsing |
| Deep merge/filtering; object-path assignment; configuration override | `prototype` | Prototype Pollution |
| Audit logs; SSH/operations platforms; CI output | `terminal-escape` | Terminal Escapes |
| HTTP headers/cookies; download filenames; MIME/email | `field-injection` | Protocol Field Injection |

Profile paths are `${CLAUDE_PLUGIN_ROOT}/profiles/<name>.md`; Reference paths are `${CLAUDE_PLUGIN_ROOT}/references/<name>.md`.

## Workflow

1. Enumerate entry points, persistence locations, background jobs, and every downstream consumer.
2. Map the raw value, normalized value, parser, working directory, and privilege at each hop in actual execution order.
3. Validate one semantic transition first, then follow it to the final file, DOM, object, command, log, or protocol state.
4. Preserve evidence for each hop in a cross-component chain, then confirm the final result through an independent read or side effect.

## Do Not Stop Here

- Looking only at the upload endpoint while ignoring preview, export, build, synchronization, and installation stages.
- Stopping after a filter bypass without confirming that the final consumer actually executes under a different interpretation.
- Reporting ordinary reflection, an error, or an unreachable gadget as a vulnerability.

## Output

For each round, record only: Profile used, target object, testing identity, hypothesis, baseline, variant, independent verification, evidence path, current status, and next step or combination path. Mark a finding `confirmed` only when it meets the evidence threshold in the unified framework.
