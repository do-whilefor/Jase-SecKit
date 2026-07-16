# File-Object Identity · Reference

Load after selecting the `filesystem-object-identity` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### CON-01-013 WP2: Unauthorized Artifact Modification via Race Condition

- Source: `7asecurity/pentest-report-conda-forge-RC1.0`
- Reported focus: CON-01-013 WP2: Unauthorized Artifact Modification via Race Condition
- Transferable test ideas:
  - Exploit the timing gap between a pathname and the real inode/handle so ownership, directory, or extension checks no longer constrain the object that is used.
- Defensive anchor:
  - Use `openat2`, `O_NOFOLLOW`, and directory file descriptors.
  - Validate the opened object with `fstat`.
  - Use atomic creation and rename.
  - Isolate untrusted workspaces and prohibit links across trust boundaries.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
