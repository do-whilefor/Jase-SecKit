# Maintainer Harness Workflow

This workflow uses Evaluation evidence to improve Flounder through a bounded
source candidate and paired baseline/candidate comparison.

## Evaluation Setup

Prepare:

- a Flounder source checkout and an isolated candidate branch;
- a finished baseline Evaluation group;
- stable work-item keys, material policies, evidence contracts, providers,
  models, and run settings shared by the baseline and candidate;
- a bounded candidate surface: prompts, skills, memory routing, or the legacy
  agent loop.

## Why Source Access Is Required

The Harness engine only mines persisted failure evidence, produces a bounded
candidate brief, and evaluates paired results. It does not modify source.
Improvement uses an external maintainer agent to edit candidate prompts,
skills, memory routing, or the legacy agent loop in an isolated branch. The
Harness UI and API expose the failure evidence, candidate brief, and paired
Evaluation results.

## Agent-Owned Flow

1. Start or reuse the Harness control plane:

   ```bash
   flounder ui --maintainer
   ```

   Inspect `GET /api` for runtime mode and the `harness-experiment` resource.

2. As the evaluation operator, inspect the finished baseline. It needs
   score-eligible positive and safe control cases, at least two distinct positive
   cases and families, and hidden holdouts. Separate execution failures from
   capability failures when interpreting the baseline.

3. Create the experiment with the candidate's editable-file list:

   ```bash
   flounder experiment create \
     --name <candidate-name> \
     --baseline <baseline-group> \
     --editable-file <candidate-path...>
   flounder experiment brief <candidate-name>
   ```

4. Create a clean worktree and `codex/` feature branch from the intended base.

5. Use the exported candidate brief and candidate source checkout to implement
   the smallest domain-general change supported by the mined failure pattern.

6. Return the candidate commit to the evaluation-operator context. Run the
   repository's deterministic tests and prompt-neutrality checks, then run the
   candidate Evaluation with the same stable work-item contracts, effective
   provider, model, thinking level, and run settings from the candidate checkout
   and daemon. The paired contract fingerprint rejects execution-setting drift.

7. Attach and evaluate the candidate:

   ```bash
   flounder experiment attach <candidate-name> --candidate <candidate-group>
   flounder experiment evaluate <candidate-name>
   ```

8. Interpret the deterministic verdict:

   - `promote`: prepare full release verification results, the diff, and the PR.
   - `reject`: retain the evidence and explain the regression or failed holdout.
   - `needs-more-samples`: add independent cases or repair blocked execution;
     measure sample diversity across distinct cases and families.

## Completion

Report the baseline and candidate group ids, experiment id, editable files,
paired improvements and regressions, holdout result, full verification result,
branch, commit, PR URL, and any unresolved evaluation or verification result.
