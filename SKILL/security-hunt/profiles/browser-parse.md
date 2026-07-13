---
id: browser-parser-sanitizer
group: input
reference: ../references/browser-parse.md
---

# Browser Parsing

**Use for:** HTML/SVG/MathML sanitization, rich-text editors, frontend templates, CSP defenses, browser extensions, and WebViews.

**Misalignment to find:** Filters, template engines, the DOM, XML/HTML namespaces, CSP, or browser error-recovery algorithms derive different parse trees from the same content.

## Baseline

- HTML is a fault-tolerant, mutation-prone, multi-namespace parsing language.
- Sanitization, serialization, DOM repair, template compilation, and browser execution can occur in different orders.
- Focus on cases where the tree seen by the filter differs from the final execution tree.
- Record the raw string, sanitized string, initial DOM, reparsed DOM, and execution sink.

## Validation Order

1. Preserve the DOM or string at every stage of sanitization or template compilation.
2. Test namespace transitions, reparsing, DOM clobbering, framework gadgets, and context switching.
3. When CSP is treated as the final boundary, enumerate loaded scripts and available gadgets.
4. Validate the final DOM and execution in a real browser.

## Variant Axes

- Input context: HTML, attribute, URL, CSS, SVG, MathML, template
- Processing order: decoding, sanitization, template rendering, DOM insertion, browser repair
- Namespaces, quoting, tag closure, entities, and encodings
- Browser, rendering mode, CSP, and Trusted Types differences

## Combination Paths

- `unicode`: Unicode Normalization
- `browser-channel`: Cross-Origin Channels
- `field-injection`: Protocol Field Injection
