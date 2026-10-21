"""Evidence provenance and source locators must survive indexing and reuse."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evidence_io import text_chunks
from rag import Corpus, encode, retrieve
from search_index import rank
from session import read_ids, start
from store import publish


class EvidenceIntegrityTests(unittest.TestCase):
    def make_session(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        info = start("evidence-integrity", "Check source evidence", temporary.name)
        first = Path(temporary.name) / "first.txt"
        second = Path(temporary.name) / "second.txt"
        first.write_bytes(b"firstneedle " + b" " * 70000 + "末尾 secondneedle".encode())
        second.write_bytes(b"unrelated thirdneedle")
        publish(info["root"], info["run_id"], {"observations": [
            {"id": "O-FIRST", "source_path": str(first), "content": {"response": {"status": 200}}},
            {"id": "O-SECOND", "source_path": str(second), "content": {"response": {"status": 403}}},
            {"id": "O-INLINE", "content": {"response": {"body": "inline evidence"}}},
        ]})
        return info

    def edit_state(self, info, change):
        path = Path(info["root"]) / "state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        change(state)
        path.write_text(encode(state), encoding="utf-8")

    def assert_source_mismatch(self, info):
        with Corpus(info["root"], info["run_id"], lazy_pages=True) as corpus:
            row = corpus.observation("O-FIRST")
            self.assertEqual(row["status"], "unavailable")
            self.assertIsNone(row["raw"])
            self.assertIn("observation_source_mismatch", {issue["code"] for issue in row["issues"]})
            self.assertEqual(list(corpus.source_chunks("O-FIRST")), [])

    def test_published_sources_and_inline_observations_remain_ready(self):
        info = self.make_session()
        with Corpus(info["root"], info["run_id"], lazy_pages=True) as corpus:
            for oid in ("O-FIRST", "O-SECOND", "O-INLINE"):
                self.assertEqual(corpus.observation(oid)["status"], "ready")

    def test_index_cannot_rebind_observation_to_another_valid_original(self):
        info = self.make_session()
        self.edit_state(info, lambda state: state["observations"]["O-FIRST"].update(
            source_artifact_id="SRC-O-SECOND"))
        self.assert_source_mismatch(info)

    def test_index_cannot_silently_drop_original_binding(self):
        info = self.make_session()
        self.edit_state(info, lambda state: state["observations"]["O-FIRST"].pop("source_artifact_id"))
        self.assert_source_mismatch(info)

    def test_index_cannot_attach_an_undeclared_original_to_inline_observation(self):
        info = self.make_session()
        self.edit_state(info, lambda state: state["observations"]["O-INLINE"].update(
            source_artifact_id="SRC-O-SECOND"))
        with Corpus(info["root"], info["run_id"], lazy_pages=True) as corpus:
            row = corpus.observation("O-INLINE")
            self.assertEqual(row["status"], "unavailable")
            self.assertIn("observation_source_mismatch", {issue["code"] for issue in row["issues"]})
            self.assertEqual(list(corpus.source_chunks("O-INLINE")), [])

    def test_original_binding_checks_hash_even_if_artifact_metadata_was_updated(self):
        info = self.make_session()
        source = Path(info["root"]) / "evidence/O-FIRST.source"
        replacement = b"altered capture"
        source.write_bytes(replacement)
        self.edit_state(info, lambda state: state["artifacts"]["SRC-O-FIRST"].update(
            bytes=len(replacement), sha256=hashlib.sha256(replacement).hexdigest()))
        self.assert_source_mismatch(info)

    def test_original_binding_checks_registered_path(self):
        info = self.make_session()
        root = Path(info["root"])
        (root / "evidence/copied.source").write_bytes((root / "evidence/O-FIRST.source").read_bytes())
        self.edit_state(info, lambda state: state["artifacts"]["SRC-O-FIRST"].update(
            path="evidence/copied.source"))
        self.assert_source_mismatch(info)

    def test_query_reuse_refreshes_and_clears_source_locator(self):
        info = self.make_session()
        with Corpus(info["root"], info["run_id"], lazy_pages=True) as corpus:
            rank(corpus, "firstneedle", [])
            first = corpus.observation("O-FIRST")
            self.assertEqual(first["source_match"]["offset"], 0)
            rank(corpus, "secondneedle", [])
            second = corpus.observation("O-FIRST")
            self.assertGreater(second["source_match"]["offset"], 0)
            self.assertFalse(second["source_match"]["evidence"])
            rank(corpus, "", ["O-FIRST"])
            self.assertNotIn("source_match", corpus.observation("O-FIRST"))
            rank(corpus, "firstneedle", [])
            rank(corpus, "unrecordedneedle", [])
            self.assertNotIn("source_match", corpus.observation("O-FIRST"))
            # Later queries must not mutate evidence already delivered to a caller.
            self.assertEqual(first["source_match"]["offset"], 0)

    def test_invalid_source_has_no_locator_and_cannot_advance_delivery_cursor(self):
        info = self.make_session()
        retrieve(info["root"], info["run_id"], "firstneedle", mode="lexical", view="compact")
        self.edit_state(info, lambda state: state["observations"]["O-FIRST"].update(
            source_artifact_id="SRC-O-SECOND"))
        result = retrieve(info["root"], info["run_id"], "thirdneedle", anchors=["O-FIRST"],
                          mode="lexical", view="compact", cursor="source-integrity")
        row = next(row for row in result["observations"] if row["id"] == "O-FIRST")
        self.assertEqual(row["status"], "unavailable")
        self.assertNotIn("source_match", row)
        self.assertFalse(result["delta"]["cursor_advanced"])

    def test_source_match_roundtrips_to_hash_verified_bytes(self):
        info = self.make_session()
        result = retrieve(info["root"], info["run_id"], "secondneedle", mode="lexical", view="compact")
        row = next(row for row in result["observations"] if row["id"] == "O-FIRST")
        hit = row["source_match"]
        with Corpus(info["root"], info["run_id"], lazy_pages=True) as corpus:
            read = read_ids(corpus, [hit["artifact_id"]], offset=hit["offset"], length=hit["length"])
        self.assertEqual(read["status"], "ready")
        window = read["package"]["artifacts"][0]
        self.assertEqual(window["range"]["sha256"], hit["sha256"])
        self.assertIn("secondneedle", window["content"])
        self.assertFalse(hit["evidence"])

    def test_source_validation_does_not_decode_large_observation_twice(self):
        info = self.make_session()
        source = Path(info["project_root"]) / "large.txt"
        source.write_bytes(b"original large source")
        publish(info["root"], info["run_id"], {"observations": [{
            "id": "O-LARGE", "source_path": str(source),
            "content": {"response": {"body": "x" * (Corpus.CACHE_FILE_BYTES + 1)}}}]})
        metrics = {}
        with Corpus(info["root"], info["run_id"], lazy_pages=True, metrics=metrics) as corpus:
            self.assertEqual(corpus.observation("O-LARGE")["status"], "ready")
            self.assertNotIn("O-LARGE", corpus.obs_cache)
            decoded = metrics["counts"]["observations_decoded"]
            self.assertTrue(list(corpus.source_chunks("O-LARGE")))
            self.assertEqual(metrics["counts"]["observations_decoded"], decoded)
            corpus.release_observation("O-LARGE")
            self.assertNotIn("O-LARGE", corpus.observation_status)

    def test_utf8_chunk_locators_preserve_exact_source_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "utf8.txt"
            raw = ("alpha 中文证据🙂\r\n" * 30).encode()
            path.write_bytes(raw)
            with patch("evidence_io.TEXT_CHUNK_BYTES", 19), patch("evidence_io.TEXT_OVERLAP_BYTES", 7):
                chunks = list(text_chunks(path))
            covered = set()
            for locator, text in chunks:
                start = locator["offset"]
                stop = start + locator["length"]
                self.assertEqual(text.encode(), raw[start:stop])
                self.assertEqual(locator["sha256"], hashlib.sha256(raw[start:stop]).hexdigest())
                covered.update(range(start, stop))
            self.assertEqual(covered, set(range(len(raw))))


if __name__ == "__main__":
    unittest.main()
