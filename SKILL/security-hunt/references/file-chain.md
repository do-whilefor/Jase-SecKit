# File Processing Chain · Reference


Load on demand after selecting the `file-parser-pipeline` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## Full Report Cases


### 7asecurity/pentest-report groundtruth · GRT-01-004 WP1/2: Ground Truth RCEs via Crafted Config Files
- Value: 9/10; command injection / cross-component attack chain.
- Chain: The attacker supplies a malicious configuration, repository, filename, or package → an import, update, or installation component accepts it as data → a downstream shell, interpreter, or plugin mechanism reinterprets it → code executes on the client, build host, or server.
- Bypass: The data/code boundary is lost while input crosses components, bypassing an earlier layer’s assumption that it is ordinary text or a passive file.
- Defensive anchor: Avoid shell concatenation and use structured APIs; validate configuration and metadata against strict schemas; isolate build/import environments; sign and pin sources; never auto-execute hooks or plugins from untrusted repositories.

### isec-partners/NCC Group - phpMyAdmin · CSV Export Allows Arbitrary Command Execution in CSV File
- Value: 9/10; command injection / cross-component attack chain.
- Chain: The attacker stores a formula payload beginning with `=`, `+`, `-`, or `@` in a database field → an administrator exports a trusted CSV from phpMyAdmin → opens it in a desktop spreadsheet and accepts the prompt → the formula is evaluated and commands execute in the administrator’s context.
- Bypass: CSV is only a transport container, while spreadsheet software interprets certain cell prefixes as formulas, converting server-side data injection into client-side code execution.
- Defensive anchor: Export formula-looking values as inert text and strip bypass characters such as leading tabs; prefix risky cells with an apostrophe; provide a safe-export mode and clearly warn about formula execution in external spreadsheet software.

### trailofbits/Helm Final Report 2020 · 11 Path traversal through chart's dependency Data Validation
- Value: 9/10; path traversal / cross-component attack chain.
- Chain: The attacker controls a filename, archive entry, or path parameter → extraction or concatenation writes outside the intended directory → configuration, source, or executable locations are overwritten → information disclosure, artifact tampering, or code execution.
- Bypass: Validation occurs before canonicalization, or absolute paths, parent segments, links, or component-specific path semantics escape the sandbox root.
- Defensive anchor: Canonicalize before writing and verify the final path prefix; reject absolute paths, parent traversal, and link entries; constrain writes through directory handles; extract into isolation and move only allowlisted outputs.

### cure53/pentest-report Cryptocat-2 · Remote Code Execution via Conversation-/Nick-Name
- Value: 8/10; command injection.
- Chain: The attacker controls a command argument, template, or script fragment → the application concatenates it and sends it to an interpreter → arbitrary commands execute → data is read, services are controlled, or same-privilege resources are affected laterally.
- Bypass: String concatenation, incomplete escaping, or dynamic evaluation moves data into a code context.
- Defensive anchor: Avoid shell and `eval`; use parameterized process APIs and a fixed command allowlist; run with least privilege; centralize dangerous interpreter entry points and apply taint-oriented tests.


## HackerOne Case Index


### 99600 · File-processing order/multi-parser semantic difference
- Value: 9/10; framework-behavior exploitation / cross-component attack chain / authentication bypass.
- Chain: `GET /media_id_to_cdn_url.json?media_id=` → file-processing order/multi-parser semantic difference → security controls and the final execution point disagree about subject, object, state, or input semantics → access to or impact on another user’s data/state.
- Bypass: Create polyglot files, SVG/document/archive content, or post-conversion semantics that pass at upload but receive a different interpretation during preview, conversion, extraction, or browser rendering.
- Defensive anchor: Revalidate final stored, converted, extracted, and rendered outputs; use isolated, networkless converters; unify content sniffing, MIME, and download policy; inspect every archive member for path and link safety.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 175587 · File-processing order/multi-parser semantic difference
- Value: 8/10; framework-behavior exploitation / cross-component attack chain / other.
- Chain: `https://bugs.php.net/bug.php?id=73280` → file-processing order/multi-parser semantic difference, combined with memory-safety or low-level runtime behavior → the corresponding trust boundary is crossed → the unauthorized data access, state change, or availability impact described by the report.
- Bypass: Create content whose interpretation changes across upload, preview, conversion, extraction, or rendering; combine it with low-level runtime behavior to extend or complete the chain.
- Defensive anchor: Revalidate every final artifact; isolate converters; unify content and MIME handling; inspect archive entries; add cross-component regressions for the low-level runtime behavior.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 822262 · File-processing order/multi-parser semantic difference
- Value: 8/10; framework-behavior exploitation / cross-component attack chain / race condition.
- Chain: `PUT /api/v4/projects/` → file-processing order/multi-parser semantic difference, combined with a TOCTOU/concurrent-state boundary failure → the corresponding trust boundary is crossed → arbitrary file read.
- Bypass: Create content whose interpretation changes in later stages and combine it with a non-atomic state transition or object replacement.
- Defensive anchor: Revalidate final artifacts; isolate converters; inspect archive entries; add cross-component negative tests for TOCTOU/concurrent-state boundary failures, ensuring the check and final use operate on the same subject, object, state, and normalized semantics.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 9.
- HackerOne reports: 80.
- Full report IDs:
  - 7asecurity/pentest-report groundtruth
  - 7asecurity/pentest-report-amneziavpn3-RC1.1
  - 7asecurity/pentest-report-nvm
  - doyensec/Doyensec Gravitational GravityPlatform Q22019
  - isec-partners/NCC Group - phpMyAdmin
  - trailofbits/Helm Final Report 2020
  - x41-d-sec/X41-Unbound-Security-Audit-2019-Final-Report-Public
  - cure53/pentest-report Cryptocat-2
  - cure53/pentest-report tuf
- HackerOne report IDs:
  - 1984060, 403417, 421859, 226428, 223203, 1542881, 2442008, 783877, 416123, 683792, 1065885, 487081, 175587, 13959, 1043480, 587854, 631956, 303061
  - 2212627, 1277383, 867052, 816086, 1377748, 713900, 630903, 736522, 765291, 753971, 1218523, 1265390, 1132606, 946578, 880099, 242727, 237381, 996041
  - 1217114, 484664, 2299069, 248668, 1277389, 906907, 2244229, 1043804, 470637, 316713, 88395, 390346, 777241, 1397940, 1705717, 1066135, 129773, 534794
  - 1069039, 135072, 822262, 2010530, 662218, 381192, 1277392, 733248, 1092574, 212721, 374106, 263760, 1716249, 302885, 1069034, 1989884, 99600, 964550
  - 214022, 299460, 397527, 460911, 783392, 963155, 1262434, 667408

