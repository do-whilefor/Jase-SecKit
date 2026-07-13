---
name: System Boundaries
description: Low-level values, system calls, file-object identity, resource complexity, sandboxes, and privileged IPC boundaries. Use for authorized testing of values and lifetimes, system calls and options, file-object identity, algorithmic complexity, sandboxes and containers, and privileged IPC.
user-invocable: false
allowed-tools: Read Grep Glob Bash
---

# System Boundaries

## Goal

Trace low-privilege input to the real system object, system call, resource cost, isolation boundary, or privileged service, then determine whether the resulting capability exceeds the design.

## Loading Order

1. Read `${CLAUDE_PLUGIN_ROOT}/framework/verify-evidence.md` first.
2. Choose one or two Profiles based on the entry point, component, and anomaly; do not load every Profile in the group at once.
3. After forming a testable hypothesis, read the matching Reference for additional cases and variants.
4. When a chain crosses boundaries, load material from other groups according to the Profile’s “Combination Paths.”

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| Protocol length fields; memory allocation; indexes/offsets | `value-lifetime` | Values & Lifetimes |
| Kernel syscalls; privileged daemons; CLI wrappers | `syscall-options` | System Calls & Options |
| High-privilege file operations; temporary directories; build workspaces | `fs-identity` | File-Object Identity |
| Regex/replacement; JSON/number parsing; DNSSEC | `complexity` | Algorithmic Complexity |
| Containers/Pods; restricted shells; browser/plugin sandboxes | `sandbox` | Sandboxes & Containers |
| D-Bus; Unix sockets; Windows Named Pipes/COM | `privileged-ipc` | Privileged IPC |

Profile paths are `${CLAUDE_PLUGIN_ROOT}/profiles/<name>.md`; Reference paths are `${CLAUDE_PLUGIN_ROOT}/references/<name>.md`.

## Workflow

1. Determine the real type, handle/inode, caller credentials, system-call arguments, and isolation configuration.
2. Independently test width/sign, path-object replacement, option parsing, resource worst cases, alternate execution paths, and IPC parameters.
3. Validate on the target platform under real privileges; do not substitute source-only inference for runtime results.
4. Prove impact through unauthorized files, processes, network access, permissions, host resources, or measurable resource exhaustion.

## Do Not Stop Here

- Assuming a file object is safe because its path string passed validation.
- Treating “locally reachable” as IPC authorization.
- Producing only a crash without quantifying cost, repeatability, scope, and recovery conditions.

## Output

For each round, record only: Profile used, target object, testing identity, hypothesis, baseline, variant, independent verification, evidence path, current status, and next step or combination path. Mark a finding `confirmed` only when it meets the evidence threshold in the unified framework.
