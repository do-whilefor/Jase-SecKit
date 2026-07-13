---
id: privileged-ipc
group: system
reference: ../references/privileged-ipc.md
---

# Privileged IPC

**Use for:** D-Bus, Unix sockets, Windows Named Pipes/COM, Android Binder, and local HTTP/RPC.

**Misalignment to find:** A low-privilege client invokes a high-privilege daemon through local IPC, RPC, sockets, Binder, D-Bus, or named pipes without tightly constraining the subject, method, arguments, and object capability.

## Baseline

- A privileged service acts on behalf of callers and must re-authenticate them while exposing the minimum capability.
- Look for trust based only on local reachability, missing caller identity, overly broad methods, or attacker-controlled path/command/configuration parameters.
- Focus on low-privilege UI input that a privileged service treats as trusted control data.
- Record connection credentials, caller SID/UID, method, object handle, and final system call.

## Validation Order

1. Enumerate IPC endpoints, methods, and sources of caller identity.
2. Invoke them directly from a low-privilege user or sandboxed process.
3. Substitute paths, commands, configuration, environment, and object IDs.
4. Trace execution to the final privileged system call.
5. Prove unauthorized file, network, process, or privilege impact.

## Variant Axes

- Endpoint: D-Bus, Unix socket, Named Pipe, COM, Binder, local RPC
- Caller identity: UID/GID, SID, peer credentials, signature, and session
- Method capability, object handle, path, command, configuration, and environment
- Complete path from low-privilege input to the final privileged system call

## Combination Paths

- `syscall-options`: System Calls & Options
- `sandbox`: Sandboxes & Containers
- `fs-identity`: File-Object Identity
