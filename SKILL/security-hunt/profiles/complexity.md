---
id: algorithmic-complexity
group: system
reference: ../references/complexity.md
---

# Algorithmic Complexity

**Use for:** regex/replacement, JSON/number parsing, DNSSEC, cryptographic proof verification, compression/decompression, and recursive parsers.

**Misalignment to find:** An attacker supplies valid but worst-case numbers, regular expressions, DNSSEC structures,
compressed data, or parse trees that make CPU, memory, recursion, or verification cost grow superlinearly.

## Baseline

- Syntactic validity does not mean computational cost is bounded.
- Look for backtracking, repeated big-integer operations, graph/chain validation, recursion depth, duplicate items, and amplification.
- Focus on cases where an input-size limit does not bound the actual amount of work.
- Record input size, key operation count, CPU/memory/stack use, concurrency amplification, and timeout behavior.

## Validation Order

1. Identify loops, recursion, backtracking, and big-integer hotspots.
2. Generate structured inputs of increasing size.
3. Measure the resource curve and compare it with expected complexity.
4. Add concurrency and cache misses.
5. Prove attacker-controlled resource exhaustion and document recovery behavior.

## Variant Axes

- Input size, structure, nesting, duplication, and compression ratio
- CPU, memory, recursion depth, I/O, lock hold time, and queue length
- Worst-case algorithms, regex backtracking, password verification, parsing, and proof verification
- Per-request cost, concurrency amplification, cache effects, and timeout/quota behavior

## Combination Paths

- `value-lifetime`: Values & Lifetimes
- `object-types`: Objects & Types
- `shared-state`: Shared Protocol State
