# Offline Verifiers · Reference

Load after selecting the `offline-verifier-exposure` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### singlepointofcontact/SPoC Penetration-Test · 2. IPMI v2.0 Password Hash Disclosure
- Knowledge value: 6/10; information disclosure / protocol-behavior exploitation.
- Chain: The attacker initiates an authentication handshake → obtains a password hash or challenge-response material → performs high-speed offline guessing → logs in to the management interface with recovered credentials.
- Bypass: The protocol reveals a password proof that can be checked offline before authentication, bypassing online rate limits and lockout policy.
- Defensive anchor: Upgrade or disable the affected protocol; use strong unique passwords and network isolation; prefer PAKE or certificate authentication resistant to offline guessing; monitor anomalous handshakes.
