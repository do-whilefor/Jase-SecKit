# XML Signature Consumption · Reference

Load after selecting the `xml-signature-consumption` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## Full Report Cases

### hackmanit/Penetration-Test-Report-SURF-openconext-saml-java-by-Hackmanit · 6.1 M01 XML Signature Wrapping Attack Targeting Signed Authentication Requests 7
- Knowledge value: 10/10; authentication bypass / protocol-behavior exploitation.
- Chain: The attacker copies or reorders a signed assertion and inserts a malicious node → the signature library verifies the legitimate node → business code reads a different node → identity or privileges are forged.
- Bypass: Differences in XML reference resolution, ID parsing, and node selection separate the verified content from the content actually used.
- Defensive anchor: Use a vetted SAML library; obtain assertions directly from the signature reference; enforce unique IDs, fixed structure, audience, and destination checks; reject duplicate or unexpected nodes.
