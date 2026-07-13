# System Calls & Options · Reference


Load on demand after selecting the `syscall-option-boundary` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## HackerOne Case Index


### 212696 · System-call argument/option-boundary failure
- Value: 8/10; command injection / framework-behavior exploitation / cross-component attack chain.
- Chain: `/edit/process` → system-call argument/option-boundary failure, combined with file-processing order and multi-parser semantic differences → the corresponding trust boundary is crossed → arbitrary code or command execution.
- Bypass: Inject a controllable filename, path, argument, or configuration fragment into an external tool’s argument/option boundary, triggering the tool’s own secondary parsing; combine this with file-processing differences to extend the chain.
- Defensive anchor: Avoid shell concatenation and use argument arrays; enforce allowlists and the `--` option terminator at the final call site; reject user filenames beginning with `-`; fix working directory, environment, and configuration; run external tools in a low-privilege, networkless sandbox; add file-processing cross-component regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 388936 · System-call argument/option-boundary failure
- Value: 8/10; command injection / framework-behavior exploitation.
- Chain: `https://www.npmjs.com/package/egg-scripts` → system-call argument/option-boundary failure → security controls and the final execution point disagree about subject, object, state, or input semantics → arbitrary code or command execution.
- Bypass: Inject controllable filenames, paths, arguments, or configuration fragments into external-tool option boundaries so the tool reparses data as options.
- Defensive anchor: Avoid shell concatenation; use argument arrays; apply allowlists and `--`; reject leading-dash filenames; fix working directory, environment, and configuration; execute tools in a low-privilege, networkless sandbox.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 0.
- HackerOne reports: 6.
- HackerOne report IDs:
  - 388936, 212696, 690010, 1154034, 1763704, 390631

