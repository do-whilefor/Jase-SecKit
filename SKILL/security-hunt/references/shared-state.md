# Shared Protocol State · Reference

Load after selecting the `protocol-cache-state` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### DNS-01-003 Cache: DNS Cache poisoning via malicious Response

- Source: `cure53/pentest-report CoreDNS`
- Reported focus: DNS-01-003 Cache: DNS Cache poisoning via malicious Response
- Transferable test ideas:
  - Weak query/response association, name rewriting, additional records, or incomplete cache-key semantics lets records unrelated to the original query inherit trusted cache state.
- Defensive anchor:
  - Strictly match query ID, source endpoint, question section, and name semantics.
  - Minimize caching of additional records.
  - Randomize source ports and IDs and use DNSSEC.
  - Test cache consistency across rewrite/forwarding plugins.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
