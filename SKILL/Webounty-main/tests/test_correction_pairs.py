"""A two-way contradiction is one relation, not a circular proof."""

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rag import Corpus, RetrievalError, encode, retrieve
from store import publish


class CorrectionPairsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "wiki").mkdir()
        (self.root / "state.json").write_text(encode({
            "run_id": "R1", "revision": 1, "session_id": "S1", "records": {},
            "observations": {}, "entities": {}, "artifacts": {},
        }), encoding="utf-8")
        (self.root / "wiki/manifest.json").write_text(encode({"run_id": "R1", "pages": []}), encoding="utf-8")
        publish(self.root, "R1", {
            "observations": [{"id": "O-GRANT-A", "summary": "Synthetic grant was active",
                              "content": {"grant_record": {"state": "active"}}}],
            "records": [{"id": "C-GRANT-A", "kind": "Capability", "status": "observed",
                "summary": "Synthetic tenant-a grant was obtained; download not verified",
                "observation_refs": ["O-GRANT-A"], "capability": {"provides": [{
                    "type": "report-download-grant", "constraints": {"tenant": "tenant-a", "grant_state": "active"}}],
                    "needs": []}}],
        })
        # Preserve the pair and observation semantics of the actual round-three
        # publication that failed during independent forward use.
        self.revocation = {
            "observations": [{"id": "O-GRANT-A-REVOKED", "summary": "Synthetic grant revoked; download denied",
                "content": {"grant_record": {"state": "revoked"},
                            "response": {"status": 403, "body": {"downloaded": False}}}}],
            "records": [
                {"id": "F-GRANT-A-REVOKED", "kind": "Fact", "status": "observed",
                 "summary": "Synthetic grant currently revoked; this download did not succeed",
                 "observation_refs": ["O-GRANT-A-REVOKED"], "contradicts": ["C-GRANT-A"],
                 "limitations": ["No working baseline; do not infer that all download paths are closed."]},
                {"id": "C-GRANT-A", "kind": "Capability", "status": "refuted",
                 "summary": "Earlier synthetic grant is now revoked",
                 "observation_refs": ["O-GRANT-A", "O-GRANT-A-REVOKED"],
                 "contradicted_by": ["F-GRANT-A-REVOKED"],
                 "capability": {"provides": [{"type": "report-download-grant",
                     "constraints": {"tenant": "tenant-a", "grant_state": "revoked"}}], "needs": []},
                 "change_reason": "Later observation revokes earlier grant; retain original evidence"},
            ],
        }

    def test_paired_contradiction_publishes_and_keeps_both_records_and_observations(self):
        publish(self.root, "R1", self.revocation)
        corpus = Corpus(self.root, "R1")
        for anchor in ("C-GRANT-A", "F-GRANT-A-REVOKED"):
            with self.subTest(anchor=anchor):
                package, issues = corpus.package(record_ids=[anchor])
                self.assertIsNotNone(package)
                self.assertFalse(any(row["code"] == "dependency_cycle" for row in issues))
                self.assertEqual({row["id"] for row in package["records"]},
                                 {"C-GRANT-A", "F-GRANT-A-REVOKED"})
                self.assertEqual({row["id"] for row in package["observations"]},
                                 {"O-GRANT-A", "O-GRANT-A-REVOKED"})
                self.assertTrue(all(row["raw"] for row in package["observations"]))

    def test_compact_cursor_returns_new_counterevidence_and_current_judgment(self):
        retrieve(self.root, "R1", "", ["C-GRANT-A"], view="compact", cursor="main")
        publish(self.root, "R1", self.revocation)
        result = retrieve(self.root, "R1", "", ["C-GRANT-A"], view="compact", cursor="main")
        self.assertTrue(result["delta"]["cursor_advanced"])
        self.assertEqual({row["id"] for row in result["records"]}, {"C-GRANT-A", "F-GRANT-A-REVOKED"})
        self.assertIn("O-GRANT-A-REVOKED", {row["id"] for row in result["observations"]})
        self.assertIn({"kind": "observation", "id": "O-GRANT-A"}, result["unchanged_refs"])
        self.assertTrue(all("raw" not in row for row in result["observations"]))
        self.assertEqual(next(row for row in result["records"] if row["id"] == "C-GRANT-A")["status"], "refuted")

    def test_paired_inverse_does_not_hide_another_dependency_to_the_same_id(self):
        for relation in ("source_refs", "requires", "evidence_refs"):
            with self.subTest(relation=relation):
                batch = copy.deepcopy(self.revocation)
                batch["records"][0][relation] = ["C-GRANT-A"]
                with self.assertRaisesRegex(RetrievalError, "dependency_cycle"):
                    publish(self.root, "R1", batch)

    def test_real_source_reference_cycle_is_still_rejected(self):
        with self.assertRaisesRegex(RetrievalError, "dependency_cycle"):
            publish(self.root, "R1", {"records": [
                {"id": "A", "kind": "Question", "status": "open", "summary": "A", "source_refs": ["B"]},
                {"id": "B", "kind": "Question", "status": "open", "summary": "B", "source_refs": ["A"]},
            ]})


if __name__ == "__main__":
    unittest.main()
