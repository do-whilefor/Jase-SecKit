# Shared Protocol State · Reference

Load after selecting the `protocol-cache-state` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### DNS-01-003 Cache: DNS Cache poisoning via malicious Response

- Source URL: https://coredns.io/assets/DNS-01-report.pdf
- Source locator: report p. 5, DNS-01-003.
- Reported boundary:
  - Cure53 reports that CoreDNS checked a response transaction ID but did not
    fully bind the response question and domain to the outstanding query,
    allowing an unrelated record to enter shared cache state.
- Transferable test ideas:
  - Treat a nonce or transaction ID as only one correlation field. Compare the
    full request/response tuple: peer, transport, question name, type, class,
    rewrite state, delegation, and accepted answer relationships.
  - Separate trigger evidence from amplification evidence by reading the cache
    through a fresh, independent resolver client.
- Impact closure:
  - Prove the exact poisoned record, TTL and persistence, later recipients,
    affected names, and security action reached through the cached value.
- Defensive anchor:
  - Strictly match query ID, source endpoint, question section, and name semantics.
  - Minimize caching of additional records.
  - Randomize source ports and IDs and use DNSSEC.
  - Test cache consistency across rewrite/forwarding plugins.
