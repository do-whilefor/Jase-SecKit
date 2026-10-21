"""Source windows must preserve real lexical terms and exact byte locations."""

import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evidence_io import text_chunks
from rag import Corpus
from search_index import _terms, rank
from session import start
from store import publish


class SourceChunkBoundaryTests(unittest.TestCase):
    def test_windows_never_invent_or_drop_lexical_terms(self):
        samples = [
            "",
            " " * 17 + "exporter other",
            "prefix " + "x" * 90 + "Tail /api/report_download next",
            " " * 17 + "ｅｘｐｏｒｔｅｒ trailing",
            "prefix " + "路径中文" * 20 + " end",
            " " * 16 + "报告 download 中文abc /v1/a-b.json",
            " " * 18 + "e\u0301xport tail",
            " " * 17 + "㎧x trailing",
            " " * 16 + "車報 done",
            "😀" * 7 + "exporter 👩‍💻 /api/report_download",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.txt"
            for source in samples:
                with self.subTest(source=source):
                    raw = source.encode("utf-8")
                    path.write_bytes(raw)
                    with patch("evidence_io.TEXT_CHUNK_BYTES", 19), patch("evidence_io.TEXT_OVERLAP_BYTES", 7):
                        windows = list(text_chunks(path))
                    terms = {term for _, body in windows for term in _terms(body)}
                    self.assertEqual(terms, set(_terms(source)))
                    covered = set()
                    for location, body in windows:
                        start, length = location["offset"], location["length"]
                        part = raw[start:start + length]
                        self.assertEqual(part.decode("utf-8"), body)
                        self.assertEqual(hashlib.sha256(part).hexdigest(), location["sha256"])
                        covered.update(range(start, start + length))
                    self.assertEqual(covered, set(range(len(raw))))

    def test_long_identifiers_and_boundary_words_match_in_cold_warm_and_rebuilt_index(self):
        with tempfile.TemporaryDirectory() as directory:
            info = start("chunk-boundaries", "inspect source boundaries", directory)
            source = Path(directory) / "source.txt"
            identifier = "token_" + "x" * 600 + "_tail"
            source.write_bytes(b" " * 65534 + b"exporter\n" + b" " * 65000 + identifier.encode())
            publish(info["root"], info["run_id"], {"observations": [
                {"id": "O-SOURCE", "source_path": str(source), "content": {"note": "original"}}]})
            for phase in ("cold", "warm", "rebuilt"):
                if phase in {"cold", "rebuilt"}:
                    shutil.rmtree(Path(info["root"]) / "cache")
                with self.subTest(phase=phase), Corpus(info["root"], info["run_id"], lazy_pages=True) as corpus:
                    for query in ("ex", "porter"):
                        self.assertNotIn(("observation", "O-SOURCE"), rank(corpus, query, [])[0])
                    for query in ("exporter", identifier):
                        self.assertIn(("observation", "O-SOURCE"), rank(corpus, query, [])[0])
                        match = corpus.retrieval_source_matches["O-SOURCE"]
                        artifact = corpus.artifacts[match["artifact_id"]]
                        raw = (Path(info["root"]) / artifact["path"]).read_bytes()
                        window = raw[match["offset"]:match["offset"] + match["length"]]
                        self.assertIn(query.encode(), window)
                        self.assertEqual(hashlib.sha256(window).hexdigest(), match["sha256"])

    def test_chinese_prose_remains_bounded_and_every_boundary_preserves_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.txt"
            path.write_text("报告下载" * 100000, encoding="utf-8")
            count = 0
            for location, body in text_chunks(path):
                count += 1
                self.assertLessEqual(location["length"], 65536 + 256 + 6)
                self.assertEqual(set(_terms(body)), {"报告", "告下", "下载", "载报"})
            self.assertGreater(count, 10)
            source = "head tenantReport /api/v1/report.json 报告下载 e\u0301xport tail"
            path.write_text(source, encoding="utf-8")
            for size in range(4, 40):
                with self.subTest(size=size), patch("evidence_io.TEXT_CHUNK_BYTES", size), patch("evidence_io.TEXT_OVERLAP_BYTES", 7):
                    actual = {term for _, body in text_chunks(path) for term in _terms(body)}
                    self.assertEqual(actual, set(_terms(source)))


if __name__ == "__main__":
    unittest.main()
