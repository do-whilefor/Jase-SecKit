from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


class SkillValidationTest(unittest.TestCase):
    def test_static_validator_passes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "validate_skill.py")],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
