# XML Signature Consumption · Reference


Load on demand after selecting the `xml-signature-consumption` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### hackmanit/Penetration-Test-Report-SURF-openconext-saml-java-by-Hackmanit · 6.1 M01 XML Signature Wrapping Attack Targeting Signed Authentication Requests 7
- Value: 10/10; authentication bypass / protocol-behavior exploitation.
- Chain: The attacker copies or reorders a signed assertion and inserts a malicious node → the signature library verifies the legitimate node → business code reads a different node → identity or privileges are forged.
- Bypass: Differences in XML reference resolution, ID parsing, and node selection separate the verified content from the content actually used.
- Defensive anchor: Use a vetted SAML library; obtain assertions directly from the signature reference; enforce unique IDs, fixed structure, audience, and destination checks; reject duplicate or unexpected nodes.


## Source Coverage

- Full reports: 1.
- HackerOne reports: 0.
- Full report IDs:
  - hackmanit/Penetration-Test-Report-SURF-openconext-saml-java-by-Hackmanit

