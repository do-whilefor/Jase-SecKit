"""Project-scoped storage contracts exercised through the real, offline CLI."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / "scripts" / "session.py"


class ProjectStorageCLITests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="webounty projects ")
        self.addCleanup(self.work.cleanup)
        self.base = Path(self.work.name)

    def cli(self, cwd, *args, batch=None, succeeds=True):
        if batch is not None:
            args = (*args, "--input", "-")
        result = subprocess.run(
            [sys.executable, str(CLI), *map(str, args)],
            cwd=cwd,
            input=json.dumps(batch) if batch is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if not succeeds:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("error", json.loads(result.stderr))
            return
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    @staticmethod
    def owner_args(opened):
        return ("--root", opened["root"], "--run-id", opened["run_id"])

    def assert_project_storage(self, opened, project):
        expected_project = project.resolve()
        root = Path(opened["root"])
        self.assertEqual(opened["project_root"], str(expected_project))
        self.assertEqual(root.parent, expected_project / ".webounty")
        self.assertRegex(root.name, r"^[0-9a-f]{64}$")
        self.assertTrue((root / "wiki/index.md").is_file())
        marker = json.loads((root / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["project_root"], str(expected_project))
        self.assertEqual(marker["session_id"], opened["session_id"])
        self.assertEqual(marker["run_id"], opened["run_id"])
        return root

    def test_default_cwd_reuses_knowledge_without_ascending_to_git_root(self):
        repository = self.base / "repository parent"
        project = repository / "nested project with spaces"
        project.mkdir(parents=True)
        (repository / ".git").mkdir()

        opened = self.cli(project, "start", "--session-id", "same conversation",
                          "--question", "Keep the original research goal")
        self.assertEqual(opened["status"], "created")
        root = self.assert_project_storage(opened, project)
        self.assertFalse((repository / ".webounty").exists())

        published = self.cli(project, "record", *self.owner_args(opened), batch={
            "records": [{"id": "S-LOCAL", "kind": "Step", "status": "blocked",
                         "summary": "Retain this unanswered question"}],
        })
        again = self.cli(project, "start", "--session-id", "same conversation",
                         "--question", "A later question must not reset the session")
        self.assertEqual(again["status"], "reused")
        self.assertEqual(again["root"], str(root))
        self.assertEqual(again["run_id"], opened["run_id"])
        self.assertEqual(again["state_revision"], published["state_revision"])
        self.assertEqual(again["goals"][0]["summary"], "Keep the original research goal")
        stored = self.cli(project, "read", *self.owner_args(again), "--id", "S-LOCAL")
        self.assertEqual(stored["package"]["records"][0]["summary"],
                         "Retain this unanswered question")

    def test_explicit_project_root_and_returned_root_survive_cwd_changes(self):
        project = self.base / "selected project"
        launcher = self.base / "launch directory"
        later = self.base / "different working directory"
        for path in (project, launcher, later):
            path.mkdir()
        original = project / "original response.txt"
        original.write_text("Synthetic local reference: EXAMPLE-9\n", encoding="utf-8")

        opened = self.cli(launcher, "start", "--session-id", "explicit project",
                          "--question", "Preserve evidence across directory changes",
                          "--project-root", "../selected project/.")
        root = self.assert_project_storage(opened, project)
        self.assertFalse((launcher / ".webounty").exists())
        common = self.owner_args(opened)
        self.cli(later, "record", *common, batch={
            "observations": [{"id": "O-LOCAL", "summary": "A synthetic reference",
                              "content": {"reference": "EXAMPLE-9"},
                              "source_path": str(original)}],
            "records": [{"id": "F-LOCAL", "kind": "Fact", "status": "observed",
                         "summary": "The local response contains EXAMPLE-9",
                         "observation_refs": ["O-LOCAL"]}],
        })
        context = self.cli(later, "context", *common, "--query", "local reference",
                           "--anchor", "F-LOCAL", "--no-methods")
        self.assertIn("F-LOCAL", {row["id"] for row in context["records"]})
        stored = self.cli(later, "read", *common, "--id", "F-LOCAL")
        observation = next(row for row in stored["package"]["observations"]
                           if row["id"] == "O-LOCAL")
        self.assertEqual(observation["raw"]["reference"], "EXAMPLE-9")
        self.assertTrue((root / "evidence/O-LOCAL.source").is_file())
        self.assertFalse((later / ".webounty").exists())

        finished = self.cli(later, "finish", *common, "--session-id", "explicit project")
        self.assertEqual(finished["status"], "deleted")
        self.assertFalse(root.exists())
        self.assertTrue((project / ".webounty").is_dir())
        self.assertEqual(original.read_text(encoding="utf-8"),
                         "Synthetic local reference: EXAMPLE-9\n")

    def test_projects_are_isolated_and_finish_preserves_neighbors_and_inputs(self):
        project_a = self.base / "project A"
        project_b = self.base / "project B"
        project_a.mkdir()
        project_b.mkdir()
        shared_id = "conversation shared across projects"
        opened_a = self.cli(project_a, "start", "--session-id", shared_id,
                            "--question", "Project A research")
        opened_b = self.cli(project_b, "start", "--session-id", shared_id,
                            "--question", "Project B research")
        neighbor = self.cli(project_a, "start", "--session-id", "neighbor conversation",
                            "--question", "Neighbor research")
        root_a = self.assert_project_storage(opened_a, project_a)
        root_b = self.assert_project_storage(opened_b, project_b)
        neighbor_root = self.assert_project_storage(neighbor, project_a)
        self.assertNotEqual(root_a, root_b)
        self.assertNotEqual(opened_a["run_id"], opened_b["run_id"])
        self.assertNotEqual(root_a, neighbor_root)

        original = project_a / "input evidence.txt"
        original.write_text("An original project file must survive cleanup.\n", encoding="utf-8")
        sentinel = project_a / ".webounty" / "keep.txt"
        sentinel.write_text("Unrelated project metadata.\n", encoding="utf-8")
        self.cli(project_a, "record", *self.owner_args(opened_a), batch={
            "observations": [{"id": "O-A", "content": {"project": "A"},
                              "source_path": str(original)}],
            "records": [{"id": "F-A", "kind": "Fact", "status": "observed",
                         "summary": "Knowledge belongs only to project A",
                         "observation_refs": ["O-A"]}],
        })
        self.cli(project_b, "read", *self.owner_args(opened_b), "--id", "F-A",
                 succeeds=False)
        state_before = (root_a / "state.json").read_bytes()

        for run_id, session_id in ((opened_b["run_id"], shared_id),
                                   (opened_a["run_id"], "neighbor conversation")):
            with self.subTest(run_id=run_id, session_id=session_id):
                self.cli(project_b, "finish", "--root", root_a, "--run-id", run_id,
                         "--session-id", session_id, succeeds=False)
                self.assertEqual((root_a / "state.json").read_bytes(), state_before)

        self.cli(project_b, "finish", *self.owner_args(opened_a), "--session-id", shared_id)
        self.assertFalse(root_a.exists())
        self.assertTrue(project_a.is_dir())
        self.assertTrue((project_a / ".webounty").is_dir())
        self.assertEqual(original.read_text(encoding="utf-8"),
                         "An original project file must survive cleanup.\n")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "Unrelated project metadata.\n")
        for opened, expected_goal in ((opened_b, "Project B research"),
                                      (neighbor, "Neighbor research")):
            stored = self.cli(project_b, "read", *self.owner_args(opened), "--id", "G-001")
            self.assertEqual(stored["package"]["records"][0]["summary"], expected_goal)


if __name__ == "__main__":
    unittest.main()
