---
id: low-level-value-lifetime
group: system
reference: ../references/value-lifetime.md
---

# Values & Lifetimes

**Use for:** protocol length fields, memory allocation, indexes/offsets, FFI/system calls, reference counting, and buffer lifetimes.

**Misalignment to find:** Boundary checks and later allocation, indexing, system-call, or object-use stages use different integer widths, signs, truncation rules, or lifetimes.

## Baseline

- A security check must cover the same final value and object lifetime that are later used.
- Look for signed/unsigned conversion, narrowing, multiply-add overflow, negative lengths, aliasing, and use-after-free.
- Focus on safe values at check time that become dangerous after conversion or a lifetime transition.
- Record raw fields, every conversion type, allocation size, index range, ownership, and release point.

## Validation Order

1. Annotate the type and conversion of every length and index.
2. Test negative values, maximum values, multiply-add boundaries, truncation, and architecture-width differences.
3. Trace ownership, references, and asynchronous callbacks.
4. Validate with sanitizers/fuzzing and hand-built boundary cases.
5. Prove OOB, UAF, invalid function-pointer use, or loss of a security property.

## Variant Axes

- Integer width, sign, truncation, overflow, underflow, and unit conversion
- Type differences across checking, allocation, indexing, copying, and system calls
- Object length, offset, count, reference, and release timing
- 32/64-bit, compiler, ABI, platform, and optimization-level differences

## Combination Paths

- `complexity`: Algorithmic Complexity
- `fs-identity`: File-Object Identity
- `sandbox`: Sandboxes & Containers
