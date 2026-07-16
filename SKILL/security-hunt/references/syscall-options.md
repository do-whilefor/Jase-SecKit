# System Calls & Options · Reference

Load after selecting the `syscall-option-boundary` Profile and forming a current-target hypothesis.

## Use Rule

- Use these sources to expand command, argument, option, environment, and system-call boundary hypotheses.
- Do not infer execution from string reflection, an error, or the presence of a shell-like character.
- Capture the final executable, argument vector, environment, working directory, caller identity, and side effect.

## Curated Sources

### OWASP OS Command Injection Defense Cheat Sheet

- Source URL: https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html
- Transferable test ideas:
  - Determine whether the application invokes a shell, a direct process API, a CLI wrapper, or a privileged service.
  - Test argument injection, leading-option interpretation, delimiter handling, environment influence, and alternate execution paths.
  - Distinguish shell metacharacter injection from unsafe argument or option construction.
- Defensive anchor:
  - Prefer library APIs over external commands and use fixed executable paths with explicit argument construction.
  - Apply least privilege and terminate option parsing where supported.

### OWASP WSTG · Testing for Command Injection

- Source URL: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/07-Input_Validation_Testing/12-Testing_for_Command_Injection
- Transferable test ideas:
  - Trace user-controlled values through wrappers, job runners, file converters, package tools, and administrative helpers.
  - Verify final execution with a controlled side effect, process trace, or another independent signal.
- Defensive anchor:
  - Keep untrusted values out of command syntax and validate arguments against a narrow semantic allowlist.
