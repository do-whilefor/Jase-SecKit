"""Observable session lifecycle and the public CLI over synthetic local evidence."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import session


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.base = Path(self.work.name)
        self.override = patch.object(session, "base_directory", return_value=self.base / "sessions")
        self.override.start()

    def tearDown(self):
        self.override.stop()
        self.work.cleanup()

    def invoke(self, *argv, batch=None):
        if batch is not None:
            path = self.base / "input.json"
            path.write_text(json.dumps(batch), encoding="utf-8")
            argv = (*argv, "--input", str(path))
        return session.dispatch(session.parser().parse_args(list(argv)))

    def test_same_session_reuses_knowledge_and_other_session_starts_empty(self):
        first = session.start("conversation-a", "Find the missing connection")
        self.invoke("record", "--root", first["root"], "--run-id", first["run_id"],
                    batch={"records": [{"id": "S-1", "kind": "Step", "summary": "Open question", "status": "blocked"}]})
        again = session.start("conversation-a", "A later subquestion")
        self.assertEqual(again["status"], "reused")
        self.assertEqual(again["run_id"], first["run_id"])
        self.assertEqual(again["goals"][0]["summary"], "Find the missing connection")
        self.assertIn("S-1", json.loads((Path(first["root"]) / "state.json").read_text())["records"])
        other = session.start("conversation-b", "Independent research")
        data = json.loads((Path(other["root"]) / "state.json").read_text())
        self.assertNotIn("S-1", data["records"])
        self.assertNotEqual(first["root"], other["root"])

    def test_multiturn_publish_discover_read_counterevidence_and_finish(self):
        opened = session.start("workflow", "Connect local training observations")
        common = ("--root", opened["root"], "--run-id", opened["run_id"])
        original = self.base / "source.txt"
        original.write_text("Synthetic raw response: reference=EXAMPLE-9", encoding="utf-8")
        conditions = {"environment": "lab", "purpose": "export"}
        first = self.invoke("record", *common, batch={
            "observations": [{"id": "O-A", "summary": "A reference was observed",
                              "content": {"reference": "EXAMPLE-9"}, "source_path": str(original)}],
            "records": [{"id": "C-A", "kind": "Capability", "status": "observed",
                         "summary": "早期响应中的标识", "observation_refs": ["O-A"],
                         "capability": {"provides": [{"type": "job-reference", "constraints": conditions}], "needs": []}}]})
        self.assertIn("C-A", first["changed_record_ids"])
        second = self.invoke("record", *common, batch={
            "observations": [{"id": "O-B", "summary": "A documented input contract",
                              "content": {"contract": "download accepts export handle"}}],
            "records": [{"id": "C-B", "kind": "Capability", "status": "candidate",
                         "summary": "后续下载入口", "observation_refs": ["O-B"],
                         "capability": {"provides": [], "needs": [{"type": "export-handle",
                             "aliases": ["job-reference"], "constraints": conditions}]}}]})
        pairs = second["chain_discovery"]["candidates"]
        self.assertTrue(any(p["producer_ref"] == "C-A" and p["consumer_ref"] == "C-B" for p in pairs))
        self.assertTrue(all(p["evidence"] is False for p in pairs))
        affected = second["change_impact"]["connections_to_review"]
        self.assertTrue(any(p["producer_ref"] == "C-A" and p["consumer_ref"] == "C-B" for p in affected))
        self.assertFalse(second["change_impact"]["evidence"])
        context = self.invoke("context", *common, "--query", "下一项验证", "--anchor", "C-B", "--no-methods")
        self.assertTrue({"C-A", "C-B"}.issubset({r["id"] for r in context["records"]}))
        raw = self.invoke("read", *common, "--id", "C-A")
        self.assertEqual(raw["package"]["observations"][0]["raw"]["reference"], "EXAMPLE-9")
        self.invoke("record", *common, batch={"records": [{
            "id": "CH-1", "kind": "Chain", "status": "candidate", "summary": "Pending connection",
            "steps": ["C-A", "C-B"], "links": [{"producer_ref": "C-A", "consumer_ref": "C-B",
                "provide_index": 0, "need_index": 0, "assessment": "candidate", "evidence_refs": []}]}]})
        self.invoke("context", *common, "--query", "", "--anchor", "CH-1", "--cursor", "main", "--no-methods")
        unchanged = self.invoke("context", *common, "--query", "", "--anchor", "CH-1", "--cursor", "main", "--no-methods")
        self.assertNotIn("change_impact", unchanged)
        update = self.invoke("record", *common, batch={
            "observations": [{"id": "O-C", "summary": "New scope limitation", "content": {"scope": "another use"}}],
            "records": [{"id": "F-C", "kind": "Fact", "status": "observed", "summary": "新证据限制原能力",
                         "observation_refs": ["O-C"], "contradicts": ["C-A"]}]})
        self.assertIn("CH-1", update["needs_review_chain_ids"])
        self.assertIn("CH-1", {row["id"] for row in update["change_impact"]["affected_chains"]})
        delta = self.invoke("context", *common, "--query", "", "--anchor", "CH-1", "--cursor", "main", "--no-methods")
        self.assertEqual(delta["change_impact"]["basis"], "new_or_changed_since_cursor_delivery")
        self.assertIn("CH-1", {row["id"] for row in delta["change_impact"]["affected_chains"]})
        chain = self.invoke("read", *common, "--id", "CH-1")
        self.assertEqual(next(r for r in chain["package"]["records"] if r["id"] == "CH-1")["status"], "needs_review")
        self.assertIn("C-A", (Path(opened["root"]) / "wiki/index.md").read_text())
        self.invoke("audit", *common)
        exported = self.base / "explicit-export"
        finished = session.finish(opened["root"], opened["run_id"], "workflow", str(exported))
        self.assertEqual(finished["status"], "deleted")
        self.assertFalse(Path(opened["root"]).exists())
        self.assertTrue(original.exists())
        self.assertTrue((exported / "evidence/O-A.source").exists())

    def test_authored_page_changes_have_review_impact_but_renames_do_not(self):
        opened = session.start("page-impact", "Review a documented condition")
        common = ("--root", opened["root"], "--run-id", opened["run_id"])
        page = {"id": "P", "kind": "question", "title": "Condition", "record_refs": ["G-001"],
                "blocks": [{"id": "B", "title": "Missing input", "source_refs": ["G-001"],
                            "text": "The grant still needs review."}]}
        self.invoke("record", *common, batch={"pages": [page]})
        page["blocks"][0]["text"] = "Check the grant and its tenant before use."
        edited = self.invoke("record", *common, batch={"pages": [page]})
        self.assertEqual(edited["content_changed_page_ids"], ["P"])
        affected = next(row for row in edited["change_impact"]["affected_pages"] if row["page_id"] == "P")
        self.assertEqual(affected["block_refs"], ["P/B"])
        renamed = self.invoke("record", *common, batch={"pages": [{"id": "P", "title": "Grant conditions"}]})
        self.assertEqual(renamed["content_changed_page_ids"], [])
        self.assertEqual(renamed["change_impact"]["changed_refs"], [])

    def test_finish_requires_owner_and_never_deletes_original_input(self):
        opened = session.start("owner", "Preserve inputs")
        with self.assertRaises(ValueError):
            session.finish(opened["root"], "other-run", "owner")
        with self.assertRaises(ValueError):
            session.finish(opened["root"], opened["run_id"], "another-session")
        self.assertTrue(Path(opened["root"]).exists())
        session.finish(opened["root"], opened["run_id"], "owner")

    def test_compare_command_reads_both_observations_without_publishing_a_verdict(self):
        opened = session.start("comparison", "Compare local baseline and retest")
        common = ("--root", opened["root"], "--run-id", opened["run_id"])
        self.invoke("record", *common, batch={"observations": [
            {"id": "O-A", "content": {"request": {"method": "GET", "url": "/reports"},
                                      "response": {"status": 200, "body": {"status": "ok"}}}},
            {"id": "O-B", "content": {"request": {"method": "GET", "url": "/reports"},
                                      "response": {"status": 200, "body": {"status": "denied"}}}}]})
        state = Path(opened["root"]) / "state.json"
        previous = state.read_bytes()
        result = self.invoke("compare", *common, "--left", "O-A", "--right", "O-B",
                             "--field", "response.body.status")
        self.assertEqual(result["assessment"], "comparison_only")
        self.assertEqual(result["observation_refs"], ["O-A", "O-B"])
        self.assertFalse(result["selected_fields"][0]["equal"])
        self.assertEqual(state.read_bytes(), previous)
        self.assertEqual(json.loads((Path(opened["root"]) / "logs/operations.jsonl").read_text().splitlines()[-1])["action"], "compare")

    def test_public_cli_runs_start_record_context_audit_finish(self):
        def cli(*args):
            result = subprocess.run([sys.executable, str(SCRIPTS / "session.py"), *args],
                                    cwd=self.base, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        sid = "cli-test-" + uuid.uuid4().hex
        opened = cli("start", "--session-id", sid, "--question", "Synthetic CLI check")
        common = ("--root", opened["root"], "--run-id", opened["run_id"])
        try:
            example = SCRIPTS.parent / "assets/record-example.json"
            result = cli("record", *common, "--input", str(example))
            self.assertIn("C-001", result["changed_record_ids"])
            context = cli("context", *common, "--query", "正常提交", "--anchor", "C-001", "--no-methods")
            self.assertIn("C-001", {r["id"] for r in context["records"]})
            events = [json.loads(line) for line in (Path(opened["root"]) / "logs/operations.jsonl").read_text().splitlines()]
            response = events[-1]
            self.assertEqual((response["action"], response["command"]), ("response", "context"))
            self.assertTrue({"load", "index", "package", "serialization"} <= response["metrics"]["stages_ms"].keys())
            self.assertGreater(response["metrics"]["counts"]["files_read"], 0)
            self.assertNotIn("metrics", context)
            self.assertNotIn("_active_stages", response["metrics"])
            self.assertNotIn("正常提交", json.dumps(events, ensure_ascii=False))
            cli("wiki", *common, "knowledge")
            cli("audit", *common)
            cli("methods", "--query", "能力消费", "--intent", "capability-consumer")
        finally:
            cli("finish", *common, "--session-id", sid)
        self.assertFalse(Path(opened["root"]).exists())


if __name__ == "__main__":
    unittest.main()
