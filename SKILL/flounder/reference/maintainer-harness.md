# Maintainer Harness Workflow

Use this workflow only when an authorized Flounder maintainer asks the agent to
improve Flounder itself. It is not part of a normal target audit and must never
run automatically after an operator Project.

## Boundary

Before doing anything, prove all of the following:

- the current checkout is the Flounder source repository;
- the operator authorized source changes and a reviewable branch or PR;
- the baseline is a finished Evaluation group, not private Project output;
- candidate and baseline use the same stable work-item keys, material policies,
  evidence contracts, providers, models, and run settings;
- the candidate can edit only bounded prompts, skills, memory routing, or the
  legacy agent loop; audit orchestration, run health, preparation, evaluator
  answers, holdouts, material policy, sandbox or command safety, confirmation or
  refutation gates, promotion policy, tests, merge authority, and deployment
  logic stay protected;

If any condition is false, stop. Do not reinterpret an ordinary audit request as
permission to improve the product.

## Why Source Access Is Required

The Harness engine only mines persisted failure evidence, produces a bounded
candidate brief, and evaluates paired results. It does not modify source.
Improvement requires an external maintainer agent to edit approved prompts,
skills, memory routing, or the legacy agent loop in an isolated branch. The
trusted audit orchestrator, health classifier, and preparation path are not in
the editable surface. Therefore normal Flounder users do not need the Harness
UI or API.

## Agent-Owned Flow

1. Start or reuse an explicitly enabled control plane:

   ```bash
   flounder ui --maintainer
   ```

   Verify `GET /api` returns `maintainerMode: true` and advertises the
   `harness-experiment` resource. Do not try to bypass a disabled server.

2. As the evaluation operator, inspect the finished baseline. It needs
   score-eligible positive and safe control cases, at least two distinct positive
   cases and families, and hidden holdouts. Blocked infrastructure is repair
   work, not learning evidence. Do not copy item-level holdout identities,
   expected outcomes, or results into the candidate-editing context.

3. Create the experiment with the narrowest justified editable-file allowlist:

   ```bash
   flounder experiment create \
     --name <candidate-name> \
     --baseline <baseline-group> \
     --editable-file <approved-path...>
   flounder experiment brief <candidate-name>
   ```

4. Create a clean worktree and `codex/` feature branch from the intended base.
   Never edit the maintainer's main checkout or a target audit workspace.

5. Give a fresh coding-agent context only the exported candidate brief and the
   approved source checkout. That agent implements the smallest domain-general
   change supported by the mined failure pattern. Do not give it the baseline
   manifest, holdout item details, expected answers, target names, incident
   wording, exploit recipes, or bug-specific strategy.

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

8. Act on the deterministic verdict:

   - `promote`: run the full release verification suite, review the diff, and
     open a PR. Promotion never merges or deploys.
   - `reject`: keep the evidence, do not ship the source change, and explain the
     regression or failed holdout.
   - `needs-more-samples`: add independent cases or repair blocked execution;
     do not duplicate one case to satisfy diversity gates.

## Trigger Policy

Run this flow only on an explicit maintainer request or a maintainer-owned
scheduled maintenance task. Prefer accumulated Evaluation evidence over a
single lucky or unlucky run. Never ingest private Project artifacts into a
public regression corpus, and never trigger source changes after every Project.

## Completion

Report the baseline and candidate group ids, experiment id, editable files,
paired improvements and regressions, holdout result, full verification result,
branch, commit, and PR URL. If no PR is created, name the exact gate that stopped
promotion.
