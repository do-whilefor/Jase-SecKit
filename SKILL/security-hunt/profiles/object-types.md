---
id: deserialization-type-system
group: input
reference: ../references/object-types.md
---

# Objects & Types

**Use for:** polymorphic deserialization, object merge/deep copy, automatic parameter binding, message queues/RPC, and dynamic-language type conversion.

**Misalignment to find:** After deserialization, object merging, type conversion, or dynamic dispatch, input forms an unintended object graph, runtime type, or execution path.

## Baseline

- Fields in a wire format may be restored as runtime types, prototypes, or object relationships.
- Type markers, setters, constructors, magic methods, prototype chains, or implicit conversions can trigger side effects.
- Focus on validation of surface fields while execution depends on the restored runtime type and object graph.
- Record pre-deserialization bytes, the canonical object, runtime type, and dispatch target.

## Validation Order

1. When input can affect a type, class name, prototype, or nested structure, enumerate the allowed runtime objects.
2. When validation occurs before binding, compare values and types before and after binding.
3. When the object enters template, query, command, authorization, or cache logic, trace cross-module effects.
4. Close the evidence chain through type readback, call traces, or the final side effect.

## Variant Axes

- Entry format and Content-Type
- Type markers, class names, dynamic dispatch, and implicit conversion
- Nesting depth, object merge, defaults, and unknown fields
- Post-construction callbacks, getters, templates, queries, or execution gadgets

## Combination Paths

- `prototype`: Prototype Pollution
- `params`: Parameter Parsing
- `workflow`: Business State Machines
