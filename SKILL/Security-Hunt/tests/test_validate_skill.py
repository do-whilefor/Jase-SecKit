from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path


class SkillValidationTest(unittest.TestCase):
    root = Path(__file__).resolve().parents[1]

    def run_validator(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(root / "scripts" / "validate_skill.py")],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    def run_mutation(
        self,
        mutate: Callable[[Path], None],
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "security-hunt"
            shutil.copytree(self.root, root)
            mutate(root)
            return self.run_validator(root)

    def test_static_validator_passes(self) -> None:
        result = self.run_validator(self.root)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_reference_profile_identity_drift_is_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "references" / "http-boundary.md"
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace("`http-parser-differential`", "`wrong-profile-id`", 1),
                encoding="utf-8",
            )

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("declares Profile id 'wrong-profile-id'", result.stdout)

    def test_broad_bash_preapproval_is_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "SKILL.md"
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace(
                    "allowed-tools: Read Grep Glob",
                    "allowed-tools: Read Grep Glob Bash",
                    1,
                ),
                encoding="utf-8",
            )

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("allowed-tools must preapprove only Read Grep Glob", result.stdout)

    def test_reported_boundary_requires_source_url(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "references" / "oauth-sso.md"
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace(
                    "- Source URL: https://cure53.de/pentest-report_pomerium.pdf",
                    "- Source: `unverified/pomerium`",
                    1,
                ),
                encoding="utf-8",
            )

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reported boundary at line", result.stdout)
        self.assertIn("requires a Source URL for provenance", result.stdout)

    def test_reported_boundary_requires_impact_closure(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "references" / "oauth-sso.md"
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace("- Impact closure:", "- Validation note:", 1),
                encoding="utf-8",
            )

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has no Impact closure", result.stdout)

    def test_reported_boundary_requires_source_locator(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "references" / "oauth-sso.md"
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace("- Source locator:", "- Source note:", 1),
                encoding="utf-8",
            )

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has no Source locator", result.stdout)

    def test_missing_profile_section_is_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "profiles" / "csrf.md"
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace("## Validation Order", "## Validation Steps", 1),
                encoding="utf-8",
            )

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing required section 'Validation Order'", result.stdout)

    def test_incomplete_eval_coverage_is_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "evals" / "evals.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["cases"] = [
                case
                for case in payload["cases"]
                if case["expected_profile"] != "unicode"
            ]
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Profiles without a routing fixture: unicode", result.stdout)

    def test_unknown_state_value_is_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "framework" / "blackboard-template.yaml"
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace("finding_status: lead", "finding_status: testing", 1),
                encoding="utf-8",
            )

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown finding_status 'testing'", result.stdout)

    def test_invalid_terminal_mapping_is_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "framework" / "verify-evidence.md"
            text = path.read_text(encoding="utf-8")
            original = "| `LOW_ROI` | `impact_verified` | `info` |"
            replacement = "| `LOW_ROI` | `technical_hit` | `info` |"
            path.write_text(
                text.replace(original, replacement, 1),
                encoding="utf-8",
            )

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LOW_ROI finding_status must be", result.stdout)

    def test_duplicate_terminal_mapping_is_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "framework" / "verify-evidence.md"
            text = path.read_text(encoding="utf-8")
            row = (
                "| `VULN_FOUND` | `impact_verified` | `P1`, `P2`, or `P3` | "
                "Reproducible PoC and original verifiable evidence exist |"
            )
            path.write_text(text.replace(row, f"{row}\n{row}", 1), encoding="utf-8")

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate terminal mapping row for VULN_FOUND", result.stdout)

    def test_fence_with_trailing_text_is_not_a_closer(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "README.md"
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text + "\n```text\ninside\n``` not-a-closing-fence\n",
                encoding="utf-8",
            )

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unclosed Markdown fence", result.stdout)

    def test_crlf_line_endings_are_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "README.md"
            text = path.read_text(encoding="utf-8")
            path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contains CR or CRLF line endings", result.stdout)

    def test_invalid_utf8_is_reported_without_crashing(self) -> None:
        def mutate(root: Path) -> None:
            (root / "SKILL.md").write_bytes(b"\xff\n")

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SKILL.md: invalid UTF-8 at byte 0", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_missing_core_file_is_reported_without_crashing(self) -> None:
        def mutate(root: Path) -> None:
            (root / "SKILL.md").unlink()

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SKILL.md: missing required file", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_missing_final_newline_is_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "README.md"
            path.write_bytes(path.read_bytes().rstrip(b"\n"))

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing final newline", result.stdout)

    def test_trailing_blank_lines_are_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "README.md"
            path.write_bytes(path.read_bytes() + b"\n")

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contains trailing blank lines", result.stdout)

    def test_overlong_text_line_is_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "README.md"
            text = path.read_text(encoding="utf-8")
            path.write_text(text + ("x" * 181) + "\n", encoding="utf-8")

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("181 characters; split it for model readability", result.stdout)

    def test_missing_terminal_section_is_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "framework" / "verify-evidence.md"
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace(
                    "### 3.3 Terminal Result",
                    "### 3.3 Completion Marker",
                    1,
                ),
                encoding="utf-8",
            )

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing section '### 3.3 Terminal Result'", result.stdout)

    def test_legacy_adjacent_eval_key_is_rejected(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "evals" / "evals.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            case = next(
                item for item in payload["cases"] if "required_adjacent_profiles" in item
            )
            case["expected_adjacent_profiles"] = case.pop("required_adjacent_profiles")
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        result = self.run_mutation(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uses legacy expected_adjacent_profiles", result.stdout)


if __name__ == "__main__":
    unittest.main()
