<h1 align="center">Jase-SecKit</h1>

<p align="center">A collection of Skills, constraint files, Prompts and MCP configurations for authorized bug bounty, security research and AI-assisted penetration testing.</p>

<p align="center">
  <a href="#usage-boundaries"><img src="https://img.shields.io/badge/Scope-Authorized%20Security%20Research-blue" alt="Scope: Authorized Security Research"></a>
  <a href="#repository-contents"><img src="https://img.shields.io/badge/Skills-Claude%20Code%20%7C%20Codex-6f42c1" alt="Skills: Claude Code and Codex"></a>
  <a href="#mcp-and-browser-configuration"><img src="https://img.shields.io/badge/MCP-Burp%20%7C%20Chrome-success" alt="MCP: Burp and Chrome"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow" alt="License: MIT"></a>
</p>

<p align="center"><a href="README.md">简体中文</a> | English | <a href="README_JA.md">日本語</a></p>

`Jase-SecKit` is a personal repository for bug bounty, authorized web security testing and AI-assisted vulnerability research.

This repository reorganizes, streamlines, translates and re-engineers bug bounty Skills and security research materials: removing duplicated or low-value content, dropping redundant modules for automated Word report generation, unifying Skill content in English, while adding global behavioral constraints, state-file mechanisms, Prompts, and usage configurations for Burp MCP and Chrome DevTools MCP.

---

## Core Principles

> Explore broadly, verify strictly. No vulnerability is confirmed without complete evidence.

This repository emphasizes the following principles:

- Server-side authentication, authorization, object ownership, tenant isolation, state transitions and business rules are the primary security boundaries.
- Static analysis, scanner results, error messages, code patterns and historical cases can only generate leads; they cannot replace dynamic verification.
- A technical hit does not equal a valid vulnerability; you must further verify the capability obtained, affected objects, data or assets, business impact, scope and preconditions.
- Use files to persist state and evidence, so the model does not rely on in-context memory alone — repeating tests, skipping tests, or fabricating conclusions.
- Skills are for guidance; they should not limit the model's autonomous exploration and unconventional verification on unknown paths.
- All testing is restricted to legal, explicitly authorized and controllable environments.

## What This Repository Provides

### 1. Global Agent Constraints

`约束文件/AGENTS.md` (Chinese) and `约束文件/CLAUDE.md` (English) provide global security testing constraints.

The constraint files are used to:

- Define authorized targets, assets, interfaces, accounts and testing scope.
- Constrain unauthorized scanning, destructive verification, persistence, lateral movement and resource exhaustion.
- Enforce the distinction between leads, technical hits, harm verification and final vulnerability conclusions.
- Prevent the model from writing tool alerts, HTTP 200s, anomalous responses or theoretical attack chains as confirmed vulnerabilities.
- Require the model to read and update `state/blackboard.md`, using files as the source of task state rather than relying on memory to invent or rebuild the blackboard.
- Use explicit terminal states for verified, unreproduced, low-value and input-missing branches, making recovery, review and continued testing easier.

### 2. MCP and Client Configurations

The `设置/` directory contains configuration references for clients such as Claude Code, Codex and ZCode, focusing on integrating:

- Burp MCP: reading proxy history, building and replaying requests, inspecting request/response pairs, and supporting dynamic verification.
- Chrome DevTools MCP: browser session reuse, page operations, network request analysis, console inspection, performance profiling, memory debugging and experimental DevTools capabilities.

These configurations are not universal plug-and-play files. Before use, check local paths, MCP service addresses, client versions and supported parameters, and replace placeholder paths in the examples with actual absolute paths.

### 3. Bug Bounty Prompts

The root-level `Prompt.md` consists of two parts:

- The first half: deep vulnerability discovery and dynamic reproduction prompts for local open-source projects, training ranges and authorized targets, suited for more autonomous models such as DeepSeek, Kimi, GLM, etc.
- The second half: website architecture, JavaScript, interface, state-flow and runtime-mechanism analysis prompts for Codex / GPT-5.6.

Prompts work best as phase-specific guidance. Use them together with the global constraint file, and require conclusions to carry verifiable evidence: code locations, interface paths, parameters, response fields, call relationships, network records, etc.

### 4. Methodology Reference Materials

The repository keeps three reference materials related to AI vulnerability-hunting agent design:

- `AI辅助漏洞挖掘系统设计指南.pdf`
- `围绕Loop的AI SRC系统设计.pptx`
- `客户端漏洞挖掘 Agent 的设计与实践.md`

These materials can be used to distill a unified vulnerability-hunting Skill — for example, merging their Loop, state management, dynamic verification, evidence auditing, blind-spot review and agent orchestration methods into a lighter entry Skill.

These files are reference or borrowed material. The original authors' rights, original licenses and source attributions are not changed by this repository's MIT License.

## Repository Contents

```text
Jase-SecKit/
├── SKILL/
│   ├── Web-Vulnhunt/                # Autonomous web pentest, state files and dynamic verification workflow
│   ├── flounder/                    # Code audit Skill
│   └── src-report/                  # Vulnerability report writing Skill
├── refer/
│   ├── ARTEX-main/                  # ARTEX reference project
│   ├── Cairn-main/                  # Cairn reference project
│   └── sapper-v2-master/            # sapper-v2 multi-agent autonomous pentest reference project
├── 约束文件/ (constraints/)
│   ├── AGENTS.md                    # Chinese global Agent constraints
│   ├── CLAUDE.md                    # English global Agent constraints
│   └── state/                       # Blackboard and state file templates
├── 设置/ (settings/)
│   ├── ASC_MCP/                     # ASC MCP server configuration and scripts
│   ├── claude-code/                 # Claude Code MCP and runtime settings
│   ├── codex/                       # Codex configuration and instruction files
│   ├── rules/                       # Client rule configurations
│   ├── zcode/                       # ZCode configuration
│   └── 注册Chrome-CLI.md            # Chrome CLI registration notes
├── Prompt.md                        # Vulnerability hunting and site architecture analysis Prompt
├── 常见漏洞.md                      # Common vulnerability directions and research references
├── AI辅助漏洞挖掘系统设计指南.pdf
├── 围绕Loop的AI SRC系统设计.pptx
├── 客户端漏洞挖掘 Agent 的设计与实践.md
├── README.md
├── README_EN.md
├── README_JA.md
├── SECURITY.md
└── LICENSE
```

## Global Constraints and the Blackboard Mechanism

- Global constraints define what is allowed, when a vulnerability can be confirmed, how state is persisted and when a branch terminates.
- Prompts steer the model's focus and reasoning direction based on the current target.
- MCP provides real browser and HTTP interaction capabilities.

The recommended basic loop:

```text
Read the blackboard
  → Build the exposure surface and object relationships
  → Generate and prioritize verification intents
  → Dynamically verify security boundaries
  → Mark technical hits
  → Verify real-world harm
  → Guardian review
  → Rate severity or enter an explicit terminal state
  → Update the blackboard
```

The blackboard stores only what is needed for task recovery, deduplication and evidence closure — not full thought processes — and the model must not fabricate it independently of existing state files.

## MCP and Browser Configuration

### Burp MCP

An example Claude Code configuration is located at:

```text
设置/claude-code/managed-mcp.json
```

Before use, modify:

```json
"command": "<absolute path>\\java.exe"
```

and:

```json
"<absolute path>\\mcp-proxy.jar"
```

By default the example connects to the Burp MCP service at:

```text
http://127.0.0.1:9876
```

Ensure the Burp-side extension, proxy program and local port are properly started.

### Chrome DevTools MCP

The current configuration focuses on enabling Chrome DevTools MCP capabilities for browser, network, experimental DevTools, visual, structured content, all pages, memory debugging, third-party tools and WebMCP.

Key parameter:

```json
"--autoConnect"
```

This attempts to automatically connect to a running, compatible Chrome instance on the machine. Where Chrome remote debugging policy and the local environment allow, it can reuse existing browser configuration, login state and cookies — suitable for analyzing pages directly within an existing authorized session.

When an isolated session is needed, remove `--autoConnect` and configure a dedicated user data directory or browser profile for the launched/connected Chrome. Removing the parameter alone does not guarantee every client will automatically create an isolated environment; actual behavior depends on the MCP client and how Chrome is started.

The configuration also uses:

```json
"--channel=stable"
```

This selects the Chrome Stable channel; it is not a scanning parameter.

Some `--experimental-*` parameters may change with Chrome DevTools MCP versions. After upgrading, refer to the official parameter documentation for the current version; when startup fails, remove experimental parameters one by one to isolate the cause.

## How to Use

### 1. Configure Global Constraints

Choose according to your client:

- Codex or environments supporting `AGENTS.md`: use `约束文件/AGENTS.md`.
- Claude Code: use `约束文件/CLAUDE.md`, or merge into an existing project constraint file as needed.

Do not blindly overwrite existing global rules. Check for conflicts before merging, and ensure the authorization scope, state file paths and tool permissions match your actual environment.

### 2. Configure MCP

Pick the configuration for your client from `设置/` as a reference, replace local paths and service addresses, then verify:

- Whether the MCP service starts successfully.
- Whether Burp can read or create test requests.
- Whether Chrome connects to the expected browser instance.
- Whether the current browser session is a reused or isolated session.
- Whether experimental parameters are supported by the current version.

### 3. Use the Prompt

Do not apply `Prompt.md` verbatim to every target. Replace the target, scope, environment, accounts, prohibitions and expected output per task, and use it together with the global constraints.

When a model is told it "must find several Critical vulnerabilities", it may develop confirmation bias. In practice: vulnerability counts and severity cannot be preset — only report issues that have been dynamically verified with a closed harm loop.

## Recommended Working Method

1. Define the target, accounts, allowed assets and exclusions.
2. Read the global constraints and the existing blackboard.
3. Analyze directories, frameworks, dependencies, configuration, JS, interfaces and object relationships.
4. Model subjects, entry points, objects, relationships, actions, states and trust fields.
5. Use Prompts to guide the current phase rather than fixing the entire process up front.
6. Use Chrome MCP to reconstruct real pages and call chains; use Burp MCP to verify server-side boundaries.
7. Mark tool hits as leads or technical hits — do not immediately write them up as vulnerabilities.
8. Compare across different identities, objects, tenants, entry points, states and request forms.
9. For confirmed issues, save reproducible evidence: requests, responses, state changes, logs, files, etc.
10. Complete independent review, blind-spot checks, deduplication and severity rating.

## Personal View on Skills

At a stage of rapidly improving LLM capability, a realistic question is: do Skills still matter? Are models already strong enough on their own? Could Skills actually constrain models?

LLMs already have strong code understanding, tool calling, attack surface analysis and autonomous reasoning. Skills are not useless, but overly detailed, procedural, checklist-style Skills may indeed constrain a model's divergent thinking, making it follow a fixed pipeline step by step.

Bug bounty is not a known path. The start and goal may be clear, but the path in between is often unknown. Truly valuable vulnerabilities often come from anomalous states, business-logic combinations, cross-module relationships, legacy compatibility logic, parsing discrepancies or developer-unintended interactions. These paths require the model to keep autonomous reasoning, association and exploration — not to be boxed into a preset checklist by a fixed Skill.

But Skills still have value. They can tell the model how to start, which security boundaries to focus on, how to record state, how to verify harm, how to judge whether evidence is sufficient, and how to avoid omissions. For weaker models that converge prematurely or lack security testing experience, well-designed Skills can significantly improve hunting quality.

What matters more now is the Prompting process: continuously adjusting prompts based on the current phase, known evidence and your own judgment, letting the model dig deeper along actual findings instead of always running one fixed process. Skills serve as base framework, knowledge index and omission guard; Prompts handle phase guidance; the model itself handles divergent thinking on unknown paths.

In the future, the importance of Skills may continue to decline; the core differentiator will be the model's own reasoning ability, tool capability, context management and dynamic verification. Rather than piling on more process constraints, it matters more to establish clear, stable, non-overreaching behavioral boundaries for the model — and to require all conclusions to return to real evidence.

## Usage Boundaries

This repository is only for:

- Explicitly authorized bug bounty and SRC testing scopes.
- User-owned systems, test environments, labs, or locally deployed open-source projects.
- CTF, training ranges, security courses and defensive research.
- Authorized code audits, interface testing, browser analysis and vulnerability reproduction.

Prohibited uses:

- Unauthorized scanning, probing, intrusion or exploitation of third-party systems.
- DoS, DDoS, sustained stress testing, resource exhaustion or actions affecting business availability.
- Deleting, destroying or irreversibly modifying real business data.
- Establishing WebShells, backdoors, scheduled tasks, startup items, reverse shells or other persistent access.
- Lateral movement, attacking unrelated assets, credential theft, phishing, credential stuffing or social engineering.
- Performing real payments, refunds, permission changes, mass notifications or other high-impact business operations on non-test accounts.
- Actions violating applicable laws, platform rules, bug bounty policies, SRC rules or explicit restrictions from the target party.

## Disclaimer

The Skills, Prompts, rules, configurations, scripts and documents in this repository are for legally authorized security research, education, code auditing and test environments only.

Users must confirm they hold sufficient authorization, and bear full responsibility for target scope, testing methods, tool configuration, data processing, evidence preservation, vulnerability submission and subsequent impact. The repository author is not liable for any unauthorized use, misconfiguration, data loss, business interruption, legal liability, third-party claims or other direct or indirect losses.

This repository does not guarantee that vulnerabilities will be found, nor their quantity or severity, nor that AI outputs, tool results, configuration parameters, attack ideas or vulnerability conclusions are always correct, complete, applicable to specific environments or compliant with specific platform rules. All conclusions should be independently verified by qualified testers.

Third-party materials, cases, documents and code referenced, included or adapted in this repository remain under the copyright and licenses of their original authors or rights holders. The root MIT License applies only to original or modified content the repository author has the right to license; third-party materials follow their own licenses, attribution and usage terms.

## License

Original and modified content in this repository that the author has the right to license is released under the [MIT License](LICENSE).
