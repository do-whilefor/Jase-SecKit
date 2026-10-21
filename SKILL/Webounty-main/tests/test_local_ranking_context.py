"""Context and mirror ranking must improve relevance without hiding evidence."""

from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ranking_context import condition_signal, mirror_owner
from search_index import rank
from rag import retrieve
from store import publish


class LocalRankingContextTests(unittest.TestCase):
    def corpus(self, *, records=None, blocks=None, current=None):
        return SimpleNamespace(
            records=records or {}, entities={}, observations={}, blocks=blocks or {},
            pages={"PAGE": {"page_id": "PAGE", "title": "Research"}},
            page_issues={}, current_conditions=current or {},
            observation=Mock(return_value={"status": "ready", "raw": {}}))

    def mirror_corpus(self):
        return self.corpus(records={
            "OWNER": {"id": "OWNER", "revision": 2, "summary": "report retrieval response"},
            "OTHER": {"id": "OTHER", "revision": 1, "summary": "report retrieval assessment"}},
            blocks={"PAGE/COPY": {
                "page_id": "PAGE", "block_id": "COPY", "title": "report retrieval details",
                "text": "report retrieval response", "representation": "record",
                "source_refs": [{"id": "OWNER", "revision": 2}]}})

    def test_conditions_compare_only_requested_axes(self):
        corpus = self.corpus(current={"environment": "lab"})
        row = {"conditions": {"environment": "lab", "tenant": "unrequested"}}
        signal = condition_signal(corpus, ("record", "R"), row)
        self.assertEqual([item["constraint"] for item in signal["matched"]], ["environment"])
        self.assertFalse(signal["unknown"])
        self.assertGreater(signal["multiplier"], 1)
        self.assertLessEqual(signal["multiplier"], 1.15)

    def test_unknown_values_never_match_even_when_identical(self):
        for value in ("", "unknown", "unspecified", "not_recorded", "未知", "未记录"):
            with self.subTest(value=value):
                corpus = self.corpus(current={"environment": value})
                signal = condition_signal(corpus, ("record", "R"), {"conditions": {"environment": value}})
                self.assertFalse(signal["matched"])
                self.assertEqual(signal["multiplier"], 1)
                self.assertEqual(signal["unknown"][0]["constraint"], "environment")

    def test_missing_conditions_and_capability_constraints_remain_unknown(self):
        corpus = self.corpus(current={"actor_ref": "MEMBER"})
        row = {"capability": {"provides": [{"type": "token", "constraints": {"actor_ref": "MEMBER"}}]}}
        signal = condition_signal(corpus, ("record", "R"), row)
        self.assertFalse(signal["matched"])
        self.assertEqual(signal["multiplier"], 1)
        corpus.observation.assert_not_called()

    def test_block_conditions_override_inherited_page_conditions(self):
        corpus = self.corpus(current={"environment": "lab", "tenant": "T1"})
        corpus.pages["PAGE"]["conditions"] = {"environment": "old", "tenant": "T1"}
        row = {"page_id": "PAGE", "conditions": {"environment": "lab"}}
        signal = condition_signal(corpus, ("block", "PAGE/B"), row)
        self.assertEqual(len(signal["matched"]), 2)
        self.assertFalse(signal["conflicts"])

    def test_matching_conditions_rank_ahead_without_removing_conflicts(self):
        rows = {rid: {"id": rid, "summary": "report retrieval response", "conditions": conditions}
                for rid, conditions in (
                    ("A-CONFLICT", {"environment": "old"}),
                    ("B-UNKNOWN", {"environment": "unknown"}),
                    ("C-MATCH", {"environment": "lab"}))}
        corpus = self.corpus(records=rows, current={"environment": "lab"})
        ranked, _ = rank(corpus, "report retrieval", [])
        self.assertEqual(ranked[0], ("record", "C-MATCH"))
        self.assertIn(("record", "A-CONFLICT"), ranked)
        self.assertIn(("record", "B-UNKNOWN"), ranked)
        self.assertEqual(rank(corpus, "report retrieval", ["A-CONFLICT"])[0][0],
                         ("record", "A-CONFLICT"))

    def test_current_mirror_has_one_candidate_and_remains_explicitly_readable(self):
        corpus = self.mirror_corpus()
        self.assertEqual(mirror_owner(corpus, "PAGE/COPY"), ("record", "OWNER"))
        ranked, _ = rank(corpus, "report retrieval", [])
        self.assertIn(("record", "OWNER"), ranked)
        self.assertIn(("record", "OTHER"), ranked)
        self.assertNotIn(("block", "PAGE/COPY"), ranked)
        ranked, _ = rank(corpus, "", ["PAGE/COPY"])
        self.assertEqual(ranked[0], ("block", "PAGE/COPY"))

    def test_mirror_only_word_can_locate_its_current_owner(self):
        corpus = self.mirror_corpus()
        corpus.blocks["PAGE/COPY"]["title"] += " mirroronlyneedle"
        ranked, _ = rank(corpus, "mirroronlyneedle", [])
        self.assertIn(("record", "OWNER"), ranked)
        self.assertNotIn(("block", "PAGE/COPY"), ranked)

    def test_mirror_only_hit_inherits_current_owner_conditions(self):
        corpus = self.corpus(records={
            "A-CONFLICT": {"id": "A-CONFLICT", "revision": 1, "summary": "measured result",
                           "conditions": {"environment": "old"}},
            "Z-MATCH": {"id": "Z-MATCH", "revision": 1, "summary": "measured result",
                        "conditions": {"environment": "lab"}}},
            current={"environment": "lab"})
        for index, rid in enumerate(corpus.records):
            bid = "COPY-" + str(index)
            corpus.blocks["PAGE/" + bid] = {
                "page_id": "PAGE", "block_id": bid, "title": "mirroronlyneedle context",
                "text": "measured result", "representation": "record",
                "source_refs": [{"id": rid, "revision": 1}]}
        ranked, _, reasons = rank(corpus, "mirroronlyneedle", [], with_reasons=True)
        self.assertEqual(ranked, [("record", "Z-MATCH"), ("record", "A-CONFLICT")])
        matched = [item for item in reasons[("record", "Z-MATCH")]
                   if item["kind"] == "execution_conditions"]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["matched"][0]["constraint"], "environment")

    def test_stale_mirror_cannot_inherit_current_owner_conditions(self):
        corpus = self.mirror_corpus()
        corpus.current_conditions = {"environment": "lab"}
        corpus.records["OWNER"]["conditions"] = {"environment": "lab"}
        block = corpus.blocks["PAGE/COPY"]
        block["source_refs"][0]["revision"] = 1
        signal = condition_signal(corpus, ("block", "PAGE/COPY"), block)
        self.assertFalse(signal["matched"])
        self.assertEqual(signal["multiplier"], 1)
        self.assertEqual(signal["unknown"][0]["constraint"], "environment")

    def test_stale_unpinned_or_missing_mirror_owner_is_not_folded(self):
        for refs in ([{"id": "OWNER", "revision": 1}], ["OWNER"],
                     [{"id": "MISSING", "revision": 2}], [{"id": "OWNER"}]):
            with self.subTest(refs=refs):
                corpus = self.mirror_corpus()
                corpus.blocks["PAGE/COPY"]["source_refs"] = refs
                self.assertIsNone(mirror_owner(corpus, "PAGE/COPY"))
                ranked, _ = rank(corpus, "report retrieval", [])
                self.assertIn(("block", "PAGE/COPY"), ranked)

    def test_invalid_page_or_block_is_not_folded(self):
        for field in ("page", "block"):
            with self.subTest(field=field):
                corpus = self.mirror_corpus()
                if field == "page":
                    corpus.page_issues["PAGE"] = [{"code": "page_hash_mismatch"}]
                else:
                    corpus.blocks["PAGE/COPY"]["_issues"] = [{"code": "block_hash_mismatch"}]
                self.assertIsNone(mirror_owner(corpus, "PAGE/COPY"))

    def test_authored_or_semantically_extended_blocks_are_not_folded(self):
        for update in ({"representation": "authored"}, {"knowledge": {}},
                       {"required_block_refs": [{"page_id": "P", "block_id": "B"}]},
                       {"conditions": {"environment": "other"}}, {"role": "history"}):
            with self.subTest(update=update):
                corpus = self.mirror_corpus()
                corpus.blocks["PAGE/COPY"].update(update)
                self.assertIsNone(mirror_owner(corpus, "PAGE/COPY"))
        corpus = self.mirror_corpus()
        corpus.pages["PAGE"]["conditions"] = {"environment": "other"}
        self.assertIsNone(mirror_owner(corpus, "PAGE/COPY"))

    def test_mirror_metadata_check_does_not_reopen_wiki_or_raw_observations(self):
        corpus = self.mirror_corpus()
        corpus.ensure_page = Mock()
        self.assertEqual(mirror_owner(corpus, "PAGE/COPY"), ("record", "OWNER"))
        corpus.ensure_page.assert_not_called()
        corpus.observation.assert_not_called()

    def test_secondary_hit_also_brings_counterevidence_without_displacing_primary(self):
        corpus = self.corpus(records={
            "TOP": {"id": "TOP", "summary": "report retrieval response",
                    "keywords": ["report", "retrieval"]},
            "OLD": {"id": "OLD", "summary": "report archive limitation", "status": "refuted"},
            "NEW": {"id": "NEW", "summary": "fresh contradictory finding", "contradicts": ["OLD"]}})
        ranked, _, reasons = rank(corpus, "report retrieval", [], with_reasons=True)
        self.assertEqual(ranked[0], ("record", "TOP"))
        self.assertIn(("record", "NEW"), ranked)
        self.assertIn(("record", "OLD"), ranked)
        self.assertTrue(any(item["kind"] == "counterevidence_relation"
                            for item in reasons[("record", "NEW")]))

    def test_all_explicit_anchors_precede_adjacent_counterevidence(self):
        corpus = self.corpus(records={
            "A": {"id": "A", "summary": "first request"},
            "B": {"id": "B", "summary": "second request"},
            "NEW": {"id": "NEW", "summary": "competing result", "contradicts": ["A"]}})
        ranked, _ = rank(corpus, "", ["A", "B"])
        self.assertEqual(set(ranked[:2]), {("record", "A"), ("record", "B")})
        self.assertIn(("record", "NEW"), ranked)


class LocalRankingSessionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run_id = "RUN-RANKING"
        (self.root / "wiki").mkdir()
        (self.root / "state.json").write_text(json.dumps({
            "run_id": self.run_id, "revision": 1, "records": {}, "entities": {},
            "observations": {}, "artifacts": {}}), encoding="utf-8")
        (self.root / "wiki/manifest.json").write_text(json.dumps({
            "run_id": self.run_id, "pages": []}), encoding="utf-8")
        self.add({
            "entities": [{"id": "E-A", "kind": "endpoint"}],
            "observations": [{"id": "O-A", "subject_refs": ["E-A"],
                              "content": {"response": "original measured result"}}],
            "records": [{"id": "F-A", "kind": "Fact", "summary": "report retrieval response",
                         "subject_refs": ["E-A"], "observation_refs": ["O-A"]},
                        {"id": "S-B", "kind": "Step", "summary": "report retrieval assessment"}],
            "pages": [{"id": "P-COPY", "title": "mirroronlyneedle", "record_refs": ["F-A"]}]})

    def add(self, batch):
        return publish(self.root, self.run_id, batch)

    def retrieve(self, query, **kwargs):
        return retrieve(self.root, self.run_id, query, mode="lexical", **kwargs)

    def test_mirrors_do_not_consume_the_candidate_limit(self):
        self.add({"pages": [{"id": "P-COPY-" + str(index), "title": "report retrieval copy",
                              "record_refs": ["F-A"]} for index in range(4)]})
        result = self.retrieve("report retrieval", max_candidates=2)
        self.assertEqual({row["id"] for row in result["records"]}, {"F-A", "S-B"})
        self.assertFalse(result["blocks"])

    def test_mirror_only_hit_keeps_page_freshness_and_new_candidates(self):
        self.add({
            "observations": [{"id": "O-LATER", "subject_refs": ["E-A"],
                              "content": {"response": "new unrelated wording"}}],
            "records": [{"id": "F-LATER", "kind": "Fact", "summary": "subsequent measurement",
                         "subject_refs": ["E-A"], "observation_refs": ["O-LATER"]}]})
        result = self.retrieve("mirroronlyneedle")
        self.assertIn("F-LATER", {row["id"] for row in result["records"]})
        checks = {row["page_id"]: row for row in result["page_checks"]}
        self.assertIn("P-COPY", checks)
        self.assertIn("F-LATER", {row["id"] for row in checks["P-COPY"]["new_candidates"]})

    def test_tampered_mirror_cannot_transfer_its_only_hit_to_owner(self):
        self.assertIn("F-A", {row["id"] for row in self.retrieve("mirroronlyneedle")["records"]})
        page = self.root / "wiki/pages/P-COPY.md"
        page.write_bytes(page.read_bytes() + b"\nUnexpected edit\n")
        result = self.retrieve("mirroronlyneedle")
        self.assertNotIn("F-A", {row["id"] for row in result["records"]})
        explicit = self.retrieve("", anchors=["P-COPY/B-F-A"])
        self.assertIn("page_hash_mismatch", {row["code"] for row in explicit["gaps"]})
        self.assertFalse(explicit["blocks"])

    def test_folded_mirror_still_reports_tampered_original_evidence(self):
        self.retrieve("mirroronlyneedle")
        original = self.root / "evidence/O-A.jsonl"
        original.write_bytes(original.read_bytes().replace(b"original measured result", b"tampered measured result"))
        result = self.retrieve("mirroronlyneedle")
        self.assertIn("artifact_hash_mismatch", {row["code"] for row in result["gaps"]})


if __name__ == "__main__":
    unittest.main()
