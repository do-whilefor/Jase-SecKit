# Privileged IPC · Reference


Load on demand after selecting the `privileged-ipc` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### 7asecurity/pentest-report-amneziavpn · AVP-01-011 WP2: Linux/Mac/Win PrivEsc via IPC Design Flaw
- Value: 9/10; authorization bypass / cross-component attack chain / framework-behavior exploitation.
- Chain: The attacker controls a low-privilege client or local process → sends crafted messages to a privileged IPC interface → the daemon performs file, network, or system operations on its behalf → higher privileges are obtained.
- Bypass: The IPC endpoint is reachable but caller identity is not bound, or the server treats client-supplied paths and commands as trusted data.
- Defensive anchor: Validate peer credentials at the OS level; minimize IPC methods; reauthorize and canonicalize arguments server-side; never let clients select arbitrary paths or commands; execute delegated work in a low-privilege sandbox.


## Source Coverage

- Full reports: 1.
- HackerOne reports: 0.
- Full report IDs:
  - 7asecurity/pentest-report-amneziavpn

