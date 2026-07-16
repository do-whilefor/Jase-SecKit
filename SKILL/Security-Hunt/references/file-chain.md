# File Processing Chain · Reference

Load after selecting the `file-parser-pipeline` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### GRT-01-004 WP1/2: Ground Truth RCEs via Crafted Config Files

- Source: `7asecurity/pentest-report groundtruth`
- Source topic: GRT-01-004 WP1/2: Ground Truth RCEs via Crafted Config Files
- Transferable test ideas:
  - The data/code boundary is lost while input crosses components, bypassing an earlier layer’s assumption that it is ordinary text or a passive file.
- Defensive anchor:
  - Avoid shell concatenation and use structured APIs.
  - Validate configuration and metadata against strict schemas.
  - Isolate build/import environments.
  - Sign and pin sources.
  - Never auto-execute hooks or plugins from untrusted repositories.

### CSV Export Allows Arbitrary Command Execution in CSV File

- Source: `isec-partners/NCC Group - phpMyAdmin`
- Source topic: CSV Export Allows Arbitrary Command Execution in CSV File
- Transferable test ideas:
  - CSV is only a transport container, while spreadsheet software interprets certain cell prefixes as formulas,
    converting server-side data injection into client-side code execution.
- Defensive anchor:
  - Export formula-looking values as inert text and strip bypass characters such as leading tabs.
  - Prefix risky cells with an apostrophe.
  - Provide a safe-export mode and clearly warn about formula execution in external spreadsheet software.

### 11 Path traversal through chart's dependency Data Validation

- Source: `trailofbits/Helm Final Report 2020`
- Source topic: 11 Path traversal through chart's dependency Data Validation
- Transferable test ideas:
  - Validation occurs before canonicalization, or absolute paths, parent segments, links, or component-specific path semantics escape the sandbox root.
- Defensive anchor:
  - Canonicalize before writing and verify the final path prefix.
  - Reject absolute paths, parent traversal, and link entries.
  - Constrain writes through directory handles.
  - Extract into isolation and move only allowlisted outputs.

### Remote Code Execution via Conversation-/Nick-Name

- Source: `cure53/pentest-report Cryptocat-2`
- Source topic: Remote Code Execution via Conversation-/Nick-Name
- Transferable test ideas:
  - String concatenation, incomplete escaping, or dynamic evaluation moves data into a code context.
- Defensive anchor:
  - Avoid shell and `eval`.
  - Use parameterized process APIs and a fixed command allowlist.
  - Run with least privilege.
  - Centralize dangerous interpreter entry points and apply taint-oriented tests.
