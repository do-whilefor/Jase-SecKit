"""Navigation and authored retrieval metadata survive publication and revision."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from rag import Corpus, RetrievalError
from search_index import rank
from store import publish
from wiki_structure import navigation_paths


class WikiStructureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "wiki").mkdir()
        self.run_id = "RUN-NAV"
        state = {"run_id": self.run_id, "revision": 1, "records": {},
                 "entities": {}, "observations": {}, "artifacts": {}}
        (self.root / "state.json").write_text(json.dumps(state), encoding="utf-8")
        (self.root / "wiki/manifest.json").write_text(
            json.dumps({"run_id": self.run_id, "pages": []}), encoding="utf-8")
        self.publish({"observations": [{"id": "O-1", "summary": "Local fixture observation.",
                                         "content": {"response": {"status": 200, "fixture": True}}}]})

    def publish(self, batch):
        return publish(self.root, self.run_id, batch)

    def corpus(self):
        return Corpus(self.root, self.run_id)

    def initial(self):
        # Parents may appear after children in a single publication.
        self.publish({"records": [{"id": "F-1", "kind": "Fact", "summary": "A narrow observation.", "observation_refs": ["O-1"]}],
                      "pages": [
                          {"id": "P-LEAF", "title": "Result", "parent_page_id": "P-FLOW",
                           "record_refs": ["F-1"], "blocks": [
                               {"id": "B-RESULT", "title": "Judgment", "text": "Applicable only to this observed identity."}]},
                          {"id": "P-FLOW", "title": "Export", "parent_page_id": "P-SERVICE", "blocks": []},
                          {"id": "P-SERVICE", "title": "Reports", "blocks": []},
                          {"id": "P-OTHER", "title": "Accounts", "blocks": []}]})

    def test_authored_fields_are_persisted_and_searchable(self):
        self.initial()
        fields = {"summary": "A conditional judgment.", "questions": ["evidencequestiontoken"],
                  "keywords": ["distinctivekeyword"], "aliases": ["judgmentalias"],
                  "retrieval": {"questions": ["nestedquestiontoken"], "keywords": ["nestedkeyword"]}}
        self.publish({"pages": [{"id": "P-LEAF", "title": "Result", "parent_page_id": "P-FLOW",
                                  "record_refs": ["F-1"], **fields,
                                  "blocks": [{"id": "B-RESULT", "title": "Judgment",
                                              "text": "Applicable only to this observed identity.", **fields},
                                             {"id": "B-NESTED", "title": "Different judgment", "text": "The next precondition is unknown.",
                                              "retrieval": {"questions": ["onlynestedquestion"]}}]}]})
        corpus = self.corpus()
        for name, value in fields.items():
            self.assertEqual(corpus.pages["P-LEAF"][name], value)
            self.assertEqual(corpus.blocks["P-LEAF/B-RESULT"][name], value)
        for query, block in (("evidencequestiontoken", "B-RESULT"),
                             ("distinctivekeyword", "B-RESULT"), ("onlynestedquestion", "B-NESTED")):
            rows, _ = rank(corpus, query, [])
            self.assertIn(("block", "P-LEAF/" + block), rows)

    def test_ancestor_rename_and_move_preserve_ids_content_and_sources(self):
        self.initial()
        before = self.corpus()
        leaf = before.pages["P-LEAF"]
        self.assertEqual(navigation_paths(before.pages)["P-LEAF"], ["Reports", "Export", "Result"])
        block_bytes = (self.root / leaf["path"]).read_bytes()
        self.publish({"pages": [{"id": "P-SERVICE", "title": "Reporting"}]})
        self.assertEqual(navigation_paths(self.corpus().pages)["P-LEAF"], ["Reporting", "Export", "Result"])
        self.publish({"pages": [{"id": "P-FLOW", "parent_page_id": "P-OTHER"}]})
        after = self.corpus()
        self.assertEqual(navigation_paths(after.pages)["P-LEAF"], ["Accounts", "Export", "Result"])
        self.assertEqual(after.pages["P-LEAF"], leaf)
        self.assertEqual((self.root / leaf["path"]).read_bytes(), block_bytes)
        self.assertIn("P-LEAF/B-RESULT", after.blocks)
        self.assertIn("Accounts → Export → Result", (self.root / "wiki/index.md").read_text())

    def test_metadata_edit_does_not_refresh_stale_interpretation(self):
        self.initial()
        self.publish({"records": [{"id": "F-1", "summary": "An additional condition is now known."}]})
        before = self.corpus().pages["P-LEAF"]
        self.publish({"pages": [{"id": "P-LEAF", "title": "Renamed result", "parent_page_id": None}]})
        corpus = self.corpus()
        page = corpus.pages["P-LEAF"]
        for field in ("blocks", "source_refs", "checked_candidates", "basis_state_revision"):
            self.assertEqual(page[field], before[field])
        self.assertEqual(navigation_paths(corpus.pages)["P-LEAF"], ["Renamed result"])
        self.assertIn("stale_source", {issue["code"] for issue in corpus.page_check("P-LEAF")["issues"]})
        self.assertTrue((self.root / page["path"]).read_text().startswith("# Renamed result\n"))

    def test_navigation_invalidity_rejects_publication_without_writing(self):
        self.initial()
        before = (self.root / "state.json").read_bytes()
        for row, error in (({"id": "P-SERVICE", "parent_page_id": "P-MISSING"}, "missing parent P-MISSING"),
                           ({"id": "P-SERVICE", "parent_page_id": "P-LEAF"}, "navigation cycle")):
            with self.assertRaisesRegex(RetrievalError, error):
                self.publish({"pages": [row]})
            self.assertEqual((self.root / "state.json").read_bytes(), before)
        self.assertEqual(navigation_paths(self.corpus().pages)["P-LEAF"], ["Reports", "Export", "Result"])

    def test_auto_block_marker_cannot_be_claimed_by_an_authored_block(self):
        self.publish({"records": [{"id": "F-1", "kind": "Fact", "summary": "An observation.", "observation_refs": ["O-1"]}]})
        self.assertEqual(self.corpus().blocks["WK-F-1/B-F-1"]["representation"], "record")
        self.publish({"pages": [{"id": "WK-F-1", "title": "Authored result", "record_refs": ["F-1"],
                                  "blocks": [{"id": "B-F-1", "title": "Interpretation", "text": "A further conditional interpretation.",
                                              "representation": "record"}]}]})
        self.assertNotIn("representation", self.corpus().blocks["WK-F-1/B-F-1"])

    def test_auto_record_refresh_keeps_navigation(self):
        self.publish({"records": [{"id": "F-1", "kind": "Fact", "summary": "An observation.", "observation_refs": ["O-1"]}],
                      "pages": [{"id": "P-SERVICE", "title": "Reports", "blocks": []}]})
        self.publish({"pages": [{"id": "WK-F-1", "parent_page_id": "P-SERVICE", "questions": ["Can the observed identifier be used?"]}]})
        self.publish({"records": [{"id": "F-1", "summary": "A revised observation."}]})
        corpus = self.corpus()
        self.assertEqual(corpus.pages["WK-F-1"]["parent_page_id"], "P-SERVICE")
        self.assertEqual(corpus.pages["WK-F-1"]["questions"], ["Can the observed identifier be used?"])
        self.assertEqual(corpus.blocks["WK-F-1/B-F-1"]["representation"], "record")


if __name__ == "__main__":
    unittest.main()
