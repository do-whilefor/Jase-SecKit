---
id: sandbox-container-boundary
group: system
reference: ../references/sandbox.md
---

# Sandboxes & Containers

**Use for:** containers/Pods, restricted shells, browser/plugin sandboxes, remote code-execution platforms, and BPF/system-call filtering.

**Misalignment to find:** The restricted environment covers only part of the system calls, namespaces, mounts, devices, network, or alternate execution paths, allowing the stated isolation boundary to be bypassed through a combination of gaps.

## Baseline

- Isolation is the intersection of multiple policies; any uncovered path may become an escape channel.
- Look for capability leakage, exposed mounts/devices, alternate system calls, proxy processes, or namespace mismatch.
- Focus on policies that block the expected path while an equivalent capability remains available through another component.
- Record subject credentials, namespaces, capabilities, mounts, devices, system calls, and proxy services.

## Validation Order

1. List the capabilities the sandbox promises to prohibit.
2. Enumerate every direct and proxied path that can provide each capability.
3. Vary system call, file descriptor, protocol, mount, and helper process.
4. Prove the boundary violation through access to host or higher-privilege resources.

## Variant Axes

- Namespaces, mounts, devices, network, capabilities, seccomp, and LSM
- Host-exposed sockets, files, credentials, kernel interfaces, and control planes
- Alternate execution paths, helper binaries, interpreters, and plugins
- Stated isolation scope versus actually reachable resources

## Combination Paths

- `privileged-ipc`: Privileged IPC
- `syscall-options`: System Calls & Options
- `policy-bypass`: Mandatory Policy Bypass
