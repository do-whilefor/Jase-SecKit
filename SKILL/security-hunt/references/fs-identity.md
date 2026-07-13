# File-Object Identity · Reference


Load on demand after selecting the `filesystem-object-identity` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### 7asecurity/pentest-report-conda-forge-RC1.0 · CON-01-013 WP2: Unauthorized Artifact Modification via Race Condition
- Value: 10/10; race condition / path traversal / cross-component attack chain.
- Chain: The attacker controls a workspace, repository, archive, or local file → prepares a symlink or concurrent replacement → a privileged process follows the new target after validation → arbitrary file read/overwrite, artifact tampering, or privilege escalation.
- Bypass: Exploit the timing gap between a pathname and the real inode/handle so ownership, directory, or extension checks no longer constrain the object that is used.
- Defensive anchor: Use `openat2`, `O_NOFOLLOW`, and directory file descriptors; validate the opened object with `fstat`; use atomic creation and rename; isolate untrusted workspaces and prohibit links across trust boundaries.


## Source Coverage

- Full reports: 5.
- HackerOne reports: 0.
- Full report IDs:
  - 7asecurity/pentest-report-conda-forge-RC1.0
  - cure53/pentest-report fdroid
  - isec-partners/ncc osquery security assessment 2016 01 25
  - quarkslab/VeraCrypt-Audit-Final-for-Public-Release
  - x41-d-sec/X41-theQRL-Review-2018-Final-Report

