# Mandatory Policy Bypass · Reference

Load after selecting the `mandatory-policy-alternate-path` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### cure53/pentest-report metamask · MM-01-002 Extension: Phishing Detector can be bypassed
- Knowledge value: 10/10; protocol-behavior exploitation / cross-component attack chain.
- Chain: An attacker or malicious content triggers a special URL, protocol, redirect, or session path → the request bypasses VPN/Tor/certificate or audit mediation → real network identity is exposed, a forged endpoint is accepted, or an action is left unrecorded.
- Bypass: Platform helpers, protocol downgrade, redirects, races, or bypass clients make a secure default path differ from universal policy enforcement.
- Defensive anchor: Centralize non-bypassable egress and certificate policy; disable plaintext and alternate paths; test every URL scheme, redirect, and subprocess end to end; generate audit records at a trusted server-side boundary.

### cure53/pentest-report smartsheriff-2 · SMS-02-007 Possible Remote Code Execution via MitM in WebView
- Knowledge value: 8/10; command injection / protocol-behavior exploitation / cross-component attack chain.
- Chain: The attacker performs a network MITM → modifies plaintext downloads, configuration, or control responses → the client/service treats the content as a trusted script, component, or policy → code execution, identity spoofing, or persistent impact.
- Bypass: Missing endpoint authentication at the transport layer lets a downstream executor inherit a false assumption that the content came from a trusted source.
- Defensive anchor: Require HTTPS/TLS with correct certificate validation; additionally verify executable content with signatures or hashes; separate download and execution privileges; never fall back to plaintext after failure.
