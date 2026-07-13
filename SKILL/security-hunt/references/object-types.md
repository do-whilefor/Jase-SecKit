# Objects & Types · Reference


Load on demand after selecting the `deserialization-type-system` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## HackerOne Case Index


### 134321 · Deserialization/type-system semantic exploitation
- Value: 9/10; deserialization / type confusion / command injection.
- Chain: `https://charlie.bz/blog/rails-3.2.10-remote-code-execution` → deserialization/type-system semantic exploitation → security controls and the final execution point disagree about subject, object, state, or input semantics → arbitrary code or command execution.
- Bypass: Construct special serialized objects, type markers, prototype properties, or cross-language values that drive deserialization or conversion into an unintended code path.
- Defensive anchor: Do not use general-purpose object deserialization on untrusted data; use explicit schemas and type allowlists; reject prototype-related keys; upgrade affected dependencies; isolate deserialization with least privilege.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 146255 · Deserialization/type-system semantic exploitation
- Value: 9/10; deserialization / type confusion / framework-behavior exploitation.
- Chain: `https://bugs.php.net/bug.php?id=72340` → deserialization/type-system semantic exploitation, combined with memory-safety or low-level runtime behavior → the corresponding trust boundary is crossed → arbitrary code or command execution.
- Bypass: Construct special serialized values and combine type confusion with low-level runtime behavior.
- Defensive anchor: Use explicit schemas and allowlists, reject prototype keys, update dependencies, isolate the parser, and add cross-component regressions for the low-level runtime path.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 410237 · Deserialization/type-system semantic exploitation
- Value: 9/10; deserialization / type confusion / framework-behavior exploitation.
- Chain: `http://172.16.175.143` → deserialization/type-system semantic exploitation, combined with file-processing order and multi-parser semantic differences → the corresponding trust boundary is crossed → arbitrary code or command execution.
- Bypass: Construct special serialized values and combine them with downstream file-processing or multi-parser reinterpretation.
- Defensive anchor: Use explicit schemas and allowlists, isolate deserialization, and regression-test the downstream file-processing chain.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 0.
- HackerOne reports: 47.
- HackerOne report IDs:
  - 410237, 73235, 983548, 1425474, 245228, 454365, 172411, 55029, 801522, 134321, 390881, 921288, 998398, 1739099, 1051192, 248659, 7972, 73245
  - 308489, 146255, 1679624, 1663299, 1095645, 198734, 407552, 415137, 1280002, 415501, 403083, 411140, 913695, 350418, 852613, 1106238, 181871, 73244
  - 2138080, 1183335, 1672388, 159948, 2334460, 1415436, 986386, 968355, 980649, 390929, 185041

