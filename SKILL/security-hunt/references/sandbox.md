# Sandboxes & Containers · Reference


Load on demand after selecting the `sandbox-container-boundary` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## HackerOne Case Index


### 1442118 · Sandbox/container/permission-model boundary bypass
- Value: 9/10; framework-behavior exploitation / cross-component attack chain / authorization bypass.
- Chain: `https://gitlab.com/ec0bb/citest` → sandbox/container/permission-model boundary bypass → security controls and the final execution point disagree about subject, object, state, or input semantics → the isolation boundary is crossed and host or privileged resources become accessible.
- Bypass: Invoke APIs omitted from the permission model or exploit mount, path, file-descriptor, or container-configuration gaps to reach host resources from a restricted environment.
- Defensive anchor: Use deny-by-default across equivalent APIs and system calls; minimize mounts, capabilities, and devices; isolate network and credentials; use separate users/namespaces for host paths; build API-equivalence regression tests for the permission model.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 125027 · Sandbox/container/permission-model boundary bypass
- Value: 8/10; framework-behavior exploitation / cross-component attack chain / XSS.
- Chain: A crafted deep-link expression → sandbox/container/permission-model boundary bypass, combined with browser/template/filter parsing differences → the corresponding trust boundary is crossed → host or privileged resources become accessible.
- Bypass: Use an omitted API, mount/path/file-descriptor gap, or container configuration weakness, then combine it with browser/template/filter parsing differences.
- Defensive anchor: Apply deny-by-default to all equivalent APIs and syscalls; minimize mounts/capabilities/devices; isolate network and credentials; separate host paths by user/namespace; add browser-parsing cross-component regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 0.
- HackerOne reports: 4.
- HackerOne report IDs:
  - 125027, 347296, 1442118, 343726

