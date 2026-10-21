"""Query projections preserve current sources, relations and complete output."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from benchmark_retrieval import make_corpus, check_context, RUN_ID, QUERY, PRODUCER, CONSUMER, COUNTER
from change_impact import build_impact
from discovery import discover
from rag import Corpus, RetrievalError, retrieve
from search_index import rank
from session import read_ids
from store import publish


class MetadataCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        make_corpus(self.root, 80, 1024)

    def corpus(self, cached=True, metrics=None):
        corpus = Corpus(self.root, RUN_ID, lazy_pages=True, lazy_metadata=cached, metrics=metrics)
        self.addCleanup(corpus.close)
        return corpus

    def publish(self, batch, metrics=None):
        return publish(self.root, RUN_ID, batch, metrics=metrics)

    def test_warm_query_loads_only_needed_rows_without_opening_whole_json(self):
        metrics = {}
        with patch.object(Corpus, "read_json", side_effect=AssertionError("whole JSON reopened")):
            result = retrieve(self.root, RUN_ID, QUERY, [CONSUMER], view="compact", metrics=metrics)
        check_context(result)
        self.assertEqual(metrics["counts"]["metadata_cache_hits"], 1)
        self.assertLess(metrics["counts"]["metadata_rows_loaded"], 80)

    def test_projected_and_direct_queries_have_identical_complete_results(self):
        actual_init = Corpus.__init__

        def direct(corpus, *args, **kwargs):
            kwargs["lazy_metadata"] = False
            actual_init(corpus, *args, **kwargs)

        for query, anchors in ((QUERY, [CONSUMER]), ("", [CONSUMER]),
                               ("synthetic local", []), ("nothing_matches_here", [])):
            with self.subTest(query=query):
                indexed = retrieve(self.root, RUN_ID, query, anchors, view="compact")
                with patch.object(Corpus, "__init__", direct):
                    original = retrieve(self.root, RUN_ID, query, anchors, view="compact")
                self.assertEqual(indexed, original)

    def test_discovery_and_change_impact_match_direct_graph_including_counterevidence(self):
        for options in ({"anchors": [CONSUMER]}, {"changed": [COUNTER]}, {"query": "任务"}, {}):
            with self.subTest(options=options):
                indexed, original = self.corpus(), self.corpus(False)
                result = discover(indexed, **options)
                self.assertEqual(result, discover(original, **options))
                self.assertEqual(build_impact(indexed, [COUNTER], result),
                                 build_impact(original, [COUNTER], result))
                self.assertTrue(all(row["evidence"] is False for row in result["candidates"]))

    def test_changed_owner_removes_old_names_and_updates_new_relations(self):
        spec = {"type": "fresh-grant", "aliases": ["新的授权"], "constraints": {"tenant": "synthetic-demo"}}
        metrics = {}
        self.publish({"records": [{"id": PRODUCER, "capability": {"provides": [spec], "needs": []}}]}, metrics)
        current = self.corpus()
        self.assertNotIn((PRODUCER, 0), current.metadata.links("named_provides")["report reference"])
        self.assertIn((PRODUCER, 0), current.metadata.links("named_provides")["新的授权"])
        self.assertLess(metrics["counts"]["metadata_owners_indexed"], 10)
        self.assertEqual(discover(current, anchors=[CONSUMER]), discover(self.corpus(False), anchors=[CONSUMER]))

    def test_shared_capability_types_keep_cross_scope_conflict_diagnostics(self):
        records = []
        for number in range(80):
            spec = {"type": "shared-reference", "aliases": ["跨页引用"],
                    "constraints": {"tenant": "group-" + str(number // 10), "purpose": "export"}}
            records.append({"id": f"R-{number:04d}", "capability": {
                "provides": [] if number % 2 else [spec], "needs": [spec] if number % 2 else []}})
        self.publish({"records": records})
        indexed, original = self.corpus(), self.corpus(False)
        result = discover(indexed, anchors=[CONSUMER])
        self.assertEqual(result, discover(original, anchors=[CONSUMER]))
        self.assertTrue(any(row["compatibility"] == "incompatible" for row in result["candidates"]))
        self.assertTrue(all(row["evidence"] is False for row in result["candidates"]))

    def test_removed_blocks_and_renamed_ancestors_update_metadata(self):
        old = {bid for bid in self.corpus().blocks if bid.startswith("P-0001/")}
        self.publish({"pages": [{"id": "P-0001", "parent_page_id": "BRANCH-CONSUMER", "record_refs": [], "blocks": []},
                                {"id": "BRANCH-CONSUMER", "title": "New directory name"}]})
        current = self.corpus()
        self.assertFalse(old.intersection(current.blocks))
        self.assertEqual(current.navigation_paths["P-0001"][0], "New directory name")
        self.assertFalse(old.intersection(current.source_blocks([CONSUMER])))

    def test_external_state_edit_with_unchanged_revision_rebuilds_projection(self):
        path = self.root / "state.json"
        state = json.loads(path.read_text())
        state["records"][CONSUMER]["summary"] = "externalmetadataonlyneedle"
        path.write_text(json.dumps(state))
        current = self.corpus()
        self.assertEqual(current.records[CONSUMER]["summary"], "externalmetadataonlyneedle")
        self.assertIn(("record", CONSUMER), rank(current, "externalmetadataonlyneedle", [])[0])

    def test_reader_snapshot_stays_old_while_publication_advances_cache(self):
        reader = self.corpus()
        self.publish({"records": [{"id": CONSUMER, "summary": "newly published judgment"}]})
        self.assertNotEqual(reader.records[CONSUMER]["summary"], "newly published judgment")
        self.assertFalse(reader.stable())
        self.assertEqual(read_ids(reader, [CONSUMER])["status"], "unavailable")
        self.assertEqual(self.corpus().records[CONSUMER]["summary"], "newly published judgment")

    def test_deleted_cache_rebuilds_without_changing_answer(self):
        expected = retrieve(self.root, RUN_ID, QUERY, [CONSUMER], view="compact")
        shutil.rmtree(self.root / "cache")
        self.assertEqual(retrieve(self.root, RUN_ID, QUERY, [CONSUMER], view="compact"), expected)

    def test_tampered_original_is_unavailable_despite_reused_metadata(self):
        current = self.corpus()
        oid = "O-0001"
        aid = current.observations[oid]["artifact_id"]
        path = self.root / current.artifacts[aid]["path"]
        path.write_text(path.read_text().replace('"status":200', '"status":201'))
        result = read_ids(self.corpus(), [oid])
        self.assertNotEqual(result["status"], "ready")
        self.assertTrue(any(row["code"] == "artifact_hash_mismatch" for row in result["issues"]))

    def test_missing_manifest_does_not_reuse_old_pages_or_report_false_deletion(self):
        retrieve(self.root, RUN_ID, QUERY, [CONSUMER], view="compact", cursor="reader")
        (self.root / "wiki/manifest.json").unlink()
        result = retrieve(self.root, RUN_ID, QUERY, [CONSUMER], view="compact", cursor="reader")
        self.assertFalse(result.get("delta", {}).get("removed_refs"))
        self.assertTrue(any(row["code"] == "manifest_unavailable" for row in result["gaps"]))

    def test_reused_paths_still_enforce_session_boundary(self):
        current = self.corpus()
        self.assertEqual(current.path("evidence/../state.json"), self.root / "state.json")
        self.assertEqual(current.path("evidence/../state.json"), self.root / "state.json")
        with self.assertRaises(RetrievalError):
            current.path("../outside")

    def test_reused_paths_reject_symlink_outside_session(self):
        current = self.corpus()
        try:
            (self.root / "outside-link").symlink_to(self.root.parent, target_is_directory=True)
        except OSError as error:
            if getattr(error, "winerror", None) == 1314:
                self.skipTest("Windows account lacks symbolic-link privilege (WinError 1314)")
            raise
        with self.assertRaises(RetrievalError):
            current.path("outside-link/outside")


if __name__ == "__main__":
    unittest.main()
