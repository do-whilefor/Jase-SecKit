# File-Object Identity · Reference

Load after selecting the `filesystem-object-identity` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### 7asecurity/pentest-report-conda-forge-RC1.0 · CON-01-013 WP2: Unauthorized Artifact Modification via Race Condition
- Knowledge value: 10/10; race condition / path traversal / cross-component attack chain.
- Chain: The attacker controls a workspace, repository, archive, or local file → prepares a symlink or concurrent replacement → a privileged process follows the new target after validation → arbitrary file read/overwrite, artifact tampering, or privilege escalation.
- Bypass: Exploit the timing gap between a pathname and the real inode/handle so ownership, directory, or extension checks no longer constrain the object that is used.
- Defensive anchor: Use `openat2`, `O_NOFOLLOW`, and directory file descriptors; validate the opened object with `fstat`; use atomic creation and rename; isolate untrusted workspaces and prohibit links across trust boundaries.
