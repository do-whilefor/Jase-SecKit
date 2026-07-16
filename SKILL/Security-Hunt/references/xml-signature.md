# XML Signature Consumption · Reference

Load after selecting the `xml-signature-consumption` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### 6.1 M01 XML Signature Wrapping Attack Targeting Signed Authentication Requests

- Source URL: https://hackmanit.de/images/download/Penetration-Test-Report-SURF-openconext-saml-java-by-Hackmanit.pdf
- Source locator: pp. 9-10, M01.
- Reported boundary:
  - Hackmanit reports that signature verification could follow the original
    nested `AuthnRequest` while application logic read a modified root request.
  - The report also limits the historical impact because relevant
    `AuthnRequest` values were generally constrained by metadata.
- Transferable test ideas:
  - Record the exact node identity, ID, reference target, and object instance at
    verification, policy evaluation, logging, and business consumption.
  - Vary duplicate IDs, wrapper position, signed nested nodes, unsigned roots,
    and parser namespace behavior one dimension at a time.
- Impact closure:
  - Prove that an unsigned consumed field changes a current-target identity,
    destination, privilege, object, or state decision. A verified/consumed node
    mismatch alone does not import the historical severity or a theoretical one.
- Defensive anchor:
  - Use a vetted SAML library.
  - Pass the exact verified object to business logic instead of reparsing or
    searching the document again.
  - Enforce unique IDs, fixed structure, audience, and destination checks.
  - Reject duplicate or unexpected nodes.
