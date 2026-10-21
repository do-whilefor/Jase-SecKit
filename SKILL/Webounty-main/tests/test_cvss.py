"""Offline CLI regression against published FIRST examples and specification edges."""

import json
from pathlib import Path
import subprocess
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cvss31-calculator.js"

# Fixed expected values transcribed from FIRST CVSS 3.1 Examples sections 3-7,
# 9-10, not calculated by another implementation of the formula under test.
# https://www.first.org/cvss/v3.1/examples
FIRST_EXAMPLES = (
    ("CVE-2013-0375", "AV:N/AC:L/PR:L/UI:N/S:C/C:L/I:L/A:N", 6.4, "MEDIUM"),
    ("CVE-2014-3566", "AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:N/A:N", 3.1, "LOW"),
    ("CVE-2012-1516", "AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H", 9.9, "CRITICAL"),
    ("CVE-2009-0783", "AV:L/AC:L/PR:H/UI:N/S:U/C:L/I:L/A:L", 4.2, "MEDIUM"),
    ("CVE-2012-0384", "AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H", 7.2, "HIGH"),
    ("CVE-2014-0160", "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N", 7.5, "HIGH"),
    ("CVE-2014-6271", "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8, "CRITICAL"),
)


class CvssTests(unittest.TestCase):
    def run_cli(self, *args, stdin=None):
        return subprocess.run(
            ["node", str(SCRIPT), *args], input=stdin, text=True,
            capture_output=True, timeout=10,
        )

    def score(self, vector):
        result = self.run_cli("--json", vector)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_published_first_examples(self):
        for name, vector, score, severity in FIRST_EXAMPLES:
            with self.subTest(example=name):
                result = self.score("CVSS:3.1/" + vector)
                self.assertEqual(result["baseScore"], score)
                self.assertEqual(result["severity"], severity)
                self.assertEqual(result["vector"], "CVSS:3.1/" + vector)
                self.assertEqual(result["version"], "3.1")
                self.assertEqual(result["metricGroup"], "Base")

    def test_no_impact_is_zero_for_both_scopes(self):
        # FIRST section 7.1: Impact <= 0 makes BaseScore zero.
        # Upstream incorrectly returned 4.3 for the Changed case.
        for scope in ("U", "C"):
            with self.subTest(scope=scope):
                result = self.score(f"CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:{scope}/C:N/I:N/A:N")
                self.assertEqual(result["baseScore"], 0)
                self.assertEqual(result["severity"], "NONE")

    def test_scope_changed_regression_and_score_ceiling(self):
        # Independently reviewed against FIRST section 7.1; upstream F18 gave 3.2.
        result = self.score("CVSS:3.1/AV:N/AC:H/PR:N/UI:R/S:C/C:L/I:L/A:N")
        self.assertEqual(result["baseScore"], 4.7)
        self.assertEqual(result["severity"], "MEDIUM")
        maximum = self.score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H")
        self.assertEqual(maximum["baseScore"], 10)

    def test_metric_order_and_bare_vectors_are_normalized(self):
        result = self.score("a:n/i:l/c:l/s:c/ui:n/pr:l/ac:l/av:n")
        self.assertEqual(result["vector"], "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:L/I:L/A:N")
        self.assertEqual(result["baseScore"], 6.4)

    def test_invalid_vectors_do_not_produce_scores(self):
        valid = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
        invalid = (
            valid.replace("S:U", "S:X"),
            valid.replace("CVSS:3.1", "CVSS:4.0"),
            valid.replace("CVSS:3.1", "CVSS:3.0"),
            valid + "/AV:N",
            valid.replace("/S:U", ""),
            valid.replace("AV:N", "AV:Q"),
            valid.replace("AV:N", "AV:N:EXTRA"),
            valid + "/E:F",  # Base only: do not silently ignore modifiers.
            valid + "/",
        )
        for vector in invalid:
            with self.subTest(vector=vector):
                result = self.run_cli("--json", vector)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.strip())

    def test_roundup_matches_first_examples_without_float_drift(self):
        # FIRST section 7: 4.02 -> 4.1, 4.00 -> 4.0.
        # Appendix A: 0.1 + 0.2 must not drift upward to 0.4 in JavaScript.
        result = subprocess.run(
            ["node", "-e",
             "const {roundup}=require(process.argv[1]);"
             "console.log(JSON.stringify([roundup(4.02),roundup(4),roundup(0.1+0.2)]));",
             str(SCRIPT)], text=True, capture_output=True, check=True, timeout=10,
        )
        self.assertEqual(json.loads(result.stdout), [4.1, 4, 0.3])

    def test_import_does_not_read_stdin_or_run_cli(self):
        result = subprocess.run(
            ["node", "-e",
             "const data=process.stdin.listenerCount('data'),end=process.stdin.listenerCount('end');"
             "const api=require(process.argv[1]);"
             "console.log(JSON.stringify({calc:typeof api.calc,data:process.stdin.listenerCount('data')-data,"
             "end:process.stdin.listenerCount('end')-end}));",
             str(SCRIPT)], input="this is not a vector", text=True,
            capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout), {"calc": "function", "data": 0, "end": 0})

    def test_json_stdin_and_readable_output(self):
        vector = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N"
        piped = self.run_cli("--json", stdin=vector + "\n")
        self.assertEqual(piped.returncode, 0, piped.stderr)
        self.assertEqual(json.loads(piped.stdout)["baseScore"], 7.5)
        readable = self.run_cli(vector)
        self.assertEqual(readable.returncode, 0, readable.stderr)
        self.assertIn("Score:     7.5", readable.stdout)
        self.assertIn("Severity:  HIGH", readable.stdout)
        self.assertIn("Computation:", readable.stdout)


if __name__ == "__main__":
    unittest.main()
