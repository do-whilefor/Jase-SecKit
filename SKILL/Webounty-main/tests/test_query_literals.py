"""Literal spelling must survive query stop-word filtering and index reuse."""

from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rag import Corpus
from search_index import query_terms, rank
from session import start
from store import publish


class QueryLiteralTests(unittest.TestCase):
    def test_all_supported_quote_styles_preserve_literal_function_words(self):
        data = SimpleNamespace(records={"R": {"id": "R", "summary": "is"}},
                               entities={}, observations={}, blocks={}, pages={}, page_issues={})
        for quoted in ('"is"', "'is'", '`is`', '“is”', '‘is’', '「is」', '『is』',
                       '＂is＂', '｢is｣', '```\nis\n```', '"say \\"is\\""'):
            with self.subTest(quoted=quoted):
                self.assertIn(("record", "R"), rank(data, quoted + " absentneedle", [])[0])
        self.assertEqual(rank(data, "is absentneedle", [])[0], [])

    def test_paths_and_identifiers_keep_their_components(self):
        for literal in (r"C:\to\report", r"folder\to\report", "/接口/to/report",
                        "https://example.test/to/report", "for_each", "for-each",
                        "for.each", "forEach", "ForEach"):
            with self.subTest(literal=literal):
                expected = "to" if "to" in literal else "for"
                self.assertIn(expected, query_terms(literal + " absentneedle"))

    def test_literal_protection_does_not_restore_surrounding_noise(self):
        for literal, expected in ((r'"say \"quoted\" is"', "is"),
                                  ("＂ｉｓ＂", "is"),
                                  ("Ｃ：＼ｔｏ＼ｒｅｐｏｒｔ", "to"),
                                  ("ｆｏｒＥａｃｈ", "for")):
            with self.subTest(literal=literal):
                terms = query_terms(f"please {literal} and absentneedle")
                self.assertIn(expected, terms)
                self.assertIn("absentneedle", terms)
                self.assertTrue(terms.isdisjoint({"please", "and"}))

    def test_mixed_query_expands_only_natural_language(self):
        data = SimpleNamespace(records={
            "LITERAL": {"id": "LITERAL", "summary": "is"},
            "TRANSLATED": {"id": "TRANSLATED", "summary": "download"},
            "EXPANDED_LITERAL": {"id": "EXPANDED_LITERAL", "summary": "报告"},
            "NOISE": {"id": "NOISE", "summary": "please and"},
        }, entities={}, observations={}, blocks={}, pages={}, page_issues={})
        ranked, _, reasons = rank(data, "please ＂ｉｓ ｒｅｐｏｒｔ＂ 下载 and absentneedle",
                                  [], with_reasons=True)
        self.assertEqual(set(ranked), {("record", "LITERAL"), ("record", "TRANSLATED")})
        self.assertIn({"kind": "query_expansion", "matched_terms": ["download"]},
                      reasons[("record", "TRANSLATED")])

    def test_cold_warm_and_rebuilt_literal_queries_agree(self):
        with tempfile.TemporaryDirectory() as temporary:
            info = start("query-literals", "synthetic query checks", temporary)
            publish(info["root"], info["run_id"], {"records": [
                {"id": "R-LITERAL", "kind": "Question", "summary": "is", "status": "open"}]})

            def search():
                with Corpus(info["root"], info["run_id"], lazy_pages=True, lazy_metadata=True) as data:
                    return rank(data, "‘is’ absentneedle", [], with_reasons=True)

            shutil.rmtree(Path(info["root"]) / "cache")
            first = search()
            self.assertIn(("record", "R-LITERAL"), first[0])
            with patch("search_index._fields", side_effect=AssertionError("warm query rebuilt text")):
                self.assertEqual(search(), first)
            shutil.rmtree(Path(info["root"]) / "cache")
            self.assertEqual(search(), first)


if __name__ == "__main__":
    unittest.main()
