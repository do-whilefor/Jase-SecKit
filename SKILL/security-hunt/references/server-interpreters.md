# Server Interpreters · Reference

Load after selecting the `server-interpreter-injection` Profile and forming a current-target hypothesis.

## Use Rule

- Use these sources to identify data/control boundaries at the final interpreter.
- Do not infer successful injection from errors, reflection, or one changed response.
- Validate changed interpreter semantics and every downstream impact independently.

## Curated Sources

### OWASP SQL Injection Prevention Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- Transferable test ideas:
  - Determine whether values are parameterized at the final query API.
  - Test structural positions such as identifiers, sort fields, operators, projections, and dynamically assembled fragments separately.
  - Trace ORM, report-builder, search, and background-job paths because they may construct queries differently.
- Defensive anchor:
  - Prefer parameterized APIs and allowlist structural choices that cannot be parameterized.
  - Keep one typed representation from validation through execution.

### OWASP Authorization Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- Transferable test ideas:
  - When an interpreter selects objects or capabilities, test authorization after query evaluation rather than assuming the query filter is the only boundary.
  - Compare direct lookup, search, aggregation, report, and export paths for equivalent object restrictions.
- Defensive anchor:
  - Enforce authorization independently of user-controlled query structure.
