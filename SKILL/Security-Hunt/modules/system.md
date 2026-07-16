# System Boundaries

## Goal

Trace low-privilege input to the real system object, system call, resource cost, isolation boundary, or privileged
service, then determine whether the resulting capability exceeds the design.

## Route Here When

Use this module as primary when the decisive failure depends on a real system object, system call, native value, resource cost, isolation boundary, or privileged IPC service.

Choose the narrower module when the decisive boundary is elsewhere:

- Prefer `input/file-chain` for cross-stage reinterpretation.
- Prefer `normalize/path` for canonicalization differences.
- Prefer `state/race` for timing-window failures.
- Use `fs-identity` when validation and use refer to different inode, handle, descriptor, or filesystem object.

## Compatibility

Effective validation may require the target operating system, compiler/runtime, sanitizer or tracer, container
runtime, IPC tooling, and real privilege context. Return `NEED_INPUT` only after
viable platform and observation alternatives have been tried and the missing
capability is recorded.

## Routing

| Trigger | Profile | Focus |
|---|---|---|
| Protocol length fields; memory allocation; indexes/offsets | `value-lifetime` | Values & Lifetimes |
| Kernel syscalls; privileged daemons; CLI wrappers | `syscall-options` | System Calls & Options |
| High-privilege file operations; temporary directories; build workspaces | `fs-identity` | File-Object Identity |
| Regex/replacement; JSON/number parsing; DNSSEC | `complexity` | Algorithmic Complexity |
| Containers/Pods; restricted shells; browser/plugin sandboxes | `sandbox` | Sandboxes & Containers |
| D-Bus; Unix sockets; Windows Named Pipes/COM | `privileged-ipc` | Privileged IPC |

## Workflow

1. Determine the real type, handle/inode, caller credentials, system-call arguments, and isolation configuration.
2. Independently test width/sign, path-object replacement, option parsing, resource worst cases, alternate execution paths, and IPC parameters.
3. Validate on the target platform under real privileges; do not substitute source-only inference for runtime results.
4. Prove impact through unauthorized files, processes, network access, permissions, host resources, or measurable resource exhaustion.

## Do Not Stop Here

- Assuming a file object is safe because its path string passed validation.
- Treating “locally reachable” as IPC authorization.
- Producing only a crash without quantifying cost, repeatability, scope, and recovery conditions.
