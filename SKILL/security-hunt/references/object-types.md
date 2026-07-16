# Objects & Types · Reference

Load after selecting the `deserialization-type-system` Profile and forming a current-target hypothesis.

## Use Rule

- Use these sources to expand object-construction, type-restoration, and automatic-binding hypotheses.
- Do not infer exploitability from the presence of serialization metadata, framework binders, or a theoretical gadget.
- Verify the final object type, property changes, dispatch path, and downstream effect.

## Curated Sources

### OWASP Deserialization Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html
- Transferable test ideas:
  - Identify general-purpose deserializers, polymorphic type metadata, native object formats, and cross-language conversions.
  - Test explicit allowlists, type confusion, unexpected classes, constructor or hook behavior, and post-deserialization use.
  - Separate parser acceptance from reachable side effects and final privileges.
- Defensive anchor:
  - Prefer simple typed data formats with explicit schemas and narrow type allowlists.
  - Avoid general-purpose native object deserialization for untrusted input.

### OWASP Mass Assignment Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
- Transferable test ideas:
  - Compare documented fields with hidden, nested, inherited, and framework-generated object properties.
  - Test create and update binders independently because they may expose different fields.
- Defensive anchor:
  - Use dedicated request models and explicit allowlists for bindable properties.
