"""Publication avoids unrelated reads while keeping changed evidence visible."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from rag import Corpus, RetrievalError
from store import audit, publish


class LocalPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "wiki").mkdir()
        self.run_id = "RUN-LOCAL"
        self.write("state.json", {"run_id": self.run_id, "revision": 1, "records": {},
                                  "entities": {}, "observations": {}, "artifacts": {}})
        self.write("wiki/manifest.json", {"run_id": self.run_id, "pages": []})

    def write(self, relative, value):
        (self.root / relative).write_text(json.dumps(value), encoding="utf-8")

    def add(self, batch, metrics=None):
        return publish(self.root, self.run_id, batch, metrics=metrics)

    def populate(self):
        self.add({"entities": [{"id": "E-" + name, "kind": "endpoint"} for name in ("A", "B")],
                  "observations": [{"id": "O-" + name, "subject_refs": ["E-" + name],
                                    "content": {"response": name, "environment": "lab"}} for name in ("A", "B")],
                  "records": [{"id": "F-" + name, "kind": "Fact", "summary": "Observed " + name,
                               "subject_refs": ["E-" + name], "observation_refs": ["O-" + name]} for name in ("A", "B")]})

    def test_update_reads_only_relevant_page_and_evidence(self):
        self.populate()
        actual, reads = Corpus.read_bytes, []

        def record(corpus, relative):
            reads.append(str(relative))
            return actual(corpus, relative)

        metrics = {}
        with patch.object(Corpus, "read_bytes", record):
            self.add({"records": [{"id": "F-A", "summary": "A revised conditional observation"}]}, metrics)
        self.assertNotIn("wiki/pages/WK-F-B.md", reads)
        self.assertNotIn("evidence/O-B.jsonl", reads)
        self.assertIn("evidence/O-A.jsonl", reads)
        self.assertEqual(metrics["counts"]["pages_checked"], 1)
        self.assertEqual(metrics["counts"]["page_checks_reused"], 1)
        self.assertEqual(metrics["counts"]["publish_pages_loaded"], 1)
        self.assertEqual(set(metrics["stages_ms"]) & {"publish.load", "publish.prepare", "publish.validation",
                                                   "publish.wiki_index", "publish.write"},
                         {"publish.load", "publish.prepare", "publish.validation", "publish.wiki_index", "publish.write"})

    def test_metadata_change_does_not_reread_evidence_or_refresh_sources(self):
        self.populate()
        before = Corpus(self.root, self.run_id, lazy_pages=True).pages["WK-F-A"]
        actual, reads = Corpus.read_bytes, []

        def record(corpus, relative):
            reads.append(str(relative))
            return actual(corpus, relative)

        with patch.object(Corpus, "read_bytes", record):
            self.add({"pages": [{"id": "WK-F-A", "title": "Renamed judgment", "parent_page_id": "WK-F-B"}]})
        self.assertFalse(any(path.startswith("evidence/") for path in reads), reads)
        after = Corpus(self.root, self.run_id, lazy_pages=True).pages["WK-F-A"]
        for key in ("blocks", "source_refs", "checked_candidates", "basis_state_revision"):
            self.assertEqual(before[key], after[key])
        self.assertIn("Observed B", (self.root / "wiki/index.md").read_text())

    def test_new_counterevidence_without_subject_rechecks_old_page(self):
        self.populate()
        metrics = {}
        self.add({"observations": [{"id": "O-COUNTER", "content": {"result": "contrary observation"}}],
                  "records": [{"id": "F-COUNTER", "kind": "Fact", "observation_refs": ["O-COUNTER"],
                               "contradicts": ["F-A"], "summary": "A new contrary observation"}]}, metrics)
        index = (self.root / "wiki/index.md").read_text()
        self.assertIn("相关记录：[F-COUNTER]", index)
        self.assertEqual(metrics["counts"]["pages_checked"], 2)
        self.assertEqual(metrics["counts"]["page_checks_reused"], 1)
        self.assertNotIn("F-COUNTER", {row["id"] for row in Corpus(self.root, self.run_id).pages["WK-F-A"]["checked_candidates"]})

    def test_subject_candidate_without_prior_reference_rechecks_old_page(self):
        self.populate()
        self.add({"observations": [{"id": "O-LATER", "subject_refs": ["E-A"], "content": {"result": "new condition"}}],
                  "records": [{"id": "F-LATER", "kind": "Fact", "subject_refs": ["E-A"],
                               "observation_refs": ["O-LATER"], "summary": "Related but uncited evidence"}]})
        index = (self.root / "wiki/index.md").read_text()
        self.assertIn("相关记录：[F-LATER]", index)

    def test_transitive_source_revision_rechecks_unchanged_interpretation(self):
        self.populate()
        self.add({"records": [{"id": "S-DEPEND", "kind": "Step", "source_refs": ["F-A"],
                               "summary": "A question based on the observed behavior"}],
                  "pages": [{"id": "P-DEPEND", "title": "Dependent question", "record_refs": ["S-DEPEND"]}]})
        before = (self.root / "wiki/pages/P-DEPEND.md").read_bytes()
        self.add({"records": [{"id": "F-A", "summary": "The original observation has a narrower boundary"}]})
        self.assertEqual(before, (self.root / "wiki/pages/P-DEPEND.md").read_bytes())
        checks = json.loads((self.root / "cache/page-checks.json").read_text())["pages"]
        self.assertEqual(checks["P-DEPEND"]["check"]["status"], "review_required")
        self.assertIn("F-A", {row["id"] for row in checks["P-DEPEND"]["check"]["new_candidates"]})

    def test_external_unrelated_page_and_observation_edits_are_detected(self):
        self.populate()
        page = self.root / "wiki/pages/WK-F-B.md"
        page.write_text(page.read_text() + "Unexpected edit\n", encoding="utf-8")
        self.add({"records": [{"id": "F-A", "summary": "Changed A"}]})
        self.assertIn("页面内容与清单不一致", (self.root / "wiki/index.md").read_text())
        # Rebuild B legitimately, then externally alter its registered evidence.
        self.add({"records": [{"id": "F-B", "summary": "Regenerated B"}]})
        observation = self.root / "evidence/O-B.jsonl"
        observation.write_bytes(observation.read_bytes().replace(b'"B"', b'"C"'))
        self.add({"records": [{"id": "F-A", "summary": "Changed A again"}]})
        self.assertIn("artifact_hash_mismatch", (self.root / "wiki/index.md").read_text())

    def test_required_block_change_marks_referring_page_for_review(self):
        self.populate()
        self.add({"pages": [{"id": "P-INTERPRET", "title": "Depends on B", "record_refs": ["F-B"],
                             "blocks": [{"id": "B-I", "title": "Interpretation", "text": "Conditional result"}]},
                            {"id": "P-COMBINE", "title": "Combination", "record_refs": ["F-A"],
                             "blocks": [{"id": "B-C", "title": "Combined judgment", "text": "Requires the other interpretation",
                                         "required_block_refs": [{"page_id": "P-INTERPRET", "block_id": "B-I"}]}]}]})
        original = (self.root / "wiki/pages/P-COMBINE.md").read_bytes()
        self.add({"records": [{"id": "F-B", "summary": "B's necessary condition changed"}]})
        self.assertEqual(original, (self.root / "wiki/pages/P-COMBINE.md").read_bytes())
        cache = json.loads((self.root / "cache/page-checks.json").read_text())
        # Cache is the page's own check; propagated required-block status is
        # derived anew for the index, not persisted as a source assertion.
        self.assertEqual(cache["pages"]["P-COMBINE"]["check"]["status"], "ready")
        self.assertIn("[Combination](pages/P-COMBINE.md)；页面待复核", (self.root / "wiki/index.md").read_text())

    def test_cache_can_be_deleted_and_audit_does_not_trust_it(self):
        self.populate()
        cache = self.root / "cache/page-checks.json"
        cache.unlink()
        metrics = {}
        self.add({}, metrics)
        self.assertEqual(metrics["counts"]["pages_checked"], 2)
        page = self.root / "wiki/pages/WK-F-B.md"
        page.write_text("external corrupt page", encoding="utf-8")
        report = audit(self.root, self.run_id)
        self.assertIn("page_hash_mismatch", json.dumps(report))

    def test_changed_record_still_checks_its_source_artifact(self):
        source = self.root / "capture.txt"
        source.write_text("original source", encoding="utf-8")
        self.add({"observations": [{"id": "O-A", "source_path": str(source), "content": {"result": "seen"}}],
                  "records": [{"id": "F-A", "kind": "Fact", "observation_refs": ["O-A"], "summary": "Narrow finding"}]})
        (self.root / "evidence/O-A.source").write_text("tampered source", encoding="utf-8")
        before = (self.root / "state.json").read_bytes()
        with self.assertRaisesRegex(RetrievalError, "artifact_hash_mismatch"):
            self.add({"records": [{"id": "F-A", "summary": "Further interpretation"}]})
        self.assertEqual(before, (self.root / "state.json").read_bytes())

    def test_unrelated_publish_rechecks_changed_observation_source_artifact(self):
        source = self.root / "capture.txt"
        source.write_text("original source", encoding="utf-8")
        self.add({"entities": [{"id": "E-A", "kind": "endpoint"}],
                  "observations": [{"id": "O-A", "source_path": str(source), "subject_refs": ["E-A"],
                                    "content": {"result": "seen"}}],
                  "records": [{"id": "F-A", "kind": "Fact", "subject_refs": ["E-A"],
                               "observation_refs": ["O-A"], "summary": "Narrow finding"}]})
        cache = self.root / "cache/page-checks.json"
        self.assertEqual(json.loads(cache.read_text())["pages"]["WK-F-A"]["check"]["status"], "ready")
        (self.root / "evidence/O-A.source").write_text("tampered source", encoding="utf-8")
        metrics = {}
        self.add({"records": [{"id": "S-OTHER", "kind": "Step", "summary": "An unrelated research question"}]}, metrics)
        check = json.loads(cache.read_text())["pages"]["WK-F-A"]["check"]
        self.assertEqual(check["status"], "review_required")
        self.assertIn("artifact_hash_mismatch", {row["code"] for row in check["issues"]})
        self.assertIn("artifact_hash_mismatch", (self.root / "wiki/index.md").read_text())
        self.assertEqual(Corpus(self.root, self.run_id, lazy_pages=True).records["F-A"]["revision"], 1)
        self.assertEqual(metrics["counts"]["pages_checked"], 2)


if __name__ == "__main__":
    unittest.main()
