# Sandboxes & Containers · Reference

Load after selecting the `sandbox-container-boundary` Profile and forming a current-target hypothesis.

## Use Rule

- Use hardening sources to enumerate isolation assumptions, not to infer escape or host impact from one misconfiguration.
- Validate the real runtime, identity, capabilities, mounts, devices, namespaces, and network paths.
- Prove each boundary crossing and host-level effect independently.

## Curated Sources

### OWASP Docker Security Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html
- Transferable test ideas:
  - Inspect privilege mode, capabilities, user identity, daemon socket exposure, mounts, devices, seccomp, namespaces, and host paths.
  - Compare intended restrictions with the effective runtime configuration and reachable host resources.
- Defensive anchor:
  - Run as a non-root user, drop unnecessary capabilities, avoid privileged mode, and protect the container runtime socket.

### OWASP Kubernetes Security Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/Kubernetes_Security_Cheat_Sheet.html
- Transferable test ideas:
  - Trace service-account permissions, pod security settings, host namespaces, volumes, admission controls, and network policy.
  - Verify whether a pod identity can reach cluster or host capabilities beyond its intended workload scope.
- Defensive anchor:
  - Apply least privilege to workloads and service accounts, enforce pod security, and isolate network and host resources.
