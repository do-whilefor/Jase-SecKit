# Security Hunt

A lightweight vulnerability-research plugin with one user-facing command, 7 AI-routed internal Skills, 32 Profiles, 32 References, and one unified validation and evidence framework.

The original 89 PDFs and 528 HackerOne entries are not copied into the plugin. Transferable methods, representative cases, and source indexes are compressed into the References to keep the Skill directory small.

## Installation

For global use:

```bash
rm -rf ~/.claude/skills/security-hunt
cp -r security-hunt ~/.claude/skills/
```

For project-local use:

```bash
rm -rf .claude/skills/security-hunt
mkdir -p .claude/skills
cp -r security-hunt .claude/skills/
```

Reload the current Claude Code session:

```text
/reload-plugins
```

Restart Claude Code if the root command does not appear immediately.

Optional validation:

```bash
claude plugin validate ~/.claude/skills/security-hunt --strict
```

## Usage

Use only:

```text
/security-hunt
```

You can include the task on the same line:

```text
/security-hunt Test the file upload, preview, export, and download chain for the current target
```

The root Skill infers the relevant security boundary and loads the smallest useful set of internal Skills. The 7 internal Skills are AI-only and are not intended as user-facing slash commands.

## Internal Skills

| Internal Skill | Profiles | Scope |
|---|---:|---|
| `input` | 6 | Inputs reinterpreted across files, objects, browsers, logs, and protocol fields. |
| `normalize` | 6 | Meaning differences across characters, paths, parameters, HTTP messages, URLs, proxies, and origins. |
| `identity` | 4 | Subject and lifecycle mismatches in login, tokens, sessions, SSO, subdomains, and account binding. |
| `channels` | 4 | Operation-level authorization and state isolation across windows, long-lived connections, caches, GraphQL, and shared protocol state. |
| `state` | 3 | Preconditions, ordering, replay, versions, atomicity, business workflows, races, and mandatory policies. |
| `crypto` | 3 | Binding between verification results, business objects, protocol context, offline-verification material, and final consumers. |
| `system` | 6 | Low-level values, system calls, file-object identity, resource complexity, sandboxes, containers, and privileged IPC. |

## 32 Profiles

### Input Chains
- `file-chain` — File Processing Chain
- `object-types` — Objects & Types
- `browser-parse` — Browser Parsing
- `prototype` — Prototype Pollution
- `terminal-escape` — Terminal Escapes
- `field-injection` — Protocol Field Injection

### Normalization
- `unicode` — Unicode Normalization
- `path` — Path Canonicalization
- `params` — Parameter Parsing
- `http-boundary` — HTTP Boundaries
- `url-address` — URLs & Addresses
- `proxy-origin` — Proxies & Origins

### Identity State
- `oauth-sso` — OAuth/SSO
- `tokens` — Token Lifecycle
- `auth-state` — Authentication State
- `subdomain-trust` — Subdomain Trust

### Channels & APIs
- `browser-channel` — Cross-Origin Channels
- `cache-variant` — Cache Variants
- `graphql-ws` — GraphQL/WS Authorization
- `shared-state` — Shared Protocol State

### State & Races
- `workflow` — Business State Machines
- `race` — Races & TOCTOU
- `policy-bypass` — Mandatory Policy Bypass

### Cryptographic Semantics
- `crypto-binding` — Cryptographic Semantic Binding
- `offline-verifier` — Offline Verifiers
- `xml-signature` — XML Signature Consumption

### System Boundaries
- `value-lifetime` — Values & Lifetimes
- `syscall-options` — System Calls & Options
- `fs-identity` — File-Object Identity
- `complexity` — Algorithmic Complexity
- `sandbox` — Sandboxes & Containers
- `privileged-ipc` — Privileged IPC

## Directory Layout

```text
security-hunt/
├── SKILL.md                 # only user-facing entry: /security-hunt
├── .claude-plugin/
│   └── plugin.json
├── skills/                  # 7 AI-only internal Skills
│   ├── input/SKILL.md
│   ├── normalize/SKILL.md
│   ├── identity/SKILL.md
│   ├── channels/SKILL.md
│   ├── state/SKILL.md
│   ├── crypto/SKILL.md
│   └── system/SKILL.md
├── profiles/                # 32 testing Profiles
├── references/              # 32 case-and-mechanism References
└── framework/
    └── verify-evidence.md
```

## Design Constraints

- Keep `/security-hunt` as the only user-facing entry point.
- Let Claude select internal Skills; do not ask the user to choose a category.
- Do not turn the 32 knowledge modules into 32 peer-level Skills.
- Do not copy original PDFs, evaluation JSON, index CSV files, manifests, or intermediate artifacts.
- Do not duplicate validation, evidence, state, or reporting rules across multiple Skills.
- Do not present tool findings, theoretical chains, or anomalous responses as established vulnerabilities.
- Keep Profiles and References one-to-one, with short and stable names.
