"""Ranking behavior with opaque references, invalid pages and exact reads."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from search_index import rank


class SearchQualityTests(unittest.TestCase):
    def corpus(self, records=None, observations=None, blocks=None):
        return SimpleNamespace(records=records or {}, entities={}, observations=observations or {},
            blocks=blocks or {}, pages={"PAGE": {"page_id": "PAGE", "title": "Research"}},
            page_issues={}, observation=Mock(return_value={"status": "ready", "raw": {}}))

    def test_nested_reference_ids_do_not_become_lexical_claims(self):
        corpus = self.corpus(records={"CHAIN": {"id": "CHAIN", "kind": "Chain",
            "summary": "组合待复核", "steps": ["secretneedle"],
            "links": [{"producer_ref": "secretneedle", "consumer_ref": "R2",
                       "evidence_refs": ["secretneedle"], "note": "缺少实际消费记录"}]}},
            observations={"RAW": {"id": "RAW", "summary": "实际响应"}})
        corpus.observation.return_value = {"status": "ready", "raw": {
            "response": {"body": "server returned secretneedle"}}}
        ranked, _ = rank(corpus, "secretneedle", [])
        self.assertIn(("observation", "RAW"), ranked)
        self.assertNotIn(("record", "CHAIN"), ranked)
        self.assertIn(("record", "CHAIN"), rank(corpus, "实际消费", [])[0])

    def test_business_constraint_names_and_result_values_remain_searchable(self):
        corpus = self.corpus(records={"C": {"id": "C", "summary": "范围有限",
            "capability": {"provides": [{"type": "ticket", "constraints": {
                "audience": "artifact-service", "status": "disabled"}}]},
            "actual_result": {"status": "rejected", "reason": "wrong tenant"}}})
        for query in ("audience", "disabled", "rejected", "wrong tenant"):
            with self.subTest(query=query):
                self.assertIn(("record", "C"), rank(corpus, query, [])[0])

    def test_invalid_block_does_not_evict_ordinary_hit_but_is_addressable(self):
        block = {"page_id": "PAGE", "block_id": "BROKEN", "title": "artifact download",
                 "text": "artifact download", "_issues": [{"code": "block_hash_mismatch"}],
                 "source_refs": ["VALID"]}
        corpus = self.corpus(records={"VALID": {"id": "VALID", "summary": "artifact download response"}},
                             blocks={"PAGE/BROKEN": block})
        ranked, _ = rank(corpus, "artifact download", [])
        self.assertEqual(ranked[0], ("record", "VALID"))
        self.assertNotIn(("block", "PAGE/BROKEN"), ranked)
        self.assertIn(("block", "PAGE/BROKEN"), rank(corpus, "", ["PAGE/BROKEN"])[0])

    def test_exact_anchor_skips_unrelated_raw_observation_loading(self):
        corpus = self.corpus(records={"R-1": {"id": "R-1", "summary": "Target"}},
                             observations={f"O-{i}": {"id": f"O-{i}"} for i in range(100)})
        ranked, _ = rank(corpus, "", ["R-1"])
        self.assertEqual(ranked, [("record", "R-1")])
        corpus.observation.assert_not_called()

    def test_new_counterevidence_is_prominent_without_hiding_exact_history(self):
        corpus = self.corpus(records={
            "OLD": {"id": "OLD", "summary": "callback redirect host validation", "status": "refuted"},
            "NEW": {"id": "NEW", "summary": "新观察纠正了先前范围", "status": "observed",
                    "contradicts": ["OLD"]}})
        ranked, _, reasons = rank(corpus, "callback redirect", [], with_reasons=True)
        self.assertEqual(ranked[0], ("record", "NEW"))
        self.assertIn(("record", "OLD"), ranked)
        self.assertEqual(reasons[("record", "NEW")], [{"kind": "counterevidence_relation"}])
        self.assertEqual(rank(corpus, "", ["OLD"])[0][0], ("record", "OLD"))
        corpus.records["OLD"]["summary"] += " invoice"
        corpus.records["OTHER"] = {"id": "OTHER", "summary": "billing invoice monthly statement"}
        self.assertEqual(rank(corpus, "billing invoice", [])[0][0], ("record", "OTHER"))


if __name__ == "__main__":
    unittest.main()
