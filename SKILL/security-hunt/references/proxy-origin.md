# Proxies & Origins · Reference


Load on demand after selecting the `host-origin-proxy-trust` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## HackerOne Case Index


### 226659 · Host/Origin/reverse-proxy trust-boundary mismatch
- Value: 9/10; authentication bypass / protocol-behavior exploitation / authorization bypass.
- Chain: `http://www.skeletonscribe.net/2013/05/practical-http-host-header-attacks.html` → Host/Origin/reverse-proxy trust-boundary mismatch → security controls and the final execution point disagree about subject, object, state, or input semantics → account takeover.
- Bypass: Modify Host, Origin, Referer, or Forwarded-family headers, or exploit boundary-matching and proxy-rewrite differences to influence security decisions.
- Defensive anchor: Use a fixed server-side base URL for security-sensitive absolute links; accept proxy headers only from trusted upstreams; perform exact structured Origin/Host matching with port and IDN normalization; prohibit substring and loose suffix checks.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 0.
- HackerOne reports: 7.
- HackerOne report IDs:
  - 1108874, 226659, 1188471, 229498, 1072277, 1848730, 94637

