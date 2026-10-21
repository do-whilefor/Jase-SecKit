"""Original artifact integrity must agree across retrieval and candidate plans."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from discovery import _Sources, discover
from rag import Corpus, retrieve
from session import start
from store import publish


class ArtifactSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.info = start("artifact-sources", "synthetic source checks", temporary.name)
        self.root = Path(self.info["root"])
        self.run_id = self.info["run_id"]
        publish(self.root, self.run_id, {
            "observations": [{"id": oid, "content": {"response": {"status": 200}}}
                             for oid in ("OA", "OC", "OX")],
            "records": [
                {"id": "A", "kind": "Fact", "status": "verified", "summary": "job producer",
                 "observation_refs": ["OA"], "artifact_refs": [{"artifact_id": "ART-OX"}],
                 "capability": {"provides": [{"type": "job", "constraints": {"tenant": "lab"}}]}},
                {"id": "C", "kind": "Question", "status": "open", "summary": "job consumer",
                 "observation_refs": ["OC"],
                 "capability": {"needs": [{"type": "job", "constraints": {"tenant": "lab"}}]}}]})

    def edge(self, corpus):
        return next(edge for edge in discover(corpus, anchors=["C"])["candidates"]
                    if edge["producer_ref"] == "A" and edge["consumer_ref"] == "C")

    def test_valid_extra_artifact_is_locatable_and_remains_a_candidate(self):
        with Corpus(self.root, self.run_id, lazy_pages=True, lazy_metadata=True) as corpus:
            edge = self.edge(corpus)
            self.assertEqual(edge["compatibility"], "compatible")
            self.assertTrue(edge["producer_usable"])
            self.assertEqual(edge["artifact_refs"], ["ART-OX"])
            self.assertFalse(edge["evidence"])

    def test_corrupt_extra_artifact_cannot_complete_a_plan(self):
        (self.root / "evidence/OX.jsonl").write_bytes(b"{}\n")
        with Corpus(self.root, self.run_id, lazy_pages=True, lazy_metadata=True) as corpus:
            edge = self.edge(corpus)
            self.assertFalse(edge["producer_usable"])
            self.assertEqual(edge["compatibility"], "unknown")
            self.assertIn("artifact_hash_mismatch", {item["code"] for item in edge["source_issues"]})
        result = retrieve(self.root, self.run_id, "job", question_ref="C", view="compact")
        self.assertEqual(result["question_context"]["requirements"]["status"], "unresolved")

    def test_missing_artifact_and_bad_line_are_not_usable(self):
        for reference, issue_code in (({"artifact_id": "MISSING"}, "missing_reference"),
                                     ({"artifact_id": "ART-OX", "line": 99}, "artifact_location_missing")):
            with self.subTest(reference=reference), Corpus(self.root, self.run_id, lazy_pages=True) as corpus:
                # Simulate external index damage; publish rejects broken references.
                corpus.records["A"]["artifact_refs"] = [reference]
                checked = _Sources(corpus).inspect("A")
                self.assertFalse(checked["usable"])
                self.assertIn(issue_code, {issue["code"] for issue in checked["issues"]})

    def test_upstream_artifact_failure_propagates_to_consumer(self):
        publish(self.root, self.run_id, {"records": [{"id": "C", "source_refs": ["A"]}]})
        (self.root / "evidence/OX.jsonl").write_bytes(b"{}\n")
        with Corpus(self.root, self.run_id, lazy_pages=True, lazy_metadata=True) as corpus:
            checked = _Sources(corpus).inspect("C")
            self.assertFalse(checked["usable"])
            self.assertTrue(any(issue["code"] == "artifact_hash_mismatch" and issue["record_id"] == "A"
                                for issue in checked["issues"]))

    def test_artifact_only_question_exposes_original_read_reference(self):
        publish(self.root, self.run_id, {"records": [
            {"id": "Q", "kind": "Question", "status": "open", "summary": "inspect original",
             "artifact_refs": [{"artifact_id": "ART-OX", "line": 1}]}]})
        result = retrieve(self.root, self.run_id, "", question_ref="Q", mode="lexical", view="compact")
        report = result["question_context"]
        self.assertEqual(report["source_observation_refs"], [])
        self.assertEqual(report["source_artifact_refs"], ["ART-OX"])
        self.assertNotIn("no_source_evidence", {issue["code"] for issue in report["source_issues"]})
        self.assertIn("ART-OX", report["next_actions"][0]["ids"])
        self.assertEqual(report["answer_support"], "not_assessed")
        self.assertFalse(report["evidence"])

    def test_no_source_stays_unknown_without_inventing_evidence(self):
        publish(self.root, self.run_id, {"records": [
            {"id": "Q", "kind": "Question", "status": "open", "summary": "unverified question"}]})
        with Corpus(self.root, self.run_id, lazy_pages=True) as corpus:
            checked = _Sources(corpus).inspect("Q")
            self.assertEqual(checked["artifacts"], set())
            self.assertIn("no_source_evidence", {issue["code"] for issue in checked["issues"]})


if __name__ == "__main__":
    unittest.main()
