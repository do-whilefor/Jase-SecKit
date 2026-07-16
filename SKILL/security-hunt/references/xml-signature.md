# XML Signature Consumption · Reference

Load after selecting the `xml-signature-consumption` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Reported focus` identifies the source topic; `Transferable test ideas` are abstractions, not source-verified reproduction steps.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### 6.1 M01 XML Signature Wrapping Attack Targeting Signed Authentication Requests

- Source: `hackmanit/Penetration-Test-Report-SURF-openconext-saml-java-by-Hackmanit`
- Reported focus: 6.1 M01 XML Signature Wrapping Attack Targeting Signed Authentication Requests
- Transferable test ideas:
  - Differences in XML reference resolution, ID parsing, and node selection separate the verified content from the content actually used.
- Defensive anchor:
  - Use a vetted SAML library.
  - Obtain assertions directly from the signature reference.
  - Enforce unique IDs, fixed structure, audience, and destination checks.
  - Reject duplicate or unexpected nodes.
- Evidence boundary:
  - Treat the source as a hypothesis seed only.
  - Reproduce every technical segment and impact claim on the current target.
  - Verify the original source before citing case-specific details externally.
