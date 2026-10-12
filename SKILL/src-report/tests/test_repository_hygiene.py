"""Keep local inputs out of Git without excluding the distributable skill."""

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("git") and (ROOT / ".git").exists(), "Requires a Git checkout")
class RepositoryHygieneTests(unittest.TestCase):
    def ignored_paths(self, paths):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin", "-z"],
            cwd=ROOT, input=("\0".join(paths) + "\0").encode("utf-8"),
            capture_output=True,
        )
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) if result.stdout else set()

    def test_local_materials_and_credentials_are_ignored(self):
        paths = [
            "AGENTS.md", "SRC报告生成_Skill与Workflow方案.md", "mermaid-diagram.png",
            "refer/input.txt", "materials/request.txt", "runs/case.json",
            "outputs/report.md", "scripts/__pycache__/assessment.cpython-314.pyc",
            ".pytest_cache/CACHEDIR.TAG",
        ]
        self.assertEqual(self.ignored_paths(paths), set(paths))

    def test_skill_source_and_tests_remain_publishable(self):
        paths = [
            "README.md", "SKILL.md", "LICENSE", "agents/openai.yaml", "prompts/build-src-report.md",
            "references/assessment.md", "references/src/jd.json",
            "scripts/assessment.py", "tests/test_repository_hygiene.py",
        ]
        self.assertEqual(self.ignored_paths(paths), set())


if __name__ == "__main__":
    unittest.main()
