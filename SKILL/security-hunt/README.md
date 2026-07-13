# Security Hunt

A lightweight, single-entry Claude Code Skill for authorized vulnerability research. It contains one discoverable Skill, 7 AI-routed internal modules, 32 Profiles, 32 References, and one unified validation and evidence framework.

The original 89 PDFs and 528 HackerOne entries are not copied into this package. Transferable methods, representative cases, and source indexes are compressed into the References to keep the Skill small and progressively loaded.

## Installation

Global installation:

```bash
rm -rf ~/.claude/skills/security-hunt
cp -r security-hunt ~/.claude/skills/
```

Project-local installation:

```bash
rm -rf .claude/skills/security-hunt
mkdir -p .claude/skills
cp -r security-hunt .claude/skills/
```

Start a new Claude Code session after installation if the Skill is not discovered in the current session.

## Usage

Use the single entry point:

```text
/security-hunt
```

The task may be supplied on the same line:

```text
/security-hunt Test the file upload, preview, export, and download chain for the current target
```

The root Skill infers the earliest security-relevant semantic divergence, loads one primary internal module, and adds another only when evidence crosses a boundary. Internal modules are ordinary Markdown references, not peer Skills or user-facing slash commands.

## Internal Modules

| Module | Profiles | Scope |
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
├── SKILL.md                 # only discoverable Skill: /security-hunt
├── modules/                 # 7 internal routing modules, loaded as references
│   ├── input.md
│   ├── normalize.md
│   ├── identity.md
│   ├── channels.md
│   ├── state.md
│   ├── crypto.md
│   └── system.md
├── profiles/                # 32 testing Profiles
├── references/              # 32 case-and-mechanism References
└── framework/
    └── verify-evidence.md
```

## Design Constraints

- Keep `/security-hunt` as the only user-facing entry point.
- Keep exactly one discoverable `SKILL.md`; internal routing modules remain ordinary Markdown files.
- Let Claude select the primary module from the earliest security-relevant semantic divergence; do not ask the user to choose a category.
- Do not turn the 32 knowledge modules into peer-level Skills.
- Do not duplicate validation, evidence, state, or reporting rules across modules.
- Do not present tool findings, theoretical chains, or anomalous responses as established vulnerabilities.
- Keep Profiles and References one-to-one, with short and stable names.
