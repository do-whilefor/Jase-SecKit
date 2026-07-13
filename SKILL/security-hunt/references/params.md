# Parameter Parsing · Reference


Load on demand after selecting the `parameter-parser-differential` Profile. Cases expand variants; they do not replace dynamic evidence from the current target.


## HackerOne Case Index


### 150083 · Parameter-location/duplicate-key/Content-Type parsing differential
- Value: 10/10; framework-behavior exploitation / type confusion / XSS.
- Chain: Parameter pollution → parameter-location/duplicate-key/Content-Type parsing differential → security controls and the final execution point disagree about subject, object, state, or input semantics → script execution in a trusted origin.
- Bypass: Duplicate a parameter, move it between locations, change encoding/Content-Type, or use method override so the security control and business logic read different values.
- Defensive anchor: Parse once at the edge and reject duplicate security-sensitive parameters; fix the allowed Content-Type and method per endpoint; make validation and execution share the same normalized object; fail explicitly on Query/Body/Header/Cookie conflicts.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 719856 · Parameter-location/duplicate-key/Content-Type parsing differential
- Value: 9/10; framework-behavior exploitation / type confusion / deserialization.
- Chain: `https://www.npmjs.com/package/dot-prop` → parameter parsing differential, combined with deserialization/type-system semantic exploitation → the corresponding trust boundary is crossed → arbitrary code or command execution.
- Bypass: Use duplicate or relocated parameters and combine the parser disagreement with unsafe type restoration or dispatch.
- Defensive anchor: Parse once, reject duplicates and cross-location conflicts, fix method/Content-Type, share one normalized object, and add deserialization-focused cross-component regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.

### 78158 · Parameter-location/duplicate-key/Content-Type parsing differential
- Value: 8/10; framework-behavior exploitation / type confusion / XSS.
- Chain: `http://vulnerable-site.com/RenderImageServlet.php?imgId=1234&lang=application/x-shockwave-flash` → parameter parsing differential, combined with browser/template/filter parsing differences → the corresponding trust boundary is crossed → the unauthorized access, state change, or availability impact described by the report.
- Bypass: Use duplicate or relocated parameters and combine the parser disagreement with browser-side reinterpretation.
- Defensive anchor: Parse once, reject ambiguity, fix methods and content types, share one normalized object, and add browser-parsing regressions.
- Source status: the current material contains only a structured evaluation; review the original disclosure before citing it as a formal report.


## Source Coverage

- Full reports: 0.
- HackerOne reports: 9.
- HackerOne report IDs:
  - 856981, 894623, 298265, 78158, 114169, 719856, 126522, 106024, 150083

