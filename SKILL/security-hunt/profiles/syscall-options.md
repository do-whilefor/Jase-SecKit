---
id: syscall-option-boundary
group: system
reference: ../references/syscall-options.md
---

# System Calls & Options

**Use for:** kernel syscalls, privileged daemons, CLI wrappers, environment-driven tools, and filenames converted into command arguments.

**Misalignment to find:** Low-privilege input influences high-privilege kernel or daemon behavior through system calls, command-line arguments, environment variables, file descriptors, or option parsing.

## Baseline

- Arguments are not always pure data; they may change the call target, option set, or kernel object.
- Look for negative values/truncation, option prefixes, environment variables, nested pointers, callbacks, and inherited file descriptors.
- Focus on wrappers that validate a surface value while the lower layer executes under a different type or syntax.
- Record raw arguments, converted types, argv/env, syscall number, and kernel object.

## Validation Order

1. Mark every cross-privilege call and the source of each argument.
2. Test sign, width, boundaries, option prefixes, environment variables, and nested structures.
3. Compare wrapper-layer arguments with the final lower-level arguments.
4. Prove impact through an unauthorized call, arbitrary file/memory access, or command side effect.

## Variant Axes

- Command/syscall argument boundaries and option terminators
- Paths, environment variables, working directory, file descriptors, and inherited handles
- Real semantics of privileged daemons, kernel interfaces, or helper programs
- Argument reordering, short/long options, response files, globbing, and configuration injection

## Combination Paths

- `privileged-ipc`: Privileged IPC
- `file-chain`: File Processing Chain
- `fs-identity`: File-Object Identity
