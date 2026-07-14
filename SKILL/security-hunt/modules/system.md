# System Boundaries

## Goal

Trace low-privilege input to the real system object, system call, resource cost, isolation boundary, or privileged service, then determine whether the resulting capability exceeds the design.

## Primary Boundary

Use this module as primary when the decisive failure depends on a real system object, system call, native value, resource cost, isolation boundary, or privileged IPC service. Prefer `input/file-chain` for cross-stage reinterpretation, `normalize/path` for canonicalization differences, and `state/race` for timing-window failures. Use `fs-identity` when validation and use refer to different inode, handle, descriptor, or filesystem object.

## Compatibility

Effective validation may require the target operating system, compiler/runtime, sanitizer or tracer, container runtime, IPC tooling, and real privilege context. Use `blocked` only under the framework rule after viable platform and observation alternatives have been tried.

## Loading Order

1. Read `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md` first.
2. Load the Profiles needed for the concrete hypothesis; keep plausible adjacent and combination paths queued, and add them whenever evidence, gaps, or downstream consumers require it.
3. Establish a baseline before reading matching References for additional variants. Progressive loading limits context use, not testing breadth or depth.

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| Protocol length fields; memory allocation; indexes/offsets | `value-lifetime` | Values & Lifetimes |
| Kernel syscalls; privileged daemons; CLI wrappers | `syscall-options` | System Calls & Options |
| High-privilege file operations; temporary directories; build workspaces | `fs-identity` | File-Object Identity |
| Regex/replacement; JSON/number parsing; DNSSEC | `complexity` | Algorithmic Complexity |
| Containers/Pods; restricted shells; browser/plugin sandboxes | `sandbox` | Sandboxes & Containers |
| D-Bus; Unix sockets; Windows Named Pipes/COM | `privileged-ipc` | Privileged IPC |

Profile paths are `${CLAUDE_SKILL_DIR}/profiles/<name>.md`; Reference paths are `${CLAUDE_SKILL_DIR}/references/<name>.md`.

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

Record each round with the complete status, blackboard, evidence, impact-validation, severity-gate, blind-spot, and closure rules in `${CLAUDE_SKILL_DIR}/framework/verify-evidence.md`; do not replace them with a reduced local schema.
