# Path Canonicalization · Reference

Load after selecting the `path-canonicalization` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Verified HackerOne Index

### HackerOne #178152 · Read files on application server, leads to RCE

- Source: `HackerOne report #178152`
- Source URL: https://hackerone.com/reports/178152
- Source topic: A GitLab export-upload path allowed application-server file disclosure and a separately demonstrated escalation path.
- Transferable test ideas:
  - Trace archive, export, import, and upload filenames through extraction and the final file operation.
  - Test traversal, absolute paths, link handling, decoding order, and root-containment checks.
  - Prove arbitrary file access first; validate any downstream code-execution segment independently.
- Defensive anchor:
  - Apply containment checks to the final canonical filesystem object.
  - Reject archive entries and links that escape the intended root.
  - Separate the evidence and severity of file access from any later execution chain.
