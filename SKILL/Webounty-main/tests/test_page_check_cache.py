"""Damaged navigation caches rebuild without hiding authoritative source errors."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rag import Corpus, RetrievalError
from store import publish


class PageCheckCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run_id = "RUN-CACHE"
        (self.root / "wiki").mkdir()
        (self.root / "state.json").write_text(json.dumps({
            "run_id": self.run_id, "revision": 1, "records": {}, "entities": {},
            "observations": {}, "artifacts": {}}), encoding="utf-8")
        (self.root / "wiki/manifest.json").write_text(json.dumps({
            "run_id": self.run_id, "pages": []}), encoding="utf-8")
        publish(self.root, self.run_id, {"records": [
            {"id": rid, "kind": "Question", "summary": "Review " + rid, "status": "open"}
            for rid in ("Q-A", "Q-B")]})
        self.cache = self.root / "cache/page-checks.json"
        self.saved = json.loads(self.cache.read_bytes())

    def update(self):
        metrics = {}
        publish(self.root, self.run_id, {"records": [
            {"id": "Q-A", "summary": "Review the next observation"}]}, metrics)
        rebuilt = json.loads(self.cache.read_bytes())
        with Corpus(self.root, self.run_id) as corpus:
            self.assertEqual(rebuilt["pages"]["WK-Q-B"]["check"], corpus.page_check("WK-Q-B"))
        return metrics["counts"]

    def test_truncated_json_and_invalid_encoding_rebuild(self):
        for data in (b"{", b"\xff"):
            with self.subTest(data=data):
                self.cache.write_bytes(data)
                counts = self.update()
                self.assertEqual(counts["pages_checked"], 2)
                self.assertEqual(counts.get("page_checks_reused", 0), 0)

    def test_wrong_cache_shapes_rebuild(self):
        bad_entries = [[], {"check": []}, {"check": {}},
                       {**self.saved["pages"]["WK-Q-B"], "check": {
                           **self.saved["pages"]["WK-Q-B"]["check"], "issues": [None]}},
                       {**self.saved["pages"]["WK-Q-B"], "check": {
                           **self.saved["pages"]["WK-Q-B"]["check"], "new_candidates": [{"kind": "record"}]}}]
        values = [[], None, {**self.saved, "pages": []}]
        values.extend({**self.saved, "pages": {"WK-Q-B": entry}} for entry in bad_entries)
        for value in values:
            with self.subTest(value=value):
                self.cache.write_text(json.dumps(value), encoding="utf-8")
                counts = self.update()
                self.assertEqual(counts["pages_checked"], 2)
                self.assertEqual(counts.get("page_checks_reused", 0), 0)

    def test_valid_unchanged_page_still_reuses_cache(self):
        counts = self.update()
        self.assertEqual(counts["pages_checked"], 1)
        self.assertEqual(counts["page_checks_reused"], 1)

    def test_cache_for_another_run_or_version_rebuilds(self):
        for field, value in (("run_id", "OTHER-RUN"), ("version", -1)):
            with self.subTest(field=field):
                self.cache.write_text(json.dumps({**self.saved, field: value}), encoding="utf-8")
                self.assertEqual(self.update()["pages_checked"], 2)

    def test_authoritative_damage_is_not_ignored(self):
        for relative in ("state.json", "wiki/manifest.json"):
            with self.subTest(relative=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.write_bytes(b"{")
                before = {name: (self.root / name).read_bytes()
                          for name in ("state.json", "wiki/manifest.json", "wiki/index.md", "cache/page-checks.json")}
                try:
                    with self.assertRaises((RetrievalError, json.JSONDecodeError)):
                        self.update()
                    self.assertEqual(before, {name: (self.root / name).read_bytes() for name in before})
                finally:
                    path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
