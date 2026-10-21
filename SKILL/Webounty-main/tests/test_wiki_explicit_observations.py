"""Explicit Wiki source observations remain in scope without invented subjects."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from rag import Corpus
from store import publish


class WikiExplicitObservationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_id = "RUN-EXPLICIT"
        (self.root / "wiki").mkdir()
        state = {"run_id": self.run_id, "revision": 1, "records": {},
                 "entities": {}, "observations": {}, "artifacts": {}}
        (self.root / "state.json").write_text(json.dumps(state), encoding="utf-8")
        (self.root / "wiki/manifest.json").write_text(
            json.dumps({"run_id": self.run_id, "pages": []}), encoding="utf-8")

    def publish(self, batch):
        return publish(self.root, self.run_id, batch)

    def corpus(self):
        return Corpus(self.root, self.run_id)

    def initial(self):
        self.publish({
            "observations": [{"id": "O-1", "summary": "Synthetic local observation.",
                              "subject_refs": [], "content": {"synthetic": True, "value": "one"}}],
            "records": [{"id": "SOURCE", "kind": "Fact", "summary": "An observed value.",
                         "subject_refs": [], "observation_refs": ["O-1"]},
                        {"id": "DERIVED", "kind": "Fact", "summary": "An interpretation of SOURCE.",
                         "subject_refs": [], "observation_refs": [],
                         "source_refs": [{"id": "SOURCE", "revision": 1}]}]})
        self.publish({"pages": [{"id": "P-AUTHORED", "title": "Interpretation", "record_refs": ["DERIVED"],
                       "blocks": [{"id": "B-1", "title": "Conditions",
                                   "text": "This interpretation applies only to the explicit source."}]}]})

    def test_initial_pages_keep_explicit_and_recursive_observations_in_scope(self):
        self.initial()
        current = self.corpus()
        for pid in ("WK-SOURCE", "WK-DERIVED", "P-AUTHORED"):
            with self.subTest(page=pid):
                check = current.page_check(pid)
                self.assertEqual(check["status"], "ready")
                self.assertEqual(check["removed_candidates"], [])
                self.assertEqual(check["new_candidates"], [])
                self.assertIn(("observation", "O-1"),
                              {(row["kind"], row["id"]) for row in current.candidates(current.pages[pid])})
        self.assertEqual(current.observations["O-1"]["subject_refs"], [])
        self.assertEqual(current.records["SOURCE"]["subject_refs"], [])
        self.assertEqual(current.entities, {})

    def test_removed_explicit_observation_still_requires_old_interpretation_review(self):
        self.initial()
        self.publish({"observations": [{"id": "O-2", "summary": "Replacement observation.",
                                         "subject_refs": [], "content": {"synthetic": True, "value": "two"}}],
                      "records": [{"id": "SOURCE", "observation_refs": ["O-2"]}]})
        current = self.corpus()
        check = current.page_check("P-AUTHORED")
        self.assertEqual(check["status"], "review_required")
        self.assertIn(("observation", "O-1"),
                      {(row["kind"], row["id"]) for row in check["removed_candidates"]})
        self.assertNotIn(("observation", "O-1"),
                         {(row["kind"], row["id"]) for row in current.candidates(current.pages["P-AUTHORED"])})
        self.assertIn("removed_candidates", {issue["code"] for issue in check["issues"]})

    def test_source_revision_change_does_not_reapprove_old_page(self):
        self.initial()
        self.publish({"records": [{"id": "SOURCE", "summary": "The source has a narrower condition."}]})
        current = self.corpus()
        check = current.page_check("P-AUTHORED")
        self.assertEqual(check["status"], "review_required")
        self.assertEqual([row["revision"] for row in check["removed_candidates"] if row["id"] == "SOURCE"], [1])
        self.assertEqual([row["revision"] for row in check["new_candidates"] if row["id"] == "SOURCE"], [2])
        self.assertNotIn("O-1", {row["id"] for row in check["removed_candidates"]})

    def test_changed_original_artifact_is_still_checked_without_subject_scope(self):
        self.initial()
        current = self.corpus()
        aid = current.observations["O-1"]["artifact_id"]
        artifact = self.root / current.artifacts[aid]["path"]
        artifact.write_bytes(artifact.read_bytes() + b"changed original\n")
        check = self.corpus().page_check("P-AUTHORED")
        self.assertEqual(check["status"], "review_required")
        self.assertIn("artifact_hash_mismatch", {issue["code"] for issue in check["issues"]})


if __name__ == "__main__":
    unittest.main()
