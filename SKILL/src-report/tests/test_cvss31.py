"""Behavior tests for CVSS v3.1 Base scoring and its non-interactive CLI."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cvss31.py"
SPEC = importlib.util.spec_from_file_location("cvss31", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
cvss31 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cvss31)

VECTOR = "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"


class Cvss31Tests(unittest.TestCase):
    def test_known_base_vectors_and_severity(self):
        cases = (
            (VECTOR, 9.8, "CRITICAL"),
            ("AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N", 5.3, "MEDIUM"),
            ("AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L", 7.3, "HIGH"),
            ("AV:P/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N", 1.6, "LOW"),
            ("AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H", 10.0, "CRITICAL"),
            ("AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H", 9.9, "CRITICAL"),
            ("AV:N/AC:L/PR:H/UI:N/S:C/C:H/I:H/A:H", 9.1, "CRITICAL"),
            ("AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N", 6.1, "MEDIUM"),
        )
        for vector, score, severity in cases:
            with self.subTest(vector=vector):
                result = cvss31.calculate(vector)
                self.assertEqual(result["base_score"], score)
                self.assertEqual(result["severity"], severity)

    def test_scope_changed_uses_base_impact_and_changed_privileges(self):
        result = cvss31.calculate("AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H")
        calculation = result["calculation"]
        self.assertAlmostEqual(calculation["isc_base"], 0.914816)
        self.assertAlmostEqual(calculation["impact"], 6.0477304915)
        self.assertAlmostEqual(calculation["exploitability"], 3.10963422)
        self.assertEqual(calculation["factors"]["PR"], 0.68)
        self.assertAlmostEqual(calculation["uncapped_base"], 9.8899538885)

    def test_zero_impact_always_scores_zero(self):
        for scope in ("U", "C"):
            result = cvss31.calculate(f"AV:N/AC:L/PR:N/UI:N/S:{scope}/C:N/I:N/A:N")
            self.assertEqual(result["base_score"], 0.0)
            self.assertEqual(result["severity"], "NONE")
            self.assertGreater(result["calculation"]["exploitability"], 0)

    def test_roundup_respects_appendix_a_at_decimal_boundaries(self):
        for value, expected in ((4.0, 4.0), (4.02, 4.1), (0.1 + 0.2, 0.3),
                                (1.200003, 1.2), (1.200006, 1.3), (9.99999, 10.0)):
            with self.subTest(value=value):
                self.assertEqual(cvss31._roundup(value), expected)

    def test_severity_thresholds(self):
        for score, label in ((0, "NONE"), (0.1, "LOW"), (3.9, "LOW"),
                             (4.0, "MEDIUM"), (6.9, "MEDIUM"), (7.0, "HIGH"),
                             (8.9, "HIGH"), (9.0, "CRITICAL"), (10, "CRITICAL")):
            with self.subTest(score=score):
                self.assertEqual(cvss31._severity(score), label)

    def test_prefix_case_order_and_segment_whitespace_normalize(self):
        result = cvss31.calculate("  cvss:3.1 / a:h/c:h/i:h/s:u/ui:n/pr:n/ac:l/av:n  ")
        self.assertEqual(result, cvss31.calculate(VECTOR))
        self.assertEqual(result["vector"], "CVSS:3.1/" + VECTOR)
        self.assertEqual(result["version"], "3.1")
        self.assertEqual(result["metric_group"], "Base")
        self.assertEqual(list(result["metrics"]), ["AV", "AC", "PR", "UI", "S", "C", "I", "A"])

    def test_invalid_vectors_are_rejected_instead_of_partially_scored(self):
        invalid = (
            None, 42, "", "   ", "CVSS:3.1", "CVSS:3.0/" + VECTOR,
            "CVSS:4.0/" + VECTOR, "CVSS:2.0/" + VECTOR, VECTOR + "/AV:N",
            VECTOR + "/av:n", VECTOR + "/E:X", VECTOR + "/MAV:N", VECTOR + "/ZZ:N",
            VECTOR.replace("/A:H", ""), VECTOR.replace("AV:N", "AV:X"),
            VECTOR.replace("S:U", "S:X"), VECTOR.replace("C:H", "C:X"),
            VECTOR.replace("PR:N", "PR:R"), VECTOR.replace("UI:N", "UI:Y"),
            VECTOR.replace("AC:L", "AC:N"), VECTOR + "/", "/" + VECTOR,
            VECTOR.replace("AV:N", "AV:N:N"), VECTOR.replace("AV:N", "AV:"),
            VECTOR.replace("AV:N", ":N"), VECTOR.replace("AV:N", "AV: N"),
            VECTOR.replace("/AC:L", "//AC:L"),
        )
        for vector in invalid:
            with self.subTest(vector=vector):
                with self.assertRaises(ValueError):
                    cvss31.calculate(vector)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True, text=True, encoding="utf-8", timeout=10)

    def test_cli_json_and_text(self):
        for args in ((VECTOR, "--json"), ("--json", VECTOR)):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), cvss31.calculate(VECTOR))
        result = self.run_cli(VECTOR)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("9.8 (CRITICAL)", result.stdout)
        self.assertIn("CVSS:3.1/" + VECTOR, result.stdout)
        self.assertIn("evidence", result.stdout)

    def test_cli_missing_or_invalid_input_fails_without_prompt_or_traceback(self):
        for args in ((), ("--json",), ("CVSS:3.1/AV:N",), (VECTOR + "/E:X",)):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
