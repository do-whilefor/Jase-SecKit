"""Public session replay for question gaps, routing, and repeated retrieval."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import session
from rag import encode


def capability(rid, provides=(), needs=()):
    def spec(name):
        return {"type": name, "constraints": {"tenant": "lab-a"}}
    return {"id": rid, "kind": "Capability", "status": "observed", "summary": rid,
            "observation_refs": ["O-" + rid], "conditions": {"tenant": "lab-a"},
            "capability": {"provides": list(map(spec, provides)), "needs": list(map(spec, needs))}}


class QuestionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.opened = session.start("questions", "Review synthetic report workflow", self.project)
        self.root = Path(self.opened["root"])
        self.common = ["--root", str(self.root), "--run-id", self.opened["run_id"]]

    def invoke(self, command, *args):
        return session.dispatch(session.parser().parse_args([command, *self.common, *args]))

    def publish(self, records):
        state = json.loads((self.root / "state.json").read_text())
        observations = [{"id": oid, "content": {"synthetic": True, "result": row["id"]}}
                        for row in records for oid in row.get("observation_refs", [])
                        if oid not in state["observations"]]
        path = self.project / "batch.json"
        path.write_text(json.dumps({"records": records, "observations": observations}))
        return self.invoke("record", "--input", str(path))

    def query(self, *args, question="C"):
        return self.invoke("context", "--question-ref", question, "--no-methods", *args)

    def test_missing_input_new_provider_and_revocation_replay(self):
        self.publish([capability("A", ["job"]), capability("C", needs=["job", "grant"])])
        first = self.query("--cursor", "main")
        report = first["question_context"]
        self.assertEqual(report["requirements"]["status"], "unresolved")
        self.assertIn("grant", {r["type"] for r in report["requirements"]["missing_preconditions"]})
        self.assertFalse(first["retrieval_progress"]["same_request_unchanged"])
        repeated = self.query("--cursor", "main")
        self.assertEqual(repeated["retrieval_progress"]["recommendation"], "stop_repeating_query")
        self.assertEqual(repeated["question_context"], report)
        self.assertFalse(repeated["records"])
        self.publish([capability("B", ["grant"])])
        added = self.query("--cursor", "main")
        self.assertFalse(added["retrieval_progress"]["same_request_unchanged"])
        self.assertEqual(added["question_context"]["requirements"]["status"], "candidate_complete")
        self.assertEqual(added["question_context"]["answer_support"], "not_assessed")
        self.assertFalse(added["question_context"]["evidence"])
        self.publish([{"id": "REVOKED", "kind": "Fact", "status": "observed",
                       "summary": "Synthetic revocation", "contradicts": ["B"],
                       "observation_refs": ["O-REVOKED"]}])
        revoked = self.query("--cursor", "main")
        self.assertEqual(revoked["question_context"]["requirements"]["status"], "unresolved")
        self.assertIn("O-REVOKED", {r["id"] for r in revoked["observations"]})
        refresh = self.query("--cursor", "main", "--refresh")
        self.assertFalse(refresh["retrieval_progress"]["same_request_unchanged"])
        self.assertTrue(refresh["records"])

    def test_lexical_mode_skips_graph_but_retains_corrections(self):
        self.publish([capability("A", ["job"]), capability("C", needs=["job"])])
        self.query("--cursor", "main")
        self.publish([{"id": "CORRECTION", "kind": "Fact", "status": "observed",
                       "summary": "Current consumer needs review", "contradicts": ["C"],
                       "observation_refs": ["O-CORRECTION"]}])
        with patch("discovery.discover", side_effect=AssertionError("graph should not run")), \
             patch("change_impact.build_impact", side_effect=AssertionError("impact should not run")):
            found = self.query("--mode", "lexical", "--cursor", "main")
        report = found["question_context"]
        self.assertEqual(report["requirements"]["status"], "not_checked")
        self.assertIn("CORRECTION", report["competing_record_refs"])
        self.assertIn("O-CORRECTION", {r["id"] for r in found["observations"]})
        self.assertFalse(found["chain_discovery"]["candidates"])
        self.assertTrue(any(r.get("mode") == "combined" for r in report["next_actions"]))
        self.assertFalse(found["retrieval_progress"]["same_request_unchanged"])

    def test_single_input_checks_upstream_not_only_direct_match(self):
        self.publish([capability("A", ["job"], ["session"]), capability("C", needs=["job"])])
        report = self.query()["question_context"]
        self.assertEqual(report["requirements"]["status"], "unresolved")
        self.assertIn("session", {r["type"] for r in report["requirements"]["missing_preconditions"]})
        self.publish([capability("S", ["session"])])
        self.assertEqual(self.query()["question_context"]["requirements"]["status"], "candidate_complete")

    def test_same_words_do_not_merge_different_conditions(self):
        producer = capability("A", ["job"])
        producer["capability"]["provides"][0]["constraints"]["tenant"] = "lab-b"
        self.publish([producer, capability("C", needs=["job"])])
        self.assertEqual(self.query()["question_context"]["requirements"]["status"], "unresolved")

    def test_undeclared_needs_or_missing_observations_never_mean_complete(self):
        self.publish([{"id": "C", "kind": "Question", "status": "open", "summary": "Can we read the report?"}])
        report = self.query()["question_context"]
        self.assertEqual(report["requirements"]["status"], "not_declared")
        self.assertEqual(report["source_observation_refs"], [])
        self.assertIn("no_source_evidence", {r["code"] for r in report["source_issues"]})
        self.assertEqual(report["answer_support"], "not_assessed")

    def test_authored_question_recalls_observation_without_promoting_claim(self):
        self.publish([{"id": "C", "kind": "Question", "status": "open",
                       "summary": "HTTP 202 with job_id", "observation_refs": ["O-C"]}])
        path = self.project / "pages.json"
        path.write_text(json.dumps({"pages": [{"id": "P", "kind": "question",
            "title": "Export", "record_refs": ["C"], "blocks": [{"id": "B",
            "title": "Observed task", "text": "A task identifier was returned. Download remains untested.",
            "questions": ["最终产物可以下载吗？"]}]}]}))
        self.invoke("record", "--input", str(path))
        found = self.invoke("context", "--mode", "lexical", "--query", "最终产物", "--no-methods")
        self.assertIn("P/B", {r["page_id"] + "/" + r["block_id"] for r in found["blocks"]})
        self.assertIn("O-C", {r["id"] for r in found["observations"]})
        self.assertEqual(next(r for r in found["records"] if r["id"] == "C")["status"], "open")

    def test_other_query_does_not_reset_repeat_detection_and_session_isolation(self):
        self.publish([capability("C"), capability("D")])
        self.query("--cursor", "main")
        other = self.query("--cursor", "main", question="D")
        self.assertFalse(other["retrieval_progress"]["same_request_unchanged"])
        self.assertTrue(self.query("--cursor", "main")["retrieval_progress"]["same_request_unchanged"])
        self.assertFalse(self.query("--cursor", "other-reader")["retrieval_progress"]["same_request_unchanged"])
        isolated = session.start("another-session", "Separate question", self.project)
        args = session.parser().parse_args(["context", "--root", isolated["root"],
            "--run-id", isolated["run_id"], "--question-ref", "C"])
        with self.assertRaisesRegex(ValueError, "existing session record"):
            session.dispatch(args)

    def test_incomplete_output_does_not_create_a_repeat_checkpoint(self):
        self.publish([capability("A", ["job"]), capability("C", needs=["job", "grant"])])
        self.query("--cursor", "main")
        cursor = next((self.root / "cache").glob("context-*.json"))
        before = cursor.read_bytes()
        for view in ("compact", "evidence"):
            short = self.query("--cursor", "main", "--budget-chars", "1024", "--view", view)
            self.assertEqual(short["status"], "unavailable")
            self.assertFalse(short["delta"]["cursor_advanced"])
            self.assertLessEqual(len(encode(short)), 1024)
        self.assertEqual(cursor.read_bytes(), before)

    def test_tampered_evidence_is_not_unchanged_success(self):
        self.publish([capability("C")])
        self.query("--cursor", "main")
        artifact = self.root / "evidence/O-C.jsonl"
        artifact.write_text("{}\n")
        changed = self.query("--cursor", "main")
        self.assertEqual(changed["question_context"]["source_issues"][0]["code"], "observation_unavailable")
        self.assertEqual(changed["retrieval_progress"]["recommendation"], "resolve_incomplete_retrieval")
        self.assertFalse(changed["retrieval_progress"]["same_request_unchanged"])

    def test_source_change_during_question_check_discards_mixed_result(self):
        import question_context
        self.publish([capability("C")])
        self.query("--cursor", "main")
        cursor = next((self.root / "cache").glob("context-*.json"))
        before = cursor.read_bytes()
        assess = question_context.assess_question

        def change_after_check(*args, **kwargs):
            result = assess(*args, **kwargs)
            state = self.root / "state.json"
            current = json.loads(state.read_text())
            current["revision"] += 1
            state.write_text(json.dumps(current))
            return result

        with patch.object(question_context, "assess_question", side_effect=change_after_check):
            result = self.query("--cursor", "main")
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result.get("records"))
        self.assertNotIn("question_context", result)
        self.assertFalse(result["delta"]["cursor_advanced"])
        self.assertEqual(cursor.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
