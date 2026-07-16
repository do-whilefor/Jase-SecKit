# Routing Evaluations

`evals.json` contains representative prompts with the expected primary module and Profile.

Use the cases to check two different properties:

1. Routing: the Skill selects the expected primary Profile without asking the user to choose an internal category.
2. Execution: after routing, the Skill still follows `framework/verify-evidence.md`, establishes a baseline, performs
   dynamic validation, and keeps technical hits `unrated` until impact is independently evidenced.

The file is intentionally simple JSON so it can be consumed by custom test runners without additional dependencies.
