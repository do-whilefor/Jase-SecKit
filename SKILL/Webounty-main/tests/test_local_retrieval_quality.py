"""Model-free recall, ordering, and persistent-index regression cases."""

from pathlib import Path
from contextlib import closing
import json
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lexical_proximity import pairs
from rag import Corpus, encode, retrieve
from search_index import rank
from session import start
from store import publish


def corpus(records):
    return SimpleNamespace(records={row["id"]: row for row in records}, entities={},
                           observations={}, blocks={}, pages={}, page_issues={},
                           observation=Mock(return_value={"raw": {}}))


class LocalRetrievalQualityTests(unittest.TestCase):
    def test_bilingual_recall_with_original_match_first(self):
        data = corpus([{"id": "EN", "summary": "report download"},
                       {"id": "ZH", "summary": "报告下载"},
                       {"id": "NOISE", "summary": "billing reconciliation"}])
        for query, first in (("报告下载", "ZH"), ("report download", "EN")):
            ranked, _, reasons = rank(data, query, [], with_reasons=True)
            self.assertEqual(ranked[0], ("record", first))
            self.assertEqual(set(ranked), {("record", "ZH"), ("record", "EN")})
            other = "EN" if first == "ZH" else "ZH"
            self.assertTrue(any(r["kind"] == "query_expansion" for r in reasons[("record", other)]))

    def test_ordered_neighbours_beat_equal_bag_of_words(self):
        data = corpus([{"id": "A", "summary": "download report alpha beta gamma"},
                       {"id": "B", "summary": "report alpha beta gamma download"},
                       {"id": "C", "summary": "report download alpha beta gamma"}])
        ranked, _, reasons = rank(data, "report download", [], with_reasons=True)
        self.assertEqual(ranked[0], ("record", "C"))
        self.assertTrue(any(r["kind"] == "ordered_proximity" for r in reasons[("record", "C")]))

    def test_phrase_signals_do_not_cross_sentences(self):
        data = corpus([{"id": "A", "summary": "租户隔离；下载报告"},
                       {"id": "B", "summary": "下载报告；租户隔离"}])
        self.assertEqual(rank(data, "下载报告", [])[0][0], ("record", "A"))
        # Same phrase in two sentences is equally relevant; stable ID breaks ties.
        self.assertFalse(pairs("report. download"))
        self.assertFalse(pairs("report\ndownload"))
        self.assertTrue(pairs("report download"))

    def test_exact_path_and_literals_do_not_expand(self):
        data = corpus([{"id": "PATH", "summary": "/api/download"},
                       {"id": "OTHER", "summary": "下载"}])
        for query in ("/api/download", '"download"', "`download`"):
            self.assertNotIn(("record", "OTHER"), rank(data, query, [])[0])

    def test_unknown_query_does_not_force_a_nearest_result(self):
        data = corpus([{"id": "R", "summary": "report download"}])
        self.assertEqual(rank(data, "unrecorded-opaque-error", [])[0], [])

    def test_negated_observation_is_retained(self):
        data = corpus([{"id": "YES", "summary": "member can download report"},
                       {"id": "NO", "summary": "member cannot download report"}])
        self.assertEqual(set(rank(data, "member cannot download report", [])[0]),
                         {("record", "YES"), ("record", "NO")})
        self.assertEqual(rank(data, "member cannot download report", [])[0][0], ("record", "NO"))

    def make_session(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        info = start("test-local-ranking", "研究目标", temporary.name)
        publish(info["root"], info["run_id"], {"records": [
            {"id": "R-EN", "kind": "Question", "summary": "report download alpha beta gamma", "status": "open"},
            {"id": "R-FAR", "kind": "Question", "summary": "report alpha beta gamma download", "status": "open"}]})
        return info

    def ranked(self, info, query, warm=False):
        with Corpus(info["root"], info["run_id"], lazy_pages=True, lazy_metadata=True) as data:
            if warm:
                with patch("search_index._fields", side_effect=AssertionError("warm query rebuilt text")):
                    return rank(data, query, [], with_reasons=True)
            return rank(data, query, [], with_reasons=True)

    def test_cold_warm_and_rebuilt_indexes_agree(self):
        info = self.make_session()
        first = self.ranked(info, "report download")
        self.assertEqual(first[0][0], ("record", "R-EN"))
        self.assertEqual(first, self.ranked(info, "report download", warm=True))
        translated = self.ranked(info, "报告下载", warm=True)
        self.assertIn(("record", "R-EN"), translated[0])
        shutil.rmtree(Path(info["root"]) / "cache")
        self.assertEqual(first, self.ranked(info, "report download"))

    def test_old_projection_version_rebuilds_and_changes_invalidate_pairs(self):
        info = self.make_session()
        with closing(sqlite3.connect(Path(info["root"]) / "cache/retrieval.sqlite")) as db:
            db.execute("UPDATE metadata SET value='3' WHERE name='format'")
            db.commit()
        first = self.ranked(info, "report download")
        self.assertEqual(first[0][0], ("record", "R-EN"))
        # External state edits must invalidate positions as well as term counts.
        path = Path(info["root"]) / "state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        state["records"]["R-EN"].update(summary="unrelated observation", revision=2)
        state["revision"] += 1
        path.write_text(encode(state), encoding="utf-8")
        self.assertNotIn(("record", "R-EN"), self.ranked(info, "report download")[0])

    def test_context_preserves_evidence_status_and_reports_expansion(self):
        info = self.make_session()
        result = retrieve(info["root"], info["run_id"], "报告下载", mode="lexical", view="compact")
        self.assertIn("R-EN", {row["id"] for row in result["records"]})
        self.assertEqual(result["chain_discovery"]["candidates"], [])
        self.assertTrue(result["retrieval_request"].get("ranking_version"))

    def test_generated_history_cannot_revive_a_changed_claim(self):
        info = self.make_session()
        publish(info["root"], info["run_id"], {"records": [
            {"id": "R-EN", "summary": "unrelated observation", "change_reason": "corrected subject"}]})
        self.assertNotIn(("record", "R-EN"), self.ranked(info, "report download")[0])
        self.assertEqual(self.ranked(info, "unrelated observation")[0][0], ("record", "R-EN"))

    def test_owner_edit_without_revision_invalidates_mirror_projection(self):
        info = self.make_session()
        self.ranked(info, "report download")
        path = Path(info["root"]) / "state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        state["records"]["R-EN"]["summary"] = "unrelated observation"
        path.write_text(encode(state), encoding="utf-8")
        # This record's generated title is its kind/ID; old body terms must go.
        self.assertNotIn(("record", "R-EN"), self.ranked(info, "report download")[0])

    def test_source_window_prefers_original_words_over_expansion_density(self):
        info = self.make_session()
        source = Path(info["project_root"]) / "original.txt"
        source.write_bytes("报告 下载 reports ".encode() + b" " * 70000 + b"report download")
        publish(info["root"], info["run_id"], {"observations": [
            {"id": "O-SOURCE", "source_path": str(source), "content": {"response": {"status": 200}}}]})
        with Corpus(info["root"], info["run_id"], lazy_pages=True) as data:
            self.assertIn(("observation", "O-SOURCE"), rank(data, "report download", [])[0])
            hit = data.retrieval_source_matches["O-SOURCE"]
            self.assertGreater(hit["offset"], 0)
            self.assertEqual(hit["matched_original_query_terms"], 2)
            self.assertFalse(hit["evidence"])


if __name__ == "__main__":
    unittest.main()
