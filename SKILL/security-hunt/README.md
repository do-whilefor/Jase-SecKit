# Security Hunt

Single-entry Claude Code Skill for authorized vulnerability research.

## Install

Copy the `security-hunt` directory to `.claude/skills/`, then use:

```text
/security-hunt <target, entry point, anomaly, or testing goal>
```

The root Skill routes internally across 7 modules and 37 Profiles. Profiles contain testing methods; References
provide curated source notes or explicitly state when no reliable historical case is retained.
`framework/verify-evidence.md` is the single source of truth for status, evidence, impact validation, closure, and
severity.

Progressive loading reduces context use only. It does not limit testing breadth, dynamic validation depth, cross-component expansion, or impact verification.

Historical cases never establish current-target impact or severity. Every technical segment and every claimed impact must be independently reproduced on the current target.

## Validation

Run the built-in structural validator after editing the Skill:

```bash
python3 scripts/validate_skill.py
```

The validator checks frontmatter, routes, Profile/Reference links, combination paths, status vocabulary, Markdown
fences, source fields, stale template phrases, routing evals, and common text-cleaning regressions.
