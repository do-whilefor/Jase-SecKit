---
id: server-interpreter-injection
group: input
reference: ../references/server-interpreters.md
---

# Server Interpreters

**Use for:** SQL/NoSQL/LDAP/XPath injection, server-side template injection, expression languages, query DSLs, search
filters, policy expressions, and dynamically constructed commands or code.

**Misalignment to find:** An application treats attacker-controlled input as data while a downstream interpreter
reparses part of it as query structure, template syntax, expression logic, or executable control content.

## Baseline

- Input validation at the HTTP layer does not prove safe construction at the final interpreter.
- Parameterization must cover the exact interpreter and every structural element that can be attacker-controlled.
- Escaping for one grammar or context is not valid for another grammar or a later reparsing stage.
- Record the raw input, normalized value, query/template/expression construction, interpreter, execution identity, and final effect.

## Validation Order

1. Identify the final interpreter, grammar, construction API, and data/control boundary.
2. Establish a benign baseline and use syntax-neutral controls before testing grammar-specific variants.
3. Vary quoting, operators, nesting, type coercion, field names, sort/projection expressions, template contexts, and alternate parameter locations.
4. Confirm the result through changed query semantics, returned objects, server-side state, timing, logs, or another independent signal.
5. Separate interpreter control from any downstream file, network, command, or code-execution impact and validate each segment independently.

## Variant Axes

- Interpreter: SQL, NoSQL, LDAP, XPath/XQuery, template, expression language, search/query DSL, policy engine
- Context: value, identifier, field name, operator, sort, projection, fragment, template expression, function call
- Representation: string, number, boolean, null, array, object, duplicate key, encoded form
- Consumer: primary query, ORM, search service, report builder, background job, export, notification, policy engine

## Combination Paths

- `params`: Parameter Parsing
- `object-types`: Objects & Types
- `object-authorization`: Object Authorization
- `tenant-isolation`: Tenant Isolation
- `field-injection`: Protocol Field Injection
- `workflow`: Business State Machines
- `syscall-options`: System Calls & Options
