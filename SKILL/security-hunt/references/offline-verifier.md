# Offline Verifiers · Reference


Load on demand after selecting the `offline-verifier-exposure` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### singlepointofcontact/SPoC Penetration-Test · 2. IPMI v2.0 Password Hash Disclosure
- Value: 6/10; information disclosure / protocol-behavior exploitation.
- Chain: The attacker initiates an authentication handshake → obtains a password hash or challenge-response material → performs high-speed offline guessing → logs in to the management interface with recovered credentials.
- Bypass: The protocol reveals a password proof that can be checked offline before authentication, bypassing online rate limits and lockout policy.
- Defensive anchor: Upgrade or disable the affected protocol; use strong unique passwords and network isolation; prefer PAKE or certificate authentication resistant to offline guessing; monitor anomalous handshakes.


## Source Coverage

- Full reports: 1.
- HackerOne reports: 0.
- Full report IDs:
  - singlepointofcontact/SPoC Penetration-Test

