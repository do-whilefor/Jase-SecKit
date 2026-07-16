# Races & TOCTOU · Reference

Load after selecting the `toctou-state-boundary` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Verified HackerOne Index

### HackerOne #187134 · JSBeautifier BApp race condition and memory leak

- Source: `HackerOne report #187134`
- Source URL: https://hackerone.com/reports/187134
- Source topic: Concurrent processing exposed a race condition that caused memory growth.
- Transferable test ideas:
  - Exercise the same shared processing path with controlled concurrency and repeatable input sizes.
  - Measure success rate, memory growth, thread count, queue behavior, and recovery after load stops.
  - Distinguish a race-specific invariant failure from ordinary high-cost processing.
- Defensive anchor:
  - Protect shared mutable state with correct synchronization and ownership rules.
  - Bound per-request and aggregate resource use.
  - Add concurrent regression tests that assert both correctness and resource recovery.
