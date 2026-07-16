# Prototype Pollution · Reference

Load after selecting the `prototype-pollution` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### Server-Side Prototype Pollution via Filters Request Parameter

- Source: `x41-d-sec/X41-Backstage-Audit-2024-Final-Report-Public`
- Source topic: Server-Side Prototype Pollution via Filters Request Parameter
- Transferable test ideas:
  - JavaScript prototype inheritance performs implicit lookup, allowing security options or object fields that were never set locally to be modified globally.
- Defensive anchor:
  - Use null-prototype objects or Map.
  - Recursively reject dangerous keys.
  - Update affected dependencies.
  - Use own-property checks at security-sensitive reads and freeze critical configuration objects.
