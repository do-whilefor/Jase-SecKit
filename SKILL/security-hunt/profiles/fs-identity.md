---
id: filesystem-object-identity
group: system
reference: ../references/fs-identity.md
---

# File-Object Identity

**Use for:** high-privilege file operations, temporary directories, build workspaces, installers/updaters, archives, and synchronization clients.

**Misalignment to find:** Path-string validation and the actual open/write are not one atomic operation, allowing an attacker to change the final inode or handle through symlinks, reparse points, directory replacement, or races.

## Baseline

- A pathname is not a stable object identity.
- Symlinks, junctions, reparse points, drive links, or directory replacement can change the final target.
- Focus on checks performed against an old path object while use occurs against a new object.
- Record directory handles, file handles, inode/file IDs, open flags, and privilege boundaries.

## Validation Order

1. Confirm an attacker-controlled directory or path component.
2. Replace the link or directory between the check and the open.
3. Test recursive processing, cross-volume behavior, hard links, and link following.
4. After opening, read back object identity to prove the boundary violation.

## Variant Axes

- Timing gap between path validation and open/write/rename
- Symlinks, hard links, reparse points, directory replacement, and mount switching
- Inode/handle, owner, permissions, no-follow behavior, and atomic APIs
- Temporary directories, updaters, extractors, logs, backups, and cleanup flows

## Combination Paths

- `path`: Path Canonicalization
- `race`: Races & TOCTOU
- `syscall-options`: System Calls & Options
