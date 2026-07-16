# Routing Evaluations

`evals.json` contains routing fixtures with the expected primary module and
Profile. Static validation checks fixture structure and Profile coverage; it
does not execute a model or prove that a model routed correctly.

Use the cases to check two different properties:

1. Routing: the Skill selects the expected primary Profile without asking the
   user to choose an internal category.
2. Execution: after routing, the Skill still follows
   `framework/verify-evidence.md`, establishes a baseline, performs dynamic
   validation, and records a reproducible boundary failure as
   `technical_hit` with `rating: unrated` until direct evidence supports the
   retained impact claims.

Every Profile has at least one direct routing fixture. An overlap case declares
`required_adjacent_profiles` only when its prompt explicitly contains a second
security boundary that must be followed. Possible but unobserved Combination
Paths do not belong in this field.

The file is intentionally simple JSON so custom test runners can consume it
without additional dependencies.
