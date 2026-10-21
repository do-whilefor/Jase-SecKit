"""Whole-session retrieval contracts, evaluated against fixed authored labels."""
from pathlib import Path
import tempfile
import unittest

from replay_session import DeliveredContext, file_reads, replay


class SessionReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = replay()
        cls.turns = {row["id"]: row for row in cls.report["turns"]}

    def test_all_six_turns_keep_required_evidence_and_conditional_combinations(self):
        for turn in self.report["turns"]:
            with self.subTest(turn=turn["id"]):
                failed = [name for name, passed in turn["checks"].items() if not passed]
                self.assertEqual(failed, [])
                self.assertTrue(turn["passed"])
                self.assertTrue(all(row["evidence"] is False for row in turn["candidates"]))
                self.assertFalse(any("R-FOREIGN" in row["record_refs"] for row in turn["paths"]))

    def test_same_blocked_step_is_reconsidered_without_upgrading_it_to_success(self):
        initial = self.turns["initial_missing_input"]
        repeated = self.turns["paraphrase_unchanged"]
        supplemented = self.turns["new_input_reopens_blocked"]
        renamed = self.turns["unrelated_edit_and_rename"]
        self.assertEqual(initial["state_revision"], repeated["state_revision"])
        self.assertEqual(repeated["delivered_record_ids"], [])
        self.assertLess(repeated["retrieval"]["output_characters"], initial["retrieval"]["output_characters"])
        self.assertEqual(initial["current_record_revisions"]["R-DOWN"], supplemented["current_record_revisions"]["R-DOWN"])
        path = next(row for row in supplemented["paths"] if row["record_refs"] == ["R-JOB", "R-GRANT", "R-DOWN"])
        self.assertEqual(path["missing_preconditions"], [])
        self.assertEqual(len(path["bindings"]), 3)
        self.assertEqual(path["status"], "candidate")
        self.assertEqual(renamed["delivered_record_ids"], [])

    def test_counterevidence_revises_review_state_retransmits_judgment_and_blocks_old_paths(self):
        old = self.turns["new_input_reopens_blocked"]
        changed = self.turns["counterevidence_changes_route"]
        self.assertGreater(changed["current_record_revisions"]["R-GRANT"], old["current_record_revisions"]["R-GRANT"])
        self.assertIn("R-GRANT", changed["delivered_record_ids"])
        self.assertEqual(changed["counterevidence_coverage"]["observations"]["coverage"], 1.0)
        self.assertFalse(any("R-GRANT" in row["record_refs"] for row in changed["paths"]))
        self.assertIn("O-DOWN", changed["required_reference_coverage"]["observations"]["found"])

    def test_refresh_restores_context_and_reads_original_negative_observations(self):
        refreshed = self.turns["refresh_and_read_originals"]
        self.assertFalse(refreshed["unchanged_record_ids"])
        self.assertTrue(all(read["passed"] for read in refreshed["reads"]))
        self.assertEqual([read["ids"] for read in refreshed["reads"]], [["O-DOWN"], ["O-COUNTER"]])
        self.assertEqual(self.report["summary"]["explicit_read_calls"], 2)
        self.assertIsNone(self.report["summary"]["host_tokens"])
        self.assertEqual(self.report["summary"]["model_calls"], 0)
        self.assertGreater(self.report["summary"]["read_output_characters"], 0)

    def test_replay_tracks_real_state_wiki_and_evidence_reads(self):
        measurements = [row["retrieval"] for row in self.report["turns"]]
        measurements += [row["publication"] for row in self.report["turns"] if row["publication"]]
        measurements += [read["measurement"] for row in self.report["turns"] for read in row["reads"]]
        for group in ("state", "wiki_manifest", "wiki_pages", "evidence"):
            with self.subTest(group=group):
                self.assertGreater(sum(row["file_reads"].get(group, {}).get("calls", 0) for row in measurements), 0)
                self.assertGreater(sum(row["file_reads"].get(group, {}).get("bytes", 0) for row in measurements), 0)
        # Publication reads the authoritative JSON. A current query projection
        # avoids reopening the whole state while originals remain measured.
        initial = self.turns["initial_missing_input"]["retrieval"]["file_reads"]
        self.assertEqual(initial.get("state", {}).get("opens", 0), 0)
        self.assertGreater(initial["evidence"]["bytes"], 0)

    def test_read_helpers_and_open_streams_are_counted_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "wiki/pages").mkdir(parents=True)
            (root / "evidence").mkdir()
            state, page, evidence = root / "state.json", root / "wiki/pages/page.md", root / "evidence/raw.txt"
            state.write_bytes(b"abc")
            page.write_text("wiki", encoding="utf-8")
            evidence.write_bytes(b"one\ntwo\nthree\n")
            with file_reads(root) as measured:
                self.assertEqual(state.read_bytes(), b"abc")
                self.assertEqual(page.read_text(encoding="utf-8"), "wiki")
                with evidence.open("rb") as stream:
                    self.assertEqual(stream.readline(), b"one\n")
                    self.assertEqual(next(iter(stream)), b"two\n")
                    self.assertEqual(stream.read(), b"three\n")
                with state.open("rb") as stream:
                    self.assertEqual(stream.read(), b"abc")
            self.assertEqual(measured["state"], {"opens": 2, "calls": 2, "bytes": 6})
            self.assertEqual(measured["wiki_pages"], {"opens": 1, "calls": 1, "bytes": 4})
            self.assertEqual(measured["evidence"], {"opens": 1, "calls": 3, "bytes": 14})

    def test_dangling_unchanged_reference_is_not_counted_as_retained_context(self):
        host = DeliveredContext()
        result = {"records": [], "observations": [], "unchanged_refs": [{"kind": "record", "id": "not-delivered"}]}
        current, missing = host.accept(result)
        self.assertFalse(current["record"])
        self.assertEqual(missing, [{"kind": "record", "id": "not-delivered"}])


if __name__ == "__main__":
    unittest.main()
