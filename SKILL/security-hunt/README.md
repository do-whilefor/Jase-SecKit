# Security Hunt

Single-entry Claude Code Skill for authorized vulnerability research.

## Install

Copy the `security-hunt` directory to `.claude/skills/`, then use:

```text
/security-hunt <target, entry point, anomaly, or testing goal>
```

The root Skill routes internally across 7 modules and 32 Profiles. Profiles contain testing methods; References provide historical variant seeds; `framework/verify-evidence.md` is the single source of truth for status, evidence, impact validation, closure, and severity.

Progressive loading reduces context use only. It does not limit testing breadth, dynamic validation depth, cross-component expansion, or impact verification.

Historical cases never establish current-target impact or severity. Every technical segment and every claimed impact must be independently reproduced on the current target.
