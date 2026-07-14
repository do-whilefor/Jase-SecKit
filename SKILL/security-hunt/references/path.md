# Path Canonicalization · Reference

Load after selecting the `path-canonicalization` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## HackerOne Case Index

### 178152 · Path canonicalization/real-target difference
- Knowledge value: 9/10; path traversal / framework-behavior exploitation / deserialization.
- Chain: `/etc/passwd` → path canonicalization/real-target difference, combined with deserialization/type-system semantic exploitation → the corresponding trust boundary is crossed → arbitrary code or command execution.
- Bypass: Use double decoding, backslashes, absolute paths, symlinks, archive entries, or canonicalization-order differences to escape the allowed directory; combine with unsafe type semantics.
- Defensive anchor: At the final file operation, enforce root containment against the fully decoded and canonicalized `realpath`; validate archive entries one by one; do not follow escaping symlinks; use the same boundary policy for read/write/delete; add deserialization cross-component regressions.

### 232614 · Path canonicalization/real-target difference
- Knowledge value: 9/10; path traversal / framework-behavior exploitation / other.
- Chain: A controllable input or business object from the report → path canonicalization/real-target difference → security controls and the final execution point disagree about subject, object, state, or input semantics → arbitrary code or command execution.
- Bypass: Use double decoding, backslashes, absolute paths, symlinks, archive entries, or canonicalization-order differences to escape the allowed directory.
- Defensive anchor: Enforce root containment on the final canonical object; validate archive entries; prohibit escaping links; use one policy across read, write, and delete.

### 378148 · Path canonicalization/real-target difference
- Knowledge value: 9/10; path traversal / framework-behavior exploitation / cross-component attack chain.
- Chain: `/var/opt/gitlab/gitlab-rails/uploads/nyangawa/myrepo/.\nevil -> /var/opt/gitlab` → path canonicalization/real-target difference, combined with file-processing order and multi-parser semantic differences → the corresponding trust boundary is crossed → arbitrary code or command execution.
- Bypass: Use path-normalization differences and combine them with downstream file-processing reinterpretation.
- Defensive anchor: Enforce root containment on the final canonical object, validate each archive member, prohibit escaping links, and add file-processing cross-component regressions.
