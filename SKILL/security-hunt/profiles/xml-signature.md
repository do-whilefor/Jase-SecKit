---
id: xml-signature-consumption
group: crypto
reference: ../references/xml-signature.md
---

# XML Signature Consumption

**Use for:** SAML, SOAP WS-Security, XMLDSig, signed configuration/documents, and payment messages.

**Misalignment to find:** Signature verification resolves to one XML node while business logic consumes a different attacker-controlled node by ID, XPath, position, or deserialized representation.

## Baseline

- A valid signature proves only the referenced node; it does not automatically prove the node ultimately consumed by the application.
- Look for duplicate IDs, wrapping nodes, namespaces, XPath/DOM selection differences, and reconstruction during deserialization.
- Focus on the verifier and business code resolving to different nodes.
- Record the Reference URI, parser ID table, verified node object, and business-consumed object.

## Validation Order

1. Record the node actually resolved by the signature Reference.
2. Insert same-name, same-ID, or differently positioned nodes and change namespaces.
3. Compare node selection by the verification library with XPath/binder selection in business logic.
4. Prove that signature verification succeeds while an attacker-controlled assertion is consumed.

## Variant Axes

- Reference URI, ID registration rules, and nodes covered by the signature
- Duplicate IDs, wrapping nodes, namespaces, and XPath
- Selection differences across verifier, DOM, binder, and business code
- Post-verification reparsing, node copying, and final assertion consumption

## Combination Paths

- `crypto-binding`: Cryptographic Semantic Binding
- `oauth-sso`: OAuth/SSO
- `object-types`: Objects & Types
