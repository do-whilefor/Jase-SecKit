# Mandatory Policy Bypass · Reference


Load on demand after selecting the `mandatory-policy-alternate-path` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### cure53/pentest-report metamask · MM-01-002 Extension: Phishing Detector can be bypassed
- Value: 10/10; protocol-behavior exploitation / cross-component attack chain.
- Chain: An attacker or malicious content triggers a special URL, protocol, redirect, or session path → the request bypasses VPN/Tor/certificate or audit mediation → real network identity is exposed, a forged endpoint is accepted, or an action is left unrecorded.
- Bypass: Platform helpers, protocol downgrade, redirects, races, or bypass clients make a secure default path differ from universal policy enforcement.
- Defensive anchor: Centralize non-bypassable egress and certificate policy; disable plaintext and alternate paths; test every URL scheme, redirect, and subprocess end to end; generate audit records at a trusted server-side boundary.

### cure53/pentest-report smartsheriff-2 · SMS-02-007 Possible Remote Code Execution via MitM in WebView
- Value: 8/10; command injection / protocol-behavior exploitation / cross-component attack chain.
- Chain: The attacker performs a network MITM → modifies plaintext downloads, configuration, or control responses → the client/service treats the content as a trusted script, component, or policy → code execution, identity spoofing, or persistent impact.
- Bypass: Missing endpoint authentication at the transport layer lets a downstream executor inherit a false assumption that the content came from a trusted source.
- Defensive anchor: Require HTTPS/TLS with correct certificate validation; additionally verify executable content with signatures or hashes; separate download and execution privileges; never fall back to plaintext after failure.


## Source Coverage

- Full reports: 8.
- HackerOne reports: 0.
- Full report IDs:
  - cure53/pentest-report metamask
  - cure53/pentest-report onion-browser
  - cure53/pentest-report teleport
  - cure53/pentest-report whiteout
  - doyensec/Doyensec Gravitational Teleport FeaturesTesting Q42021
  - doyensec/Doyensec Gravitational Teleport Testing Q22019
  - isec-partners/iSEC Cryptocat iOS
  - cure53/pentest-report smartsheriff-2

