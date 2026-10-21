"""Warm sparse lookups must scale with hits, not unrelated term/dependency rows."""

from pathlib import Path
from contextlib import closing
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark_retrieval_efficiency import dependency_steps, fixture, projection_steps
from retrieval_index import _open, FORMAT_VERSION


class RetrievalEfficiencyTests(unittest.TestCase):
    def make_fixture(self, size):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return fixture(temporary.name, size)

    def test_sparse_projection_ignores_unrelated_postings(self):
        small, small_rows = self.make_fixture(20)
        large, large_rows = self.make_fixture(2000)
        small_steps, small_result = projection_steps(small, small_rows)
        large_steps, large_result = projection_steps(large, large_rows)
        self.assertEqual(small_result, large_result)
        self.assertEqual(large_result[0], {"alpha": {("observation", "O-HIT"): {"body": 1}}})
        self.assertEqual(large.retrieval_index_stats["indexed_documents"], 0)
        # A loose delta avoids SQLite-version-specific plans or opcode counts;
        # an accidental corpus scan adds hundreds of thousands of VM steps.
        self.assertLess(large_steps - small_steps, 5000)
        self.assertEqual(large.retrieval_source_matches["O-HIT"], {
            "artifact_id": "A-1", "offset": 100, "length": 100, "sha256": "1" * 64,
            "matched_query_terms": 2, "matched_original_query_terms": 1,
            "matching_chunks": 2, "selection": "representative_window", "evidence": False})

    def test_unknown_query_does_not_scan_or_reuse_previous_source_window(self):
        data, rows = self.make_fixture(2000)
        projection_steps(data, rows)
        steps, result = projection_steps(data, rows, ("absent-query",))
        self.assertEqual(result[0], {})
        self.assertEqual(data.retrieval_source_matches, {})
        self.assertLess(steps, 5000)

    def test_changed_reference_looks_up_only_its_dependents(self):
        small, small_rows = self.make_fixture(20)
        large, large_rows = self.make_fixture(2000)
        small_steps, small_keys = dependency_steps(small, small_rows)
        large_steps, large_keys = dependency_steps(large, large_rows)
        self.assertEqual(small_keys, {("observation", "O-HIT")})
        self.assertEqual(small_keys, large_keys)
        self.assertLess(large_steps - small_steps, 5000)

    def test_previous_source_admission_version_requires_rebuild(self):
        data, _ = self.make_fixture(20)
        with closing(_open(data)) as db:
            db.execute("UPDATE metadata SET value='4' WHERE name='format'")
            db.commit()
        with closing(_open(data)) as db:
            self.assertEqual(db.execute("SELECT value FROM metadata WHERE name='format'").fetchone()[0],
                             FORMAT_VERSION)
            for table in ("documents", "terms", "dependencies", "source_chunks", "source_terms"):
                self.assertEqual(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
