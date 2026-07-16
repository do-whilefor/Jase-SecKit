---
id: terminal-control-sequence
group: input
reference: ../references/terminal-escape.md
---

# Terminal Escapes

**Use for:** audit logs, SSH/operations platforms, CI output, terminal approvals, CLI listings, and alerts.

**Misalignment to find:** Plain text from a Web/API context is reinterpreted by a CLI, log viewer, or terminal as
ANSI/VT control sequences, allowing output forgery, content hiding, or interaction manipulation.

## Baseline

- Text is a stateful control language in a terminal.
- ESC/CSI/OSC, carriage return, backspace, line feed, and bidirectional characters can change display or interaction.
- Focus on differences between stored content and terminal-rendered content.
- Record raw bytes, stored logs, terminal-emulator state, final visible text, and key behavior.

## Validation Order

1. Find every path from user input to a terminal or log display.
2. Inject cursor movement, line clearing, title, hyperlink, carriage-return, and newline sequences.
3. Compare behavior in a real terminal and a Web log viewer.
4. Verify forged approvals, hidden identifiers, or operator deception.

## Variant Axes

- Control characters: ESC/CSI/OSC, CR, LF, backspace, tab, bidirectional characters
- Propagation location: username, reason, filename, header, log field
- Consumer: real terminal, Web log viewer, CI, SSH/TUI
- Result: overwrite, hide, forge, link spoofing, interaction-state change

## Combination Paths

- `field-injection`: Protocol Field Injection
- `unicode`: Unicode Normalization
