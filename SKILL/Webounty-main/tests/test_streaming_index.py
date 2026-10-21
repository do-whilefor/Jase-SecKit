"""Publication visibility, disk-backed source retrieval and current-source checks."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evidence_io import TEXT_CHUNK_BYTES
from rag import Corpus, digest, encode, retrieve
from search_index import rank
from session import read_ids, start
from store import publish


class StreamingIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        owner = start("stream-tests", "Review local source observations", self.project)
        self.root, self.run_id = Path(owner["root"]), owner["run_id"]

    def add(self, batch):
        return publish(self.root, self.run_id, batch)

    def corpus(self):
        return Corpus(self.root, self.run_id, lazy_pages=True)

    def source(self):
        path = self.project / "responses.txt"
        with path.open("wb") as stream:
            # UTF-8 and a query term cross physical buffer boundaries.
            stream.write(b" " * (TEXT_CHUNK_BYTES - 7))
            stream.write("boundaryNeedle 权限复核\n".encode())
            for _ in range(24):
                stream.write(("normal response with local source detail\n" * 2048).encode())
            stream.write(b"finalsourceonlyneedle\n")
        return path

    def add_source(self, source):
        return self.add({"observations": [{"id": "O-SOURCE", "summary": "Local saved response body",
                    "source_path": str(source), "content": {"response": {"status": 200}}}],
                "records": [{"id": "F-SOURCE", "kind": "Fact", "status": "observed",
                    "summary": "Stored body for review", "observation_refs": ["O-SOURCE"]}]})

    def test_source_text_recall_range_and_rebuild_do_not_materialize_full_source(self):
        source = self.source()
        original = Corpus.read_bytes

        def no_full_source(corpus, relative):
            self.assertFalse(str(relative).endswith(".source"), "full source was materialized")
            return original(corpus, relative)

        with patch.object(Corpus, "read_bytes", no_full_source):
            publication = self.add_source(source)
            self.assertGreater(publication["retrieval_index"]["source_chunks_indexed"], 1)
            for query in ("finalsourceonlyneedle", "boundary needle", "权限复核"):
                result = retrieve(self.root, self.run_id, query, view="compact")
                observation = next(row for row in result["observations"] if row["id"] == "O-SOURCE")
                self.assertEqual(observation["status"], "ready")
                hit = observation["source_match"]
                self.assertFalse(hit["evidence"])
                expanded = read_ids(self.corpus(), [hit["artifact_id"]],
                                    offset=hit["offset"], length=hit["length"])
                body = expanded["package"]["artifacts"][0]
                self.assertEqual(body["range"]["sha256"], hit["sha256"])
                self.assertIn("finalsourceonlyneedle" if query.startswith("final") else
                              "boundaryNeedle" if query.startswith("boundary") else "权限复核", body["content"])
            shutil.rmtree(self.root / "cache")
            rebuilt = self.corpus()
            self.assertIn(("observation", "O-SOURCE"), rank(rebuilt, "finalsourceonlyneedle", [])[0])
            self.assertLessEqual(rebuilt.cached_bytes, rebuilt.CACHE_TOTAL_BYTES)

    def test_submission_updates_only_changed_rows_and_warm_queries_skip_document_signatures(self):
        self.add({"records": [{"id": f"S-{i}", "kind": "Step", "status": "active",
                                "summary": "originalphrase"} for i in range(40)]})
        result = self.add({"records": [{"id": "S-3", "summary": "changedphrase"}]})
        self.assertFalse(result["retrieval_index"]["full_reconciliation"])
        self.assertLess(result["retrieval_index"]["signature_checks"], 5)
        self.assertEqual(result["retrieval_index"]["indexed_documents"], 2)
        with patch("retrieval_index._Signatures.document", side_effect=AssertionError("full signature sweep")):
            corpus = self.corpus()
            self.assertIn(("record", "S-3"), rank(corpus, "changedphrase", [])[0])
        self.assertEqual(corpus.retrieval_index_stats["signature_checks"], 0)
        self.assertNotIn(("record", "S-3"), rank(self.corpus(), "originalphrase", [])[0])

    def test_removed_block_and_old_terms_are_retired_at_publication(self):
        self.add({"pages": [{"id": "P", "title": "Research notes", "record_refs": [], "blocks": [
            {"id": "OLD", "title": "Old note", "text": "obsoleteonlyneedle", "source_refs": []}]}]})
        retrieve(self.root, self.run_id, "obsoleteonlyneedle", view="compact", cursor="reader")
        different = retrieve(self.root, self.run_id, "unrelated query", view="compact", cursor="reader")
        self.assertFalse(different["delta"].get("removed_refs"))
        result = self.add({"pages": [{"id": "P", "title": "Research notes", "record_refs": [], "blocks": [
            {"id": "NEW", "title": "New note", "text": "currentonlyneedle", "source_refs": []}]}]})
        self.assertEqual(result["retrieval_index"]["deleted_documents"], 1)
        self.assertFalse(rank(self.corpus(), "obsoleteonlyneedle", [])[0])
        self.assertIn(("block", "P/NEW"), rank(self.corpus(), "currentonlyneedle", [])[0])
        updated = retrieve(self.root, self.run_id, "currentonlyneedle", view="compact", cursor="reader")
        self.assertEqual([row["id"] for row in updated["delta"]["removed_refs"]], ["P/OLD"])
        repeated = retrieve(self.root, self.run_id, "currentonlyneedle", view="compact", cursor="reader")
        self.assertFalse(repeated["delta"].get("removed_refs"))

    def test_missing_manifest_cannot_retire_previously_delivered_blocks(self):
        self.add({"pages": [{"id": "P", "title": "Saved note", "record_refs": [], "blocks": [
            {"id": "B", "title": "Note", "text": "savedonlyneedle", "source_refs": []}]}]})
        retrieve(self.root, self.run_id, "savedonlyneedle", view="compact", cursor="reader")
        (self.root / "wiki/manifest.json").unlink()
        result = retrieve(self.root, self.run_id, "G-001", view="compact", cursor="reader")
        self.assertFalse(result["delta"].get("removed_refs"))

    def test_tampered_large_source_loses_cached_hits_and_range_is_unavailable(self):
        self.add_source(self.source())
        source = self.root / "evidence/O-SOURCE.source"
        with source.open("r+b") as stream:
            stream.write(b"x")
        corpus = self.corpus()
        self.assertNotIn(("observation", "O-SOURCE"), rank(corpus, "finalsourceonlyneedle", [])[0])
        read = read_ids(self.corpus(), ["SRC-O-SOURCE"], offset=0, length=20)
        artifact = read["package"]["artifacts"][0]
        self.assertEqual(artifact["status"], "unavailable")
        self.assertNotIn("content", artifact)
        self.assertTrue(any(issue["code"] == "artifact_hash_mismatch" for issue in read["issues"]))

    def test_external_state_change_is_reconciled_without_trusting_cached_revision(self):
        self.add({"records": [{"id": "S", "kind": "Step", "status": "active", "summary": "oldneedle"}]})
        path = self.root / "state.json"
        import json
        state = json.loads(path.read_text())
        state["records"]["S"].update(summary="externalnewneedle", revision=2)
        path.write_text(encode(state))
        corpus = self.corpus()
        self.assertIn(("record", "S"), rank(corpus, "externalnewneedle", [])[0])
        self.assertTrue(corpus.retrieval_index_stats["full_reconciliation"])
        self.assertNotIn(("record", "S"), rank(self.corpus(), "oldneedle", [])[0])

    def test_identifier_components_and_unicode_width_are_searchable(self):
        self.add({"records": [{"id": "S", "kind": "Step", "status": "active",
                    "summary": "downloadToken requires ＲＥＰＯＲＴ permission"}]})
        for query in ("download token", "report", "ｄｏｗｎｌｏａｄＴｏｋｅｎ"):
            self.assertIn(("record", "S"), rank(self.corpus(), query, [])[0])

    def test_source_revision_marks_dependent_capability_and_finding_for_review(self):
        from discovery import discover
        self.add({"observations": [{"id": "O", "content": {"response": {"body": {"handle": "fixture-handle"}}}}],
                  "records": [
                      {"id": "F", "kind": "Fact", "status": "observed", "summary": "Observed local handle",
                       "observation_refs": ["O"]},
                      {"id": "CAP", "kind": "Capability", "status": "verified", "source_refs": ["F"],
                       "capability": {"provides": [{"type": "resource-handle"}], "needs": []}},
                      {"id": "FIND", "kind": "Finding", "status": "candidate", "source_refs": ["CAP"]},
                      {"id": "USE", "kind": "Step", "status": "active", "source_refs": ["F"],
                       "capability": {"provides": [], "needs": [{"type": "resource-handle"}]}}
                  ]})
        result = self.add({"records": [{"id": "F", "summary": "Handle conditions require a new review",
                    "change_reason": "Current source interpretation changed."}]})
        self.assertEqual(set(result["needs_review_record_ids"]), {"CAP", "FIND", "USE"})
        corpus = self.corpus()
        self.assertEqual(corpus.records["CAP"]["status"], "needs_review")
        self.assertEqual(corpus.records["FIND"]["status"], "needs_review")
        self.assertEqual(corpus.records["F"]["status"], "observed")
        edges = [edge for edge in discover(corpus, anchors=["USE"])["candidates"]
                 if edge["producer_ref"] == "CAP"]
        self.assertTrue(edges)
        self.assertTrue(all(edge["producer_usable"] is False for edge in edges))

    def test_more_than_twelve_thousand_metadata_items_remain_readable(self):
        import json
        path = self.root / "state.json"
        state = json.loads(path.read_text())
        state["entities"] = {f"E-{i}": {"id": f"E-{i}", "revision": 1,
                            "kind": "endpoint", "summary": "local fixture"} for i in range(12010)}
        path.write_text(encode(state))
        self.assertEqual(len(self.corpus().entities), 12010)

    def test_inline_observation_larger_than_sixteen_mib_with_line_reference(self):
        body = "local data " * (17 * 1024 * 1024 // 11) + " inlineendneedle"
        self.add({"observations": [{"id": "O-INLINE", "content": {"response": {"status": 200, "body": body}}}],
                  "records": [{"id": "F-INLINE", "kind": "Fact", "status": "observed",
                               "observation_refs": ["O-INLINE"],
                               "artifact_refs": [{"artifact_id": "ART-O-INLINE", "line": 1}]}]})
        result = retrieve(self.root, self.run_id, "inlineendneedle", view="compact")
        self.assertTrue(any(row["id"] == "O-INLINE" and row["status"] == "ready" for row in result["observations"]))
        self.assertLess(len(encode(result)), 20000)
        corpus = self.corpus()
        corpus.observation("O-INLINE")
        self.assertNotIn("O-INLINE", corpus.obs_cache)
        self.assertIsNone(corpus.artifact("ART-O-INLINE")["data"])

    def test_range_preserves_partial_utf8_bytes_without_fabricating_text(self):
        source = self.project / "utf8.txt"
        source.write_text("权限", encoding="utf-8")
        self.add_source(source)
        result = read_ids(self.corpus(), ["SRC-O-SOURCE"], offset=1, length=2)
        artifact = result["package"]["artifacts"][0]
        import base64
        self.assertEqual(artifact["encoding"], "base64")
        self.assertEqual(base64.b64decode(artifact["content"]), "权".encode()[1:])


if __name__ == "__main__":
    unittest.main()
