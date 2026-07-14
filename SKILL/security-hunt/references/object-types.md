# Objects & Types · Reference

Load after selecting the `deserialization-type-system` Profile and forming a current-target hypothesis.

Historical cases are variant seeds only. Do not transfer their impact, severity, exploit chain, or final outcome to the current target. Reproduce every relevant segment and every claimed impact independently. `Knowledge value` ranks reference usefulness, not current-target severity.

## HackerOne Case Index

### 134321 · Deserialization/type-system semantic exploitation
- Knowledge value: 9/10; deserialization / type confusion / command injection.
- Chain: `https://charlie.bz/blog/rails-3.2.10-remote-code-execution` → deserialization/type-system semantic exploitation → security controls and the final execution point disagree about subject, object, state, or input semantics → arbitrary code or command execution.
- Bypass: Construct special serialized objects, type markers, prototype properties, or cross-language values that drive deserialization or conversion into an unintended code path.
- Defensive anchor: Do not use general-purpose object deserialization on untrusted data; use explicit schemas and type allowlists; reject prototype-related keys; upgrade affected dependencies; isolate deserialization with least privilege.

### 146255 · Deserialization/type-system semantic exploitation
- Knowledge value: 9/10; deserialization / type confusion / framework-behavior exploitation.
- Chain: `https://bugs.php.net/bug.php?id=72340` → deserialization/type-system semantic exploitation, combined with memory-safety or low-level runtime behavior → the corresponding trust boundary is crossed → arbitrary code or command execution.
- Bypass: Construct special serialized values and combine type confusion with low-level runtime behavior.
- Defensive anchor: Use explicit schemas and allowlists, reject prototype keys, update dependencies, isolate the parser, and add cross-component regressions for the low-level runtime path.

### 410237 · Deserialization/type-system semantic exploitation
- Knowledge value: 9/10; deserialization / type confusion / framework-behavior exploitation.
- Chain: `http://172.16.175.143` → deserialization/type-system semantic exploitation, combined with file-processing order and multi-parser semantic differences → the corresponding trust boundary is crossed → arbitrary code or command execution.
- Bypass: Construct special serialized values and combine them with downstream file-processing or multi-parser reinterpretation.
- Defensive anchor: Use explicit schemas and allowlists, isolate deserialization, and regression-test the downstream file-processing chain.
