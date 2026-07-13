---
id: prototype-pollution
group: input
reference: ../references/prototype.md
---

# Prototype Pollution

**Use for:** deep merge/filtering, object-path assignment, configuration override, JSON parameters, and plugin/template systems.

**Misalignment to find:** Generic object merge, filtering, or path assignment writes attacker-controlled properties into the prototype chain, and inherited values later affect authorization, queries, templates, or execution in a different module.

## Baseline

- Inherited properties appear on objects where they were never explicitly defined.
- `__proto__`, `constructor`, `prototype`, or equivalent paths can modify a shared prototype.
- Focus on writes in a low-risk module followed by reads in a high-privilege module.
- Record the polluted key, prototype object, pollution lifetime, gadget read point, and final sink.

## Validation Order

1. Identify recursive merge, set-by-path, and filtering functions.
2. Verify whether newly created objects inherit the polluted property.
3. Search for implicit reads of security-sensitive properties.
4. Test persistence and gadgets across requests and modules.
5. Prove impact through authorization, queries, templates, commands, or DoS.

## Variant Axes

- Write key: `__proto__`, `constructor`, `prototype`, and path variants
- Write primitive: deep copy, merge, set-by-path, filter
- Pollution scope: single object, request-local, process-wide, persistent
- Gadget: authorization defaults, query, template, command, request option

## Combination Paths

- `object-types`: Objects & Types
- `workflow`: Business State Machines
- `syscall-options`: System Calls & Options
