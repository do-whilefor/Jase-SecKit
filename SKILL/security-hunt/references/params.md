# Parameter Parsing · Reference

Load after selecting the `parameter-parser-differential` Profile and forming a current-target hypothesis.

## Use Rule

- Use these sources to identify ambiguity in duplicate values, locations, methods, content types, and binders.
- Preserve the raw request and the value selected by each layer.
- Prove that the disagreement changes the final object, authorization decision, or action.

## Curated Sources

### OWASP WSTG · Testing for HTTP Parameter Pollution

- Source URL: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/07-Input_Validation_Testing/04-Testing_for_HTTP_Parameter_Pollution
- Transferable test ideas:
  - Duplicate security-sensitive parameters and vary their order, location, encoding, array form, and content type.
  - Compare CDN, WAF, gateway, framework, binder, and business-logic selection rules.
  - Use single-variable controls to distinguish parser behavior from backend instability.
- Defensive anchor:
  - Reject ambiguous duplicates and cross-location conflicts for security-sensitive fields.
  - Parse once into one typed object shared by validation and execution.

### OWASP Mass Assignment Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
- Transferable test ideas:
  - Test undocumented, nested, and privilege-bearing fields accepted by automatic binders.
  - Compare create, patch, bulk, import, and administrative endpoints.
- Defensive anchor:
  - Bind only explicitly allowed fields and apply authorization to each sensitive property.
