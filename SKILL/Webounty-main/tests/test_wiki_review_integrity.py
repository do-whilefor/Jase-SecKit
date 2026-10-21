"""Wiki navigation and knowledge views retain current source-integrity signals."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rag import Corpus
from session import start
from store import _index_section, publish
from wiki import knowledge


class WikiReviewIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        info = start("wiki-review", "Review synthetic evidence", temporary.name)
        self.root, self.run_id = Path(info["root"]), info["run_id"]

    def publish(self, batch, metrics=None):
        return publish(self.root, self.run_id, batch, metrics)

    def artifact_question(self, *, transitive=False):
        source = {"id": "Q", "kind": "Question", "status": "open",
                  "summary": "Inspect original", "artifact_refs": [{"artifact_id": "ART-O"}]}
        records = [source, {"id": "OTHER", "kind": "Question", "status": "open"},
                   {"id": "UNCHANGED", "kind": "Question", "status": "open"}]
        if transitive:
            source["id"] = "SOURCE"
            records.append({"id": "Q", "kind": "Question", "status": "open", "source_refs": ["SOURCE"]})
        self.publish({"observations": [{"id": "O", "content": {"response": {"status": 200}}}],
                      "records": records})
        return self.root / "evidence/O.jsonl"

    def test_question_statuses_select_the_expected_navigation_section(self):
        cases = {"open": "活动问题", "blocked": "活动问题", "needs_review": "活动问题",
                 "resolved": "事实与其他记录", "closed": "事实与其他记录",
                 "refuted": "负结果与关闭命题", "closed_for_conditions": "负结果与关闭命题"}
        for status, section in cases.items():
            with self.subTest(status=status):
                self.assertEqual(_index_section({"kind": "Question", "status": status}), section)

    def test_published_open_question_is_in_active_questions(self):
        self.publish({"records": [{"id": "Q", "kind": "Question", "status": "open",
                                   "summary": "Unresolved boundary"}]})
        index = (self.root / "wiki/index.md").read_text(encoding="utf-8")
        active = index.split("## 活动问题\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("pages/WK-Q.md", active)
        self.publish({"records": [{"id": "Q", "status": "resolved"}]})
        index = (self.root / "wiki/index.md").read_text(encoding="utf-8")
        active = index.split("## 活动问题\n", 1)[1].split("\n## ", 1)[0]
        self.assertNotIn("pages/WK-Q.md", active)

    def test_artifact_only_record_damage_and_repair_refresh_cached_navigation(self):
        self.assert_damage_and_repair_refresh_cached_navigation(transitive=False)

    def test_transitive_artifact_damage_and_repair_refresh_cached_navigation(self):
        self.assert_damage_and_repair_refresh_cached_navigation(transitive=True)

    def assert_damage_and_repair_refresh_cached_navigation(self, *, transitive):
        path = self.artifact_question(transitive=transitive)
        original = path.read_bytes()
        cache = self.root / "cache/page-checks.json"
        saved = json.loads(cache.read_bytes())
        self.assertEqual(saved["pages"]["WK-Q"]["evidence_paths"], ["evidence/O.jsonl"])
        for data, expected in ((b"{}\n", "review_required"), (original, "ready")):
            with self.subTest(status=expected):
                path.write_bytes(data)
                metrics = {}
                self.publish({"records": [{"id": "OTHER", "summary": "Refresh navigation"}]}, metrics)
                saved = json.loads(cache.read_bytes())
                check = saved["pages"]["WK-Q"]["check"]
                with Corpus(self.root, self.run_id) as corpus:
                    self.assertEqual(check, corpus.page_check("WK-Q"))
                self.assertEqual(check["status"], expected)
                self.assertGreaterEqual(metrics["counts"]["page_checks_reused"], 1)
                line = next(line for line in (self.root / "wiki/index.md").read_text(
                    encoding="utf-8").splitlines() if "(pages/WK-Q.md)" in line)
                self.assertEqual("页面待复核" in line, expected == "review_required")

    def test_transitive_artifact_damage_is_visible_in_page_check(self):
        path = self.artifact_question(transitive=True)
        path.write_bytes(b"{}\n")
        with Corpus(self.root, self.run_id) as corpus:
            check = corpus.page_check("WK-Q")
            self.assertEqual(check["status"], "review_required")
            self.assertIn("artifact_hash_mismatch", {issue["code"] for issue in check["issues"]})

    def test_missing_artifact_agrees_after_cache_rebuild(self):
        self.artifact_question().unlink()
        cache = self.root / "cache/page-checks.json"
        previous = None
        for rebuild in (False, True):
            with self.subTest(rebuild=rebuild):
                if rebuild:
                    cache.unlink()
                self.publish({"records": [{"id": "OTHER", "summary": "Refresh navigation"}]})
                check = json.loads(cache.read_bytes())["pages"]["WK-Q"]["check"]
                self.assertEqual(check["status"], "review_required")
                self.assertIn("artifact_missing", {issue["code"] for issue in check["issues"]})
                if previous is not None:
                    self.assertEqual(check, previous)
                previous = check

    def test_record_artifact_location_is_checked(self):
        self.artifact_question()
        with Corpus(self.root, self.run_id) as corpus:
            corpus.records["Q"]["artifact_refs"][0]["line"] = 99
            check = corpus.page_check("WK-Q")
            self.assertIn("artifact_location_missing", {issue["code"] for issue in check["issues"]})

    def source_question(self, content):
        source = self.directory / "original.bin"
        source.write_bytes(content)
        self.publish({"observations": [{"id": "O", "content": {"response": {"status": 200}},
                                        "source_path": str(source)}],
                      "records": [{"id": "Q", "kind": "Question", "status": "open",
                                   "observation_refs": ["O"]}],
                      "pages": [{"id": "P", "record_refs": ["Q"], "blocks": [
                          {"id": "B", "title": "Source limits", "text": "Inspect the original.",
                           "source_refs": ["Q"], "knowledge": {}}]}]})

    def test_knowledge_accepts_binary_original_and_still_detects_damage(self):
        self.source_question(b"\xff\x00\xfe")
        result = knowledge(self.root, self.run_id, ["P/B"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["artifacts"]["SRC-O"]["status"], "ready")
        (self.root / "evidence/O.source").write_bytes(b"changed")
        result = knowledge(self.root, self.run_id, ["P/B"])
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("artifact_hash_mismatch", {issue["code"] for issue in result["issues"]})

    def test_knowledge_does_not_materialize_unused_large_original(self):
        self.source_question(b"original evidence\n" * 40000)
        original = Corpus.artifact_data
        with patch.object(Corpus, "artifact_data", autospec=True, side_effect=original) as expanded:
            result = knowledge(self.root, self.run_id, ["P/B"])
        self.assertEqual(result["status"], "ready")
        self.assertNotIn("SRC-O", [call.args[1] for call in expanded.call_args_list])
        self.assertNotIn("content", result["artifacts"]["SRC-O"])


if __name__ == "__main__":
    unittest.main()
