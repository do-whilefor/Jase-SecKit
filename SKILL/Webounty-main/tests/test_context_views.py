"""Delivery views preserve judgments while source bytes remain explicitly readable."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from context_views import finalize_context
from rag import Corpus, encode, retrieve
from store import publish


class ContextViewsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "wiki").mkdir()
        state = {"run_id": "R1", "revision": 1, "session_id": "S1", "records": {},
                 "observations": {}, "entities": {}, "artifacts": {}}
        (self.root / "state.json").write_text(encode(state), encoding="utf-8")
        (self.root / "wiki/manifest.json").write_text(encode({"run_id": "R1", "pages": []}), encoding="utf-8")
        publish(self.root, "R1", {
            "records": [
                {"id": "G", "kind": "Goal", "status": "active", "summary": "download report"},
                {"id": "R", "kind": "Question", "status": "open", "summary": "download report conclusion",
                 "observation_refs": ["O"], "conditions": {"tenant": "lab-a"},
                 "limitations": "A second role remains untested", "contradicted_by": []},
                {"id": "OTHER", "kind": "Question", "status": "open", "summary": "independent login"},
            ],
            "observations": [{"id": "O", "summary": "The local demo returned a response",
                              "content": {"actor_ref": "lab-role", "request": {"method": "GET", "url": "/report"},
                                          "response": {"status": 403, "body": "large raw payload " * 1000}}}],
            "pages": [
                {"id": "ROOT", "kind": "flow", "title": "Reports", "record_refs": ["G"]},
                {"id": "P", "kind": "question", "title": "Download checks", "parent_page_id": "ROOT", "record_refs": ["R"],
                 "blocks": [{"id": "B", "title": "Judgment", "summary": "Can the report be downloaded?",
                             "text": "The observation does not establish access.\nOnly lab-a was tested.\nCounterevidence: access denied.",
                             "source_refs": ["R"]}]},
                {"id": "AUTO", "kind": "question", "title": "Record mirror", "record_refs": ["R"]},
            ],
        })

    def output(self, query="", anchors=("P/B",), **options):
        # Keep tests independent of the public retrieve wrapper's new arguments.
        original = retrieve(self.root, "R1", query, anchors)
        corpus = Corpus(self.root, "R1")
        return finalize_context(corpus, original, **options)

    def cursor_files(self):
        return sorted((self.root / "cache").glob("context-*.json"))

    def test_compact_keeps_complete_judgment_and_source_locator_without_raw_bytes(self):
        original = retrieve(self.root, "R1", "", ["P/B", "AUTO"])
        before = copy.deepcopy(original)
        compact = finalize_context(Corpus(self.root, "R1"), original)
        self.assertEqual(original, before)
        self.assertLess(len(encode(compact)), len(encode(original)))
        self.assertEqual(compact["mandatory_context"]["goal_refs"], ["G"])
        record = next(row for row in compact["records"] if row["id"] == "R")
        self.assertEqual(record["conditions"], {"tenant": "lab-a"})
        self.assertIn("untested", record["limitations"])
        block = next(row for row in compact["blocks"] if row["block_id"] == "B")
        self.assertIn("Counterevidence: access denied", block["text"])
        self.assertEqual(block["ancestry"], ["Reports", "Download checks"])
        self.assertEqual(block["read_ref"], "P/B")
        mirror = next(row for row in compact["blocks"] if row["page_id"] == "AUTO")
        self.assertNotIn("text", mirror)
        self.assertEqual(mirror["record_refs"], ["R"])
        observation = next(row for row in compact["observations"] if row["id"] == "O")
        self.assertNotIn("raw", observation)
        self.assertFalse(observation["raw_expanded"])
        self.assertEqual(observation["read_ref"], "O")
        self.assertEqual(observation["context"]["response_status"], 403)
        self.assertEqual(observation["provenance"]["line"], 1)
        self.assertEqual(compact["budget"]["used_chars"], len(encode(compact)))

    def test_evidence_without_cursor_preserves_original_contract(self):
        original = retrieve(self.root, "R1", "", ["R"])
        self.assertIs(finalize_context(Corpus(self.root, "R1"), original, view="evidence"), original)

    def test_repeat_cursor_sends_refs_and_no_fact_store(self):
        first = self.output(cursor="same conversation")
        second = self.output(cursor="same conversation")
        self.assertTrue(first["records"])
        self.assertFalse(second["records"])
        self.assertFalse(second["observations"])
        self.assertIn({"kind": "record", "id": "R"}, second["unchanged_refs"])
        self.assertLess(len(encode(second)), len(encode(first)))
        self.assertEqual(second["budget"]["used_chars"], len(encode(second)))
        saved = json.loads(self.cursor_files()[0].read_text())
        self.assertNotIn("large raw payload", encode(saved))
        self.assertNotIn("download report conclusion", encode(saved))
        self.assertTrue(all(set(row) <= {"content", "navigation", "dependencies"} for row in saved["delivered"].values()))

    def test_unrelated_global_revision_does_not_retransmit_old_facts(self):
        self.output(cursor="c")
        publish(self.root, "R1", {"records": [{"id": "OTHER", "summary": "independent login refined"}]})
        second = self.output(cursor="c")
        self.assertNotIn("R", {row["id"] for row in second["records"]})
        self.assertIn({"kind": "record", "id": "R"}, second["unchanged_refs"])

    def test_parent_rename_returns_navigation_change_without_repeating_judgment(self):
        self.output(cursor="c")
        publish(self.root, "R1", {"pages": [{"id": "ROOT", "title": "Updated reports"}]})
        second = self.output(cursor="c")
        self.assertFalse(any(row["block_id"] == "B" for row in second["blocks"]))
        change = next(row for row in second["delta"]["metadata_changes"] if row["id"] == "P/B")
        self.assertEqual(change["ancestry"], ["Updated reports", "Download checks"])
        self.assertNotIn("text", change)

    def test_new_counterevidence_marks_question_basis_and_retransmits_judgment(self):
        self.output(cursor="c")
        state = json.loads((self.root / "state.json").read_text())
        old_revision = state["records"]["R"]["revision"]
        publish(self.root, "R1", {"records": [{"id": "NEG", "kind": "Question", "status": "open",
                                             "summary": "The earlier assumption is disputed", "contradicts": ["R"]}]})
        second = self.output(cursor="c")
        self.assertIn("NEG", {row["id"] for row in second["records"]})
        record = next(row for row in second["records"] if row["id"] == "R")
        self.assertEqual(record["revision"], old_revision + 1)
        self.assertEqual(record["status"], "open")
        self.assertEqual(record["basis_status"], "needs_review")
        self.assertIn({"kind": "record", "id": "R", "change": "content"}, second["delta"]["changes"])

    def test_refresh_resets_old_nonmatching_deliveries(self):
        self.output(anchors=("OTHER",), cursor="c")
        self.output(cursor="c")
        refreshed = self.output(cursor="c", refresh=True)
        self.assertTrue(refreshed["records"])
        self.assertFalse(refreshed["unchanged_refs"])
        other = self.output(anchors=("OTHER",), cursor="c")
        self.assertIn("OTHER", {row["id"] for row in other["records"]})
        # Without refresh, an unrelated query does not forget or delete prior IDs.
        again = self.output(cursor="c")
        self.assertIn({"kind": "record", "id": "R"}, again["unchanged_refs"])
        self.assertNotIn("deleted", encode(again["delta"]))

    def test_required_block_counterevidence_retransmits_dependent_judgment(self):
        publish(self.root, "R1", {"pages": [{"id": "DEPENDENT", "kind": "question", "title": "Dependent judgment",
            "record_refs": ["R"], "blocks": [{"id": "D", "title": "Combined assessment", "source_refs": ["R"],
                "text": "This assessment depends on the other block's restrictions.",
                "required_block_refs": [{"page_id": "P", "block_id": "B"}]}]}]})
        self.output(anchors=("DEPENDENT/D",), cursor="c")
        publish(self.root, "R1", {"pages": [{"id": "P", "kind": "question", "title": "Download checks",
            "parent_page_id": "ROOT", "record_refs": ["R"], "blocks": [{"id": "B", "title": "Judgment",
                "text": "New counterevidence: the previously assumed condition is disproved.", "source_refs": ["R"]}]}]})
        result = self.output(anchors=("DEPENDENT/D",), cursor="c")
        self.assertIn("D", {row["block_id"] for row in result["blocks"]})
        self.assertIn({"kind": "block", "id": "DEPENDENT/D", "change": "dependencies"}, result["delta"]["changes"])

    def test_graph_candidates_and_paths_are_delivered_only_when_changed(self):
        original = retrieve(self.root, "R1", "", ["R"])
        original["chain_discovery"] = {
            "record_refs": ["R", "OTHER"], "issues": [],
            "candidates": [{"producer_ref": "R", "provide_index": 0, "consumer_ref": "OTHER", "need_index": 0,
                            "compatibility": "unknown", "evidence": False, "unknown_conditions": ["tenant"]}],
            "paths": [{"record_refs": ["R", "OTHER"], "evidence": False, "missing_preconditions": ["tenant"]}],
        }
        finalize_context(Corpus(self.root, "R1"), original, cursor="c")
        again = finalize_context(Corpus(self.root, "R1"), original, cursor="c")
        self.assertFalse(again["chain_discovery"]["candidates"])
        self.assertFalse(again["chain_discovery"]["paths"])
        revised = copy.deepcopy(original)
        revised["chain_discovery"]["candidates"][0]["compatibility"] = "incompatible"
        revised["chain_discovery"]["candidates"][0]["conflicts"] = ["tenant mismatch"]
        changed = finalize_context(Corpus(self.root, "R1"), revised, cursor="c")
        self.assertEqual(changed["chain_discovery"]["candidates"][0]["compatibility"], "incompatible")
        self.assertFalse(changed["chain_discovery"]["paths"])

    def test_unavailable_snapshot_does_not_advance_cursor(self):
        self.output(cursor="c")
        path = self.cursor_files()[0]
        saved = path.read_bytes()
        original = retrieve(self.root, "R1", "", ["OTHER"])
        original["status"] = "unavailable"
        original["gaps"].append({"code": "snapshot_changed"})
        result = finalize_context(Corpus(self.root, "R1"), original, cursor="c")
        self.assertFalse(result["delta"]["cursor_advanced"])
        self.assertEqual(path.read_bytes(), saved)

    def test_method_query_match_change_does_not_repeat_method_body(self):
        original = retrieve(self.root, "R1", "", ["R"])
        original["methods"] = [{"id": "METHOD", "content": "Keep current evidence and conditions together.",
                                "evidence": False, "matched_terms": ["report"], "selection": "query"}]
        finalize_context(Corpus(self.root, "R1"), original, cursor="c")
        original["methods"][0]["matched_terms"] = ["download"]
        result = finalize_context(Corpus(self.root, "R1"), original, cursor="c")
        self.assertFalse(result["methods"])
        change = next(row for row in result["delta"]["metadata_changes"] if row["kind"] == "method")
        self.assertEqual(change["matched_terms"], ["download"])
        self.assertNotIn("content", change)

    def test_changed_source_validity_is_visible_and_does_not_advance_cursor(self):
        self.output(cursor="c")
        path = self.cursor_files()[0]
        saved = path.read_bytes()
        original = retrieve(self.root, "R1", "", ["R"])
        original["observations"][0]["status"] = "unavailable"
        original["observations"][0]["issues"] = [{"code": "artifact_hash_mismatch"}]
        result = finalize_context(Corpus(self.root, "R1"), original, cursor="c")
        self.assertIn("R", {row["id"] for row in result["records"]})
        self.assertFalse(result["delta"]["cursor_advanced"])
        self.assertEqual(path.read_bytes(), saved)

    def test_over_budget_transformation_fails_explicitly_without_advancing(self):
        self.output(cursor="c")
        path = self.cursor_files()[0]
        saved = path.read_bytes()
        original = retrieve(self.root, "R1", "", ["R"])
        original["budget"]["limit_chars"] = 1024
        result = finalize_context(Corpus(self.root, "R1"), original, cursor="c", refresh=True)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["gaps"][0]["code"], "budget_exhausted")
        self.assertLessEqual(len(encode(result)), 1024)
        self.assertEqual(result["budget"]["used_chars"], len(encode(result)))
        self.assertGreater(result["budget"]["omitted_units"], 0)
        self.assertEqual(path.read_bytes(), saved)

    def test_cursor_scopes_evidence_and_compact_deliveries_separately(self):
        self.output(cursor="../same cursor")
        evidence = self.output(cursor="../same cursor", view="evidence")
        self.assertTrue(evidence["observations"][0]["raw"])
        self.assertEqual(len(self.cursor_files()), 2)
        self.assertTrue(all(path.parent == self.root / "cache" for path in self.cursor_files()))


if __name__ == "__main__":
    unittest.main()
