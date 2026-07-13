---
id: mandatory-policy-alternate-path
group: state
reference: ../references/policy-bypass.md
---

# Mandatory Policy Bypass

**Use for:** forced VPN/Tor egress, TLS/certificate validation, zero-trust proxies, session recording/auditing, and restricted sessions.

**Misalignment to find:** The system claims to enforce VPN/Tor/TLS/certificate/audit/session restrictions, but alternate protocols, redirects, races, system integrations, or uncovered paths bypass the policy.

## Baseline

- A mandatory policy must cover every equivalent path and lifecycle stage.
- Look for alternate protocols, system URL handlers, redirects, races, proxy bypass, unrecorded commands, or policy-installation timing gaps.
- Focus on a controlled primary path while the same capability remains available through an uncovered path.
- Record the security promise, every egress/execution path, policy activation timing, and final network/audit evidence.

## Validation Order

1. Rewrite the security promise as a testable invariant.
2. Enumerate protocols, system integrations, background jobs, redirects, and race paths.
3. Test coverage during startup, switching, recovery, and error states.
4. Prove impact through the real egress path, certificate acceptance, unrecorded action, or unauthorized session.

## Variant Axes

- Stated mandatory policy versus actual coverage
- Primary path, alternate protocol, legacy entry point, system integration, and failure fallback
- Redirects, races, startup phase, network switching, and recovery flow
- Actual traffic, audit records, and final execution path before and after policy application

## Combination Paths

- `workflow`: Business State Machines
- `sandbox`: Sandboxes & Containers
- `auth-state`: Authentication State
