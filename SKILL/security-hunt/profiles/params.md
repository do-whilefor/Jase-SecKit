---
id: parameter-parser-differential
group: normalize
reference: ../references/params.md
---

# Parameter Parsing

**Use for:** REST APIs, gateways/WAFs, forms/JSON, method override, and signed parameters.

**Misalignment to find:** Gateways, middleware, frameworks, and business code use different rules for duplicate parameters, Query/Body/Header/Cookie precedence, method override, or Content-Type parsing.

## Baseline

- The same logical parameter may appear in multiple locations and have multiple values.
- First/last/array selection, Query/Body precedence, Content-Type parsing, and type conversion can differ.
- Focus on security controls reading value A while business logic reads value B.
- Record the raw request, each layer’s parameter object, the validated value, and the final execution value.

## Validation Order

1. Duplicate security-sensitive parameters and vary their order.
2. Place conflicting values in Query, Body, Header, and Cookie locations.
3. Switch Content-Type, method, and encoding.
4. Record the value actually read by the gateway and the application.
5. Prove the effect through the final object or action.

## Variant Axes

- Location: Query, Body, Header, Cookie, Path
- Duplicate parameters, array/scalar shape, empty values, case, and ordering
- Content-Type, charset, method override, and boundary format
- Precedence in gateway, middleware, framework binder, and business logic

## Combination Paths

- `http-boundary`: HTTP Boundaries
- `object-types`: Objects & Types
- `workflow`: Business State Machines
