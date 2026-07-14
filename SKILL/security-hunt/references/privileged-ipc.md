# Privileged IPC · Reference

Load after selecting the `privileged-ipc` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### 7asecurity/pentest-report-amneziavpn · AVP-01-011 WP2: Linux/Mac/Win PrivEsc via IPC Design Flaw
- Knowledge value: 9/10; authorization bypass / cross-component attack chain / framework-behavior exploitation.
- Chain: The attacker controls a low-privilege client or local process → sends crafted messages to a privileged IPC interface → the daemon performs file, network, or system operations on its behalf → higher privileges are obtained.
- Bypass: The IPC endpoint is reachable but caller identity is not bound, or the server treats client-supplied paths and commands as trusted data.
- Defensive anchor: Validate peer credentials at the OS level; minimize IPC methods; reauthorize and canonicalize arguments server-side; never let clients select arbitrary paths or commands; execute delegated work in a low-privilege sandbox.
