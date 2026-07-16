# Security Hunt

Single-entry Claude Code Skill for authorized, evidence-driven vulnerability research.

## Install

Copy the `security-hunt` directory to `.claude/skills/`, then use:

```text
/security-hunt <target, entry point, anomaly, or testing goal>
```

The root Skill routes internally across 7 modules and 37 Profiles. Profiles
contain testing methods; References provide hypothesis seeds that load only
after a current-target baseline exists. `framework/verify-evidence.md` is the
single source of truth for finding state, evidence, impact, rating, closure, and
terminal results.

This package targets Claude Code. Its `argument-hint` and
`disable-model-invocation` frontmatter fields are Claude Code extensions, so a
base Agent Skills validator may report them as unknown.

Progressive loading reduces context use only. It does not limit testing breadth,
dynamic validation depth, cross-component expansion, or impact verification.

The Skill preapproves only `Read`, `Grep`, and `Glob`. Request-producing and
mutating commands remain available under the user's normal Claude Code
permission settings; `allowed-tools` is not used as an availability allowlist.

Historical cases never establish current-target impact or rating. Every
technical segment must be corroborated, and every retained impact claim needs
direct current-target evidence.

## Validation

Run the built-in structural validator after editing the Skill:

```bash
python3 scripts/validate_skill.py
```

The validator requires Python 3.10 or newer and uses only the standard library.

The validator checks frontmatter, routes, Profile/Reference identity, required
Profile sections, combination paths, state vocabulary, terminal mapping,
Markdown fences, Python syntax, source fields, stale template phrases, routing
fixture coverage, and common text-cleaning regressions. It does not run a model
or measure routing quality, and URL checks do not verify source content.
