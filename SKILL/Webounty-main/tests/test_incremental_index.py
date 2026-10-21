"""Incremental index contracts: warm work, invalidation, hierarchy and raw recall."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rag import Corpus, digest, encode
from search_index import rank
from store import publish


class IncrementalIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "evidence").mkdir()
        (self.root / "wiki").mkdir()
        self.state = {"run_id": "R1", "session_id": "S1", "revision": 1,
                      "records": {}, "entities": {}, "observations": {}, "artifacts": {}}
        (self.root / "wiki/manifest.json").write_text(encode({"run_id": "R1", "pages": []}))

    def record(self, rid, summary, **extra):
        self.state["records"][rid] = {"id": rid, "revision": 1, "kind": "Question",
            "summary": summary, "status": "open", "subject_refs": [], **extra}

    def observation(self, oid, body):
        data = (encode({"observation_id": oid, "run_id": "R1", "response": {"body": body}}) + "\n").encode()
        path = "evidence/" + oid + ".jsonl"
        (self.root / path).write_bytes(data)
        self.state["artifacts"]["A-" + oid] = {"id": "A-" + oid, "path": path,
            "sealed": True, "kind": "evidence", "sha256": digest(data), "bytes": len(data)}
        self.state["observations"][oid] = {"id": oid, "revision": 1, "artifact_id": "A-" + oid,
            "line": 1, "content_hash": digest(data), "subject_refs": []}

    def save(self):
        (self.root / "state.json").write_text(encode(self.state))

    def corpus(self):
        return Corpus(self.root, "R1", lazy_pages=True)

    def test_warm_query_reuses_all_terms_and_does_not_open_raw_observations(self):
        self.record("R", "下载授权 /api/download", aliases=["ticket consumer"])
        self.observation("O", "metadata " + "padding " * 100 + " trailingpayload")
        self.save()
        cold = self.corpus()
        self.assertIn(("observation", "O"), rank(cold, "trailingpayload", [])[0])
        self.assertEqual(cold.retrieval_index_stats["indexed_documents"], 2)
        warm = self.corpus()
        with patch("search_index._fields", side_effect=AssertionError("unchanged text was rebuilt")), \
                patch.object(warm, "observation", side_effect=AssertionError("unmatched raw evidence was read")):
            self.assertIn(("record", "R"), rank(warm, "下载授权", [])[0])
        self.assertEqual(warm.retrieval_index_stats["indexed_documents"], 0)
        self.assertEqual(warm.retrieval_index_stats["tokenized_fields"], 0)

    def test_changed_record_and_deletion_update_only_affected_entries(self):
        for rid in ("ONE", "TWO", "THREE"):
            self.record(rid, "oldphrase")
        self.save()
        rank(self.corpus(), "oldphrase", [])
        self.state["records"]["ONE"].update(summary="newphrase", revision=2)
        del self.state["records"]["THREE"]
        self.save()
        changed = self.corpus()
        self.assertEqual(rank(changed, "newphrase", [])[0], [("record", "ONE")])
        self.assertEqual(changed.retrieval_index_stats["indexed_documents"], 1)
        self.assertEqual(changed.retrieval_index_stats["reused_documents"], 1)
        self.assertEqual(changed.retrieval_index_stats["deleted_documents"], 1)
        self.assertEqual(rank(self.corpus(), "oldphrase", [])[0], [("record", "TWO")])

    def test_cached_observation_is_invalidated_by_unregistered_file_edit(self):
        self.observation("O", "originalneedle")
        self.record("SOURCE", "observed response", observation_refs=["O"])
        self.save()
        rank(self.corpus(), "originalneedle", [])
        (self.root / "evidence/O.jsonl").write_text("edited originalneedle\n")
        changed = self.corpus()
        self.assertNotIn(("observation", "O"), rank(changed, "originalneedle", [])[0])
        self.assertEqual(changed.retrieval_index_stats["indexed_documents"], 1)
        package, _ = changed.package(record_ids=["SOURCE"])
        self.assertEqual(package["observations"][0]["status"], "unavailable")

    def publish_pages(self):
        self.record("R", "record source")
        self.save()
        publish(self.root, "R1", {"pages": [
            {"id": "P", "title": "租户隔离", "record_refs": [], "blocks": []},
            {"id": "C", "title": "验证结果", "parent_page_id": "P", "record_refs": ["R"],
             "questions": ["如何确认调用方权限"], "blocks": [
                 {"id": "B", "title": "独立结论", "text": "local block prose", "source_refs": ["R"]}]}]})

    def test_warm_wiki_lookup_uses_navigation_and_questions_without_opening_pages(self):
        self.publish_pages()
        rank(self.corpus(), "租户隔离", [])
        warm = self.corpus()
        with patch.object(warm, "ensure_page", side_effect=AssertionError("warm lookup read Wiki page")):
            self.assertIn(("block", "C/B"), rank(warm, "调用方权限", [])[0])
        self.assertEqual(warm.retrieval_index_stats["indexed_documents"], 0)

    def test_parent_rename_updates_descendant_terms_without_rewriting_child(self):
        self.publish_pages()
        rank(self.corpus(), "租户隔离", [])
        previous = (self.root / "wiki/pages/C.md").read_bytes()
        publication = publish(self.root, "R1", {"pages": [{"id": "P", "title": "下载授权"}]})
        changed = self.corpus()
        self.assertIn(("block", "C/B"), rank(changed, "下载授权", [])[0])
        self.assertNotIn(("block", "C/B"), rank(self.corpus(), "租户隔离", [])[0])
        self.assertEqual((self.root / "wiki/pages/C.md").read_bytes(), previous)
        self.assertEqual(publication["retrieval_index"]["indexed_documents"], 1)
        self.assertEqual(changed.retrieval_index_stats["indexed_documents"], 0)

    def test_tampered_wiki_drops_cached_lexical_hit_but_keeps_exact_diagnostic(self):
        self.publish_pages()
        rank(self.corpus(), "local block prose", [])
        path = self.root / "wiki/pages/C.md"
        path.write_text(path.read_text() + "unauthorized edit\n")
        changed = self.corpus()
        self.assertNotIn(("block", "C/B"), rank(changed, "local block prose", [])[0])
        self.assertIn(("block", "C/B"), rank(changed, "", ["C/B"])[0])
        package, issues = changed.package(block_keys=["C/B"])
        self.assertIsNone(package)
        self.assertTrue(any(issue["code"] == "page_hash_mismatch" for issue in issues))

    def test_deleted_projection_rebuilds_same_ranking_and_counterevidence(self):
        self.record("OLD", "callback redirect", status="refuted")
        self.record("NEW", "new limitation", contradicts=["OLD"])
        self.save()
        first = rank(self.corpus(), "callback redirect", [], with_exact=True, with_reasons=True)
        shutil.rmtree(self.root / "cache")
        rebuilt = rank(self.corpus(), "callback redirect", [], with_exact=True, with_reasons=True)
        self.assertEqual(first, rebuilt)
        self.assertEqual(first[0][0], ("record", "NEW"))

    def test_knowledge_fields_revalidate_when_source_artifact_changes(self):
        self.observation("O", "independent source response")
        self.record("R", "claim source", observation_refs=["O"])
        self.save()
        publish(self.root, "R1", {"pages": [{"id": "P", "title": "Research", "record_refs": ["R"],
            "blocks": [{"id": "B", "title": "Judgment", "text": "ordinary prose", "source_refs": ["R"],
                "knowledge": {"limitations": ["specificdiscriminator"], "supporting_refs": ["O"]}}]}]})
        self.assertIn(("block", "P/B"), rank(self.corpus(), "specificdiscriminator", [])[0])
        warm = self.corpus()
        self.assertIn(("block", "P/B"), rank(warm, "specificdiscriminator", [])[0])
        self.assertEqual(warm.retrieval_index_stats["indexed_documents"], 0)
        (self.root / "evidence/O.jsonl").write_text("tampered source\n")
        changed = self.corpus()
        self.assertNotIn(("block", "P/B"), rank(changed, "specificdiscriminator", [])[0])
        self.assertEqual(changed.retrieval_index_stats["indexed_documents"], 2)

    def test_navigation_does_not_hide_matching_other_branch(self):
        self.publish_pages()
        publish(self.root, "R1", {"pages": [{"id": "OTHER", "title": "通知流程", "record_refs": ["R"],
            "blocks": [{"id": "B", "title": "外部分支", "text": "租户隔离存在独立前提", "source_refs": ["R"]}]}]})
        ranked, _ = rank(self.corpus(), "租户隔离", [])
        self.assertIn(("block", "C/B"), ranked)
        self.assertIn(("block", "OTHER/B"), ranked)

    def test_changed_eager_snapshot_cannot_commit_old_text_with_new_file_signature(self):
        self.publish_pages()
        # This is the race: eager Corpus has already verified and cached old
        # bytes, but the index's following stat() observes the changed file.
        eager = Corpus(self.root, "R1")
        path = self.root / "wiki/pages/C.md"
        path.write_text(path.read_text() + "unregistered edit\n")
        rank(eager, "local block prose", [])
        self.assertTrue(eager.retrieval_index_stats["snapshot_changed"])
        fresh = self.corpus()
        self.assertNotIn(("block", "C/B"), rank(fresh, "local block prose", [])[0])
        self.assertGreater(fresh.retrieval_index_stats["indexed_documents"], 0)


if __name__ == "__main__":
    unittest.main()
