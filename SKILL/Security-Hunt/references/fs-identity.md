# File-Object Identity · Reference

Load after selecting the `filesystem-object-identity` Profile and forming a current-target hypothesis.

## Use Rule

- Read this file only after forming a current-target hypothesis and recording a baseline.
- `Source topic` is only a historical label; `Reported boundary` requires primary-source-checked facts, a URL, and a locator.
- `Transferable test ideas` are abstractions, not source facts or reproduction evidence.
- Never inherit historical impact, exploitability, scope, severity, or chain completion.
- Verify the original source before citing case-specific details outside the testing workspace.

## Retained Case Notes

### CON-01-013 WP2: Unauthorized Artifact Modification via Race Condition

- Source URL: https://conda-forge.org/_static/CON-01-conda-forge-Audit-Public_RC1.0.pdf
- Source locator: pp. 18-21, CON-01-013.
- Reported boundary:
  - 7ASecurity reports a gap between token, artifact-path, and hash validation
    and the later copy step. An attacker could modify the artifact after
    validation so different bytes reached the production artifact path.
- Transferable test ideas:
  - Model file identity as at least `{namespace, path, object/version, digest}`.
    Prove whether authorization and digest checks bind to the exact immutable
    object version later copied or published.
  - Instrument validate, open, copy, rename, upload, and publish timestamps;
    vary replacement, overwrite, link, retry, and concurrent build ownership.
- Impact closure:
  - Prove that copied or published bytes differ from the bytes whose digest and
    authorization were accepted, then verify the resulting artifact through a
    clean consumer. Winning a timing window alone is not the supply-chain impact.
- Defensive anchor:
  - Publish from immutable content-addressed storage or one already-open handle.
  - Recheck the digest on the copied object, use atomic promotion, and bind the
    authenticated build identity to the immutable artifact version.
