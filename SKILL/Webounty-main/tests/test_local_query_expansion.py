"""Regression cases for conservative, offline query expansion."""

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from query_expansion import expand_query
from search_index import _terms


class LocalQueryExpansionTests(unittest.TestCase):
    def expand(self, query):
        original = set(_terms(query))
        result = expand_query(query, _terms, original)
        self.assertTrue(original.isdisjoint(result))
        self.assertTrue(all(0 < weight < 1 for weight in result.values()))
        return result

    def test_chinese_natural_phrase_adds_english_terms(self):
        self.assertEqual(set(self.expand("普通成员下载他人的导出报告")),
                         {"download", "export", "report", "reports"})

    def test_english_casefold_and_chinese_translation(self):
        self.assertEqual(set(self.expand("DOWNLOAD exported file")), {"下载"})
        self.assertEqual(set(self.expand("download报告")), {"下载", "report", "reports"})
        self.assertEqual(set(self.expand("ｄｏｗｎｌｏａｄ")), {"下载"})

    def test_english_words_require_whole_word_matching(self):
        for query in ("downloader", "preexport", "cached", "sessions", "reporter"):
            with self.subTest(query=query):
                self.assertEqual(self.expand(query), {})

    def test_quoted_literals_and_code_are_not_expanded(self):
        for query in ('"download"', "'export'", '`下载`', '“导出”', '「报告」',
                      '```download report```', '"say \\"download\\""'):
            with self.subTest(query=query):
                self.assertEqual(self.expand(query), {})

    def test_paths_urls_and_identifiers_are_not_expanded(self):
        for query in ("/api/download", "api/export", r"C:\reports\download",
                      "https://example.test/download?mode=export", "/接口/下载",
                      "download_report", "download-report", "report.json",
                      "downloadReport", "DownloadReport", "download2",
                      "getDownload", "tenant_id"):
            with self.subTest(query=query):
                self.assertEqual(self.expand(query), {})

    def test_protected_span_does_not_disable_other_query_text(self):
        self.assertEqual(set(self.expand('"report" 下载 /api/export')), {"download"})

    def test_negation_original_terms_and_input_are_preserved(self):
        query = "cannot download 不可下载"
        original = set(_terms(query))
        before = original.copy()
        self.assertEqual(expand_query(query, _terms, original), {})
        self.assertEqual(original, before)
        self.assertIn("cannot", original)
        self.assertIn("不可", original)
        self.assertEqual(set(self.expand("不能下载")), {"download"})

    def test_unknown_terms_and_identity_inferences_do_not_expand(self):
        for query in ("quux", "普通账号", "成员身份", "authorization", "admin", "权限"):
            with self.subTest(query=query):
                self.assertEqual(self.expand(query), {})

    def test_group_budget_and_deterministic_result(self):
        result = self.expand("report")
        self.assertAlmostEqual(sum(result.values()), 0.3)
        self.assertEqual(result, self.expand("report report"))

    def test_no_recursive_expansion(self):
        def tokenizer(value):
            yield "report" if value == "下载" else value

        result = expand_query("download", tokenizer, {"download"})
        self.assertEqual(result, {"report": 0.3})


if __name__ == "__main__":
    unittest.main()
