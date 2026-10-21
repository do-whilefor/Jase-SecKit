"""Final delivery must preserve complete evidence within the caller's budget."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rag import encode, retrieve
import rag
from session import start
from store import publish


class ContextDeliveryLimitsTests(unittest.TestCase):
    def make_session(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        info = start("context-delivery", "Test goal", temporary.name)
        publish(info["root"], info["run_id"], {"records": [
            {"id": f"Q-{i}", "kind": "Question", "summary": "needle " + "x " * 200,
             "status": "open"} for i in range(8)]})
        return info

    def retrieve(self, info, **kwargs):
        return retrieve(info["root"], info["run_id"], "needle",
                        mode="lexical", view="compact", **kwargs)

    def cursor_path(self, info):
        return next((Path(info["root"]) / "cache").glob("context-*.json"))

    def test_final_envelope_does_not_discard_deliverable_records(self):
        info = self.make_session()
        for limit in (3000, 4000, 5000, 6000, 8000):
            with self.subTest(limit=limit):
                result = self.retrieve(info, budget_chars=limit)
                self.assertNotEqual(result["status"], "unavailable")
                self.assertIn("G-001", {row["id"] for row in result["records"]})
                self.assertTrue(any(row["id"].startswith("Q-") for row in result["records"]))
                self.assertGreater(result["budget"]["omitted_units"], 0)
                self.assertEqual(result["budget"]["used_chars"], len(encode(result)))
                self.assertLessEqual(len(encode(result)), limit)

    def test_large_envelope_skips_unused_packing_budget_when_retrying(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        info = start("large-envelope", "synthetic goal " + "x" * 12000, temporary.name)
        publish(info["root"], info["run_id"], {"records": [
            {"id": "Q-HIT", "kind": "Question", "summary": "needle", "status": "open"}]})
        limit = len(encode(self.retrieve(info)))
        with patch("rag._retrieve", wraps=rag._retrieve) as pack:
            result = self.retrieve(info, budget_chars=limit)
        self.assertLessEqual(pack.call_count, 6)
        self.assertNotEqual(result["status"], "unavailable")
        self.assertIn("Q-HIT", {row["id"] for row in result["records"]})
        self.assertLessEqual(len(encode(result)), limit)

    def test_question_and_cursor_envelopes_keep_sources_and_only_acknowledge_delivery(self):
        info = self.make_session()
        publish(info["root"], info["run_id"], {
            "observations": [{"id": "O-1", "content": {"response": {"status": 200}}}],
            "records": [{"id": "Q-0", "observation_refs": ["O-1"],
                         "change_reason": "Attach observed source"}]})
        result = self.retrieve(info, budget_chars=7000, question_ref="Q-0", cursor="reader")
        self.assertNotEqual(result["status"], "unavailable")
        self.assertIn("Q-0", {row["id"] for row in result["records"]})
        self.assertEqual({row["id"] for row in result["observations"]}, {"O-1"})
        artifact_refs = {row["index"]["artifact_id"] for row in result["observations"]}
        self.assertTrue(artifact_refs.issubset({row["id"] for row in result["artifacts"]}))
        self.assertLessEqual(len(encode(result)), 7000)
        saved = json.loads(self.cursor_path(info).read_text(encoding="utf-8"))["delivered"]
        acknowledged = {json.loads(key)[1] for key in saved if json.loads(key)[0] == "record"}
        self.assertEqual(acknowledged, {row["id"] for row in result["records"]})
        previous = self.cursor_path(info).read_bytes()
        failed = self.retrieve(info, budget_chars=1024, question_ref="Q-0", cursor="reader")
        self.assertEqual(failed["status"], "unavailable")
        self.assertFalse(failed["delta"]["cursor_advanced"])
        self.assertEqual(self.cursor_path(info).read_bytes(), previous)

    def test_corrupt_cursor_recovers_by_redelivering_current_material(self):
        info = self.make_session()
        expected = self.retrieve(info, cursor="reader")
        cursor_path = self.cursor_path(info)
        valid = json.loads(cursor_path.read_text(encoding="utf-8"))
        malformed = ("{", "[]", encode({**valid, "delivered": []}),
                     encode({**valid, "delivered": {"not-json": {}}}),
                     encode({**valid, "delivered": {encode(["record", "Q-0"]): []}}),
                     encode({**valid, "delivered": {encode(["record", "Q-0"]): {
                         "content": "digest", "navigation": "digest", "combination": None}}}),
                     encode({**valid, "queries": []}))
        for contents in malformed:
            with self.subTest(contents=contents):
                cursor_path.write_text(contents, encoding="utf-8")
                result = self.retrieve(info, cursor="reader")
                self.assertEqual(result["records"], expected["records"])
                self.assertEqual(result["delta"]["reset_reason"], "invalid_cursor")
                self.assertTrue(result["delta"]["cursor_advanced"])
                self.assertEqual(self.retrieve(info, cursor="reader")["records"], [])

    def test_larger_budget_delivers_records_omitted_from_previous_cursor_response(self):
        info = self.make_session()
        expected = {row["id"] for row in self.retrieve(info)["records"]}
        first = self.retrieve(info, budget_chars=5000, cursor="reader")
        self.assertNotEqual(first["status"], "unavailable")
        delivered = {row["id"] for row in first["records"]}
        self.assertTrue(delivered)
        self.assertTrue(delivered < expected)
        self.assertTrue(first["delta"]["cursor_advanced"])
        self.assertGreater(first["budget"]["omitted_units"], 0)
        self.assertLessEqual(len(encode(first)), 5000)

        resumed = self.retrieve(info, budget_chars=30000, cursor="reader")
        self.assertNotEqual(resumed["status"], "unavailable")
        self.assertEqual({row["id"] for row in resumed["records"]}, expected - delivered)
        self.assertEqual({row["id"] for row in resumed["unchanged_refs"]
                          if row["kind"] == "record"}, delivered)
        self.assertEqual(resumed["budget"]["omitted_units"], 0)
        self.assertLessEqual(len(encode(resumed)), 30000)
        repeated = self.retrieve(info, budget_chars=30000, cursor="reader")
        self.assertEqual(repeated["records"], [])
        self.assertTrue(repeated["retrieval_progress"]["same_request_unchanged"])

    def test_refresh_ignores_unreadable_previous_cursor(self):
        info = self.make_session()
        expected = self.retrieve(info, cursor="reader")
        self.cursor_path(info).write_text("{", encoding="utf-8")
        result = self.retrieve(info, cursor="reader", refresh=True)
        self.assertEqual(result["records"], expected["records"])
        self.assertEqual(result["delta"]["reset_reason"], "explicit_refresh")

    def test_failed_atomic_replacement_preserves_previous_delivery(self):
        info = self.make_session()
        self.retrieve(info, cursor="reader")
        cursor_path = self.cursor_path(info)
        previous = cursor_path.read_bytes()
        publish(info["root"], info["run_id"], {"records": [
            {"id": "Q-0", "summary": "needle revised", "change_reason": "New context"}]})
        with patch("context_views.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(ValueError):
                self.retrieve(info, cursor="reader")
        self.assertEqual(cursor_path.read_bytes(), previous)
        self.assertEqual(list(cursor_path.parent.glob("context-*.tmp")), [])
        changed = self.retrieve(info, cursor="reader")
        self.assertIn("Q-0", {row["id"] for row in changed["records"]})


if __name__ == "__main__":
    unittest.main()
