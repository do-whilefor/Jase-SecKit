# Input Chains

## Goal

Trace semantic changes as the same input crosses multiple consumers, and locate where upstream treats it as data while downstream treats it as control content.

## Primary Boundary

Use this module as primary when the same attacker-controlled value is reinterpreted across processing stages or components. Prefer `normalize/path` when canonicalization alone changes the resolved target, and prefer `system/fs-identity` when a validated path and the filesystem object ultimately opened are different.

## Loading Order

1. Read `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md` first.
2. Choose one or two Profiles based on the entry point, component, and anomaly; do not load every Profile in the group at once.
3. After forming a testable hypothesis, read the matching Reference for additional cases and variants.
4. When a chain crosses boundaries, load only the additional module, Profile, and Reference required by the Profile’s “Combination Paths.”

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| File upload/import/export; archive extraction and dependency handling; configuration, repository metadata, and package installation | `file-chain` | File Processing Chain |
| Polymorphic deserialization; object merge/deep copy; automatic parameter binding | `object-types` | Objects & Types |
| HTML/SVG/MathML sanitization; rich-text editors; frontend templates | `browser-parse` | Browser Parsing |
| Deep merge/filtering; object-path assignment; configuration override | `prototype` | Prototype Pollution |
| Audit logs; SSH/operations platforms; CI output | `terminal-escape` | Terminal Escapes |
| HTTP headers/cookies; download filenames; MIME/email | `field-injection` | Protocol Field Injection |

Profile paths are `${CLAUDE_SKILL_DIR}/profiles/<name>.md`; Reference paths are `${CLAUDE_SKILL_DIR}/references/<name>.md`.

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
