# Proxies & Origins · Reference

Load after selecting the `host-origin-proxy-trust` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## HackerOne Case Index

### 226659 · Host/Origin/reverse-proxy trust-boundary mismatch
- Knowledge value: 9/10; authentication bypass / protocol-behavior exploitation / authorization bypass.
- Chain: `http://www.skeletonscribe.net/2013/05/practical-http-host-header-attacks.html` → Host/Origin/reverse-proxy trust-boundary mismatch → security controls and the final execution point disagree about subject, object, state, or input semantics → account takeover.
- Bypass: Modify Host, Origin, Referer, or Forwarded-family headers, or exploit boundary-matching and proxy-rewrite differences to influence security decisions.
- Defensive anchor: Use a fixed server-side base URL for security-sensitive absolute links; accept proxy headers only from trusted upstreams; perform exact structured Origin/Host matching with port and IDN normalization; prohibit substring and loose suffix checks.
