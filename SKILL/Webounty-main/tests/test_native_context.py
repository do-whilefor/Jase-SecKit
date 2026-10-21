"""Native compact packaging retains judgments and validation without source expansion."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from context_views import finalize_context
from rag import Corpus, encode, retrieve
from store import publish


class NativeContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "wiki").mkdir()
        (self.root / "state.json").write_text(encode({
            "run_id": "R1", "revision": 1, "session_id": "S1", "records": {},
            "observations": {}, "entities": {}, "artifacts": {},
        }), encoding="utf-8")
        (self.root / "wiki/manifest.json").write_text(encode({"run_id": "R1", "pages": []}), encoding="utf-8")
        self.payload = "Original response with important evidence.\n" * 3000
        self.source = self.root / "import.txt"
        self.source.write_bytes(self.payload.encode("utf-8"))
        self.block = {"id": "B", "title": "Current judgment", "source_refs": ["R"],
                      "text": "Only tenant lab-a was tested.\nCounterevidence: the response denied access.\n"
                              "A second identity must still be checked.",
                      "knowledge": {"limitations": ["A second identity remains untested"]}}
        publish(self.root, "R1", {
            "entities": [{"id": "ENDPOINT", "kind": "endpoint", "name": "/report"}],
            "observations": [{"id": "O", "summary": "The report request was denied",
                "subject_refs": ["ENDPOINT"], "source_path": str(self.source),
                "content": {"actor_ref": "role-a", "request": {"method": "GET", "url": "/report"},
                            "response": {"status": 403, "body": self.payload}}}],
            "records": [
                {"id": "G", "kind": "Goal", "status": "active", "summary": "Inspect report access"},
                {"id": "R", "kind": "Question", "status": "open", "summary": "Report access conclusion",
                 "observation_refs": ["O"], "conditions": {"tenant": "lab-a"}},
            ],
            "pages": [
                {"id": "ROOT", "kind": "flow", "title": "Reports", "record_refs": ["G"]},
                {"id": "P", "kind": "question", "title": "Report access", "record_refs": ["R"],
                 "parent_page_id": "ROOT", "blocks": [self.block]},
                {"id": "AUTO", "kind": "question", "title": "Record mirror", "record_refs": ["R"]},
            ],
        })

    def query(self, **options):
        return retrieve(self.root, "R1", "", ["P/B", "AUTO"], view="compact", **options)

    def test_native_result_matches_complete_evidence_projection(self):
        evidence = retrieve(self.root, "R1", "", ["P/B", "AUTO"])
        expected = finalize_context(Corpus(self.root, "R1"), evidence, view="compact")
        native = self.query()
        self.assertEqual(native, expected)

    def test_compact_does_not_decode_source_text_but_still_validates_knowledge(self):
        import wiki
        metrics, validation_packages = {}, []
        original = wiki.validate_block_knowledge

        def verify(corpus, key, package):
            validation_packages.append(copy.deepcopy(package))
            return original(corpus, key, package)

        with patch.object(wiki, "validate_block_knowledge", side_effect=verify):
            result = self.query(metrics=metrics)
        self.assertNotIn(self.payload, encode(result))
        self.assertEqual(metrics["counts"].get("source_text_expansions", 0), 0)
        self.assertEqual(metrics["counts"].get("packaged_raw_observations", 0), 0)
        self.assertGreater(metrics["counts"]["artifacts_verified"], 0)
        self.assertGreater(metrics["counts"]["observations_decoded"], 0)
        self.assertTrue(validation_packages)
        self.assertEqual(validation_packages[0]["observations"][0]["raw"]["response"]["body"], self.payload)
        self.assertFalse(any("content" in row for row in validation_packages[0]["artifacts"]))
        judgment = next(row for row in result["blocks"] if row["block_id"] == "B")
        self.assertIn("Counterevidence: the response denied access", judgment["text"])
        self.assertTrue(any(row.get("text_expanded") is False for row in result["blocks"]))
        self.assertTrue({"load", "index", "discovery", "package", "context_view", "verification"}
                        <= metrics["stages_ms"].keys())
        self.assertEqual(result, self.query())
        expanded_metrics = {}
        expanded = retrieve(self.root, "R1", "", ["P/B"], metrics=expanded_metrics)
        self.assertGreater(expanded_metrics["counts"]["source_text_expansions"], 0)
        self.assertIn(self.payload, [row.get("content") for row in expanded["artifacts"]])

    def test_cold_lexical_search_validates_knowledge_without_expanding_source_text(self):
        metrics = {}
        result = retrieve(self.root, "R1", "second identity", [], view="compact", metrics=metrics)
        self.assertIn("B", {row["block_id"] for row in result["blocks"]})
        self.assertEqual(metrics["counts"].get("source_text_expansions", 0), 0)
        self.assertGreater(metrics["counts"]["artifacts_verified"], 0)
        self.assertNotIn(self.payload, encode(result))

    def test_output_budget_admits_compact_source_closure_without_first_packing_raw(self):
        complete = self.query()
        limit = len(encode(complete)) + 2000
        self.assertLess(limit, len(self.payload))
        result = self.query(budget_chars=limit)
        self.assertNotEqual(result["status"], "unavailable")
        self.assertEqual({row["id"] for row in result["records"]}, {"G", "R"})
        self.assertEqual({row["id"] for row in result["observations"]}, {"O"})
        self.assertEqual({row["block_id"] for row in result["blocks"]},
                         {row["block_id"] for row in complete["blocks"]})
        self.assertLessEqual(len(encode(result)), limit)
        self.assertEqual(result["budget"]["used_chars"], len(encode(result)))
        self.assertFalse(result["omissions"])

    def test_compact_still_detects_tampered_source_and_does_not_advance_cursor(self):
        self.query(cursor="main")
        cursor = next((self.root / "cache").glob("context-*.json"))
        before = cursor.read_bytes()
        state = json.loads((self.root / "state.json").read_text())
        source_id = state["observations"]["O"]["source_artifact_id"]
        (self.root / state["artifacts"][source_id]["path"]).write_text("changed evidence", encoding="utf-8")
        result = self.query(cursor="main")
        self.assertFalse(result["delta"]["cursor_advanced"])
        self.assertEqual(cursor.read_bytes(), before)
        self.assertTrue(any(row["code"] == "artifact_hash_mismatch" for row in result["gaps"]))
        self.assertEqual(next(row for row in result["observations"] if row["id"] == "O")["status"], "unavailable")

    def test_comparison_reads_originals_without_inserting_them_into_compact_output(self):
        publish(self.root, "R1", {
            "observations": [{"id": "O2", "summary": "The second report response",
                "subject_refs": ["ENDPOINT"], "content": {
                    "actor_ref": "role-b", "request": {"method": "GET", "url": "/report"},
                    "response": {"status": 200, "body": "Different synthetic result"}}}],
            "records": [{"id": "R", "observation_refs": ["O", "O2"]}],
        })
        compact = self.query(cross_limit=10)
        full = retrieve(self.root, "R1", "", ["P/B", "AUTO"], cross_limit=10)
        self.assertTrue(compact["cross_candidates"])
        self.assertEqual(compact["cross_candidates"], full["cross_candidates"])
        self.assertTrue(all("raw" not in row for row in compact["observations"]))


if __name__ == "__main__":
    unittest.main()
