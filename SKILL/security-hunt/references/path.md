# Path Canonicalization · Reference


Load on demand after selecting the `path-canonicalization` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## HackerOne Case Index


### 178152 · Path canonicalization/real-target difference
- Value: 9/10; path traversal / framework-behavior exploitation / deserialization.
- Chain: `/etc/passwd` → path canonicalization/real-target difference, combined with deserialization/type-system semantic exploitation → the corresponding trust boundary is crossed → arbitrary code or command execution.
- Bypass: Use double decoding, backslashes, absolute paths, symlinks, archive entries, or canonicalization-order differences to escape the allowed directory; combine with unsafe type semantics.
- Defensive anchor: At the final file operation, enforce root containment against the fully decoded and canonicalized `realpath`; validate archive entries one by one; do not follow escaping symlinks; use the same boundary policy for read/write/delete; add deserialization cross-component regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 232614 · Path canonicalization/real-target difference
- Value: 9/10; path traversal / framework-behavior exploitation / other.
- Chain: A controllable input or business object from the report → path canonicalization/real-target difference → security controls and the final execution point disagree about subject, object, state, or input semantics → arbitrary code or command execution.
- Bypass: Use double decoding, backslashes, absolute paths, symlinks, archive entries, or canonicalization-order differences to escape the allowed directory.
- Defensive anchor: Enforce root containment on the final canonical object; validate archive entries; prohibit escaping links; use one policy across read, write, and delete.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 378148 · Path canonicalization/real-target difference
- Value: 9/10; path traversal / framework-behavior exploitation / cross-component attack chain.
- Chain: `/var/opt/gitlab/gitlab-rails/uploads/nyangawa/myrepo/.\nevil -> /var/opt/gitlab` → path canonicalization/real-target difference, combined with file-processing order and multi-parser semantic differences → the corresponding trust boundary is crossed → arbitrary code or command execution.
- Bypass: Use path-normalization differences and combine them with downstream file-processing reinterpretation.
- Defensive anchor: Enforce root containment on the final canonical object, validate each archive member, prohibit escaping links, and add file-processing cross-component regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 0.
- HackerOne reports: 30.
- HackerOne report IDs:
  - 470398, 2039870, 402473, 1948562, 676976, 1888808, 955016, 178152, 1040786, 622864, 1520931, 378148, 945122, 682774, 1251464, 903872, 858598, 1180252
  - 110352, 1115864, 1132378, 2078571, 730239, 473252, 578119, 890272, 487008, 232614, 288955, 784714

