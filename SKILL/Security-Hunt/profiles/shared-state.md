---
id: protocol-cache-state
group: channels
reference: ../references/shared-state.md
---

# Shared Protocol State

**Use for:** DNS caches, cookie/session stores, proxy caches, client resolver caches, and connection state.

**Misalignment to find:** Protocol responses, cache entries, session state, or parse results lack source, object, and
freshness binding, allowing a malicious participant to contaminate later independent requests.

## Baseline

- Shared state must be bound to source, object, context, and freshness.
- Look for weak matching, missing transaction/source validation, cross-domain writes, incorrect TTLs, or parser-state reuse.
- Focus on one malicious response affecting a later independent trusted request.
- Record the state key, write source, validation fields, TTL/version, and reading consumer.

## Validation Order

1. Identify persistent or shared state that remote input can write.
2. Compare validation at write time with matching conditions at read time.
3. Construct cross-domain, cross-session, out-of-order, stale, and conflicting responses.
4. Verify the contamination through an independent later request.

## Variant Axes

- State key: name, object, source, session, transaction ID, connection
- Write source and validation fields
- TTL, version, freshness, conflict, and eviction
- Reads by later independent requests, other sessions, or other consumers

## Combination Paths

- `cache-variant`: Cache Variants
- `field-injection`: Protocol Field Injection
- `url-address`: URLs & Addresses
