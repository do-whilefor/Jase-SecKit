"""Failure boundaries for publishing a complete session revision, offline."""

from contextlib import redirect_stderr, redirect_stdout
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from evidence_io import FileCopy
import publication
from rag import Corpus
from session import main, start
from store import publish


class PublicationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="webounty-publication-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.session_id = "publication-recovery"
        info = start(self.session_id, "Keep a consistent research session", self.project)
        self.root, self.run_id = Path(info["root"]), info["run_id"]
        publish(self.root, self.run_id, {
            "observations": [{"id": "O-OLD", "content": {"response": "old evidence"}}],
            "records": [{"id": "Q-1", "kind": "Question", "status": "open",
                         "summary": "Original question", "observation_refs": ["O-OLD"]}],
        })
        self.before = self.authoritative_files()
        self.revision = json.loads(self.before["state.json"])["revision"]

    def authoritative_files(self):
        paths = [self.root / "state.json", *(self.root / "wiki").rglob("*"),
                 *(self.root / "evidence").rglob("*")]
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in paths if path.is_file()}

    def batch(self, *, source=None):
        observation = {"id": "O-NEW", "content": {"response": "new evidence"}}
        if source is not None:
            observation["source_path"] = str(source)
        return {"observations": [observation], "records": [
            {"id": "Q-1", "summary": "Revised question", "observation_refs": ["O-NEW"]},
        ]}

    def assert_old_revision(self):
        self.assertEqual(self.authoritative_files(), self.before)
        with Corpus(self.root, self.run_id) as corpus:
            self.assertEqual(corpus.records["Q-1"]["summary"], "Original question")
            self.assertNotIn("O-NEW", corpus.observations)
            self.assertEqual(corpus.observation("O-OLD")["status"], "ready")
            self.assertFalse(corpus.page_issues["WK-Q-1"])

    def assert_committed(self, result):
        self.assertEqual(result["publication_status"], "committed")
        self.assertEqual(result["state_revision"], self.revision + 1)
        self.assertTrue(result["warnings"])
        for warning in result["warnings"]:
            self.assertTrue(warning["code"])
            self.assertTrue(warning["detail"])
        with Corpus(self.root, self.run_id) as corpus:
            self.assertEqual(corpus.records["Q-1"]["summary"], "Revised question")
            self.assertEqual(corpus.observation("O-NEW")["status"], "ready")
            self.assertFalse(corpus.page_issues["WK-Q-1"])

    def test_manifest_replace_failure_restores_pages_state_and_removes_new_evidence(self):
        original = publication.os.replace
        failed = False

        def fail_once(source, target, *args, **kwargs):
            nonlocal failed
            if Path(target) == self.root / "wiki/manifest.json" and not failed:
                failed = True
                raise OSError("synthetic manifest replacement failure")
            return original(source, target, *args, **kwargs)

        with patch.object(publication.os, "replace", side_effect=fail_once):
            with self.assertRaisesRegex(OSError, "synthetic manifest"):
                publish(self.root, self.run_id, self.batch())
        self.assertTrue(failed)
        self.assert_old_revision()
        # A retry must not be rejected because failed publication left immutable files.
        result = publish(self.root, self.run_id, self.batch())
        self.assertEqual(result["publication_status"], "committed")
        self.assertEqual(result["state_revision"], self.revision + 1)

    def test_interrupted_source_copy_leaves_no_partial_official_evidence(self):
        source = self.project / "capture.txt"
        original = b"A complete captured response\n" * 20
        source.write_bytes(original)

        def interrupt_copy(copy, stream):
            stream.write(b"partial capture")
            raise OSError("synthetic source copy interruption")

        with patch.object(FileCopy, "write_to", interrupt_copy):
            with self.assertRaisesRegex(OSError, "source copy interruption"):
                publish(self.root, self.run_id, self.batch(source=source))
        self.assertEqual(source.read_bytes(), original)
        self.assert_old_revision()
        publish(self.root, self.run_id, self.batch(source=source))
        self.assertEqual((self.root / "evidence/O-NEW.source").read_bytes(), original)

    def test_retrieval_cache_failure_reports_committed_revision(self):
        with patch("retrieval_index.sync_publication", side_effect=OSError("synthetic cache failure")):
            result = publish(self.root, self.run_id, self.batch())
        self.assert_committed(result)

    def test_page_check_cache_failure_reports_committed_revision(self):
        with patch("store.PageChecks.save", side_effect=OSError("synthetic page cache failure")):
            result = publish(self.root, self.run_id, self.batch())
        self.assert_committed(result)

    def test_log_failure_reports_committed_revision(self):
        original = Path.open

        def fail_log(path, mode="r", *args, **kwargs):
            if path == self.root / "logs/store.jsonl" and "a" in mode:
                raise PermissionError("synthetic publication log failure")
            return original(path, mode, *args, **kwargs)

        with patch.object(Path, "open", fail_log):
            result = publish(self.root, self.run_id, self.batch())
        self.assert_committed(result)

    def test_partial_cleanup_cannot_turn_a_committed_batch_into_a_rollback(self):
        removed_markers = []

        def interrupt_cleanup(folder, *args, **kwargs):
            marker = Path(folder) / "committed"
            if marker.exists():
                marker.unlink()
                removed_markers.append(marker)
            raise PermissionError("synthetic partial cleanup failure")

        with patch.object(publication.shutil, "rmtree", side_effect=interrupt_cleanup):
            result = publish(self.root, self.run_id, self.batch())
            self.assertEqual(result["publication_status"], "committed")
            self.assertTrue(removed_markers)
            committed = self.authoritative_files()
            publication.recover(self.root, self.run_id)
            self.assertEqual(self.authoritative_files(), committed)
        with Corpus(self.root, self.run_id) as corpus:
            self.assertEqual(corpus.state["revision"], self.revision + 1)
            self.assertEqual(corpus.observation("O-NEW")["status"], "ready")

    def test_committed_revision_remains_readable_when_cleanup_keeps_failing(self):
        with patch("publication._cleanup", side_effect=PermissionError("synthetic locked cleanup")):
            result = publish(self.root, self.run_id, self.batch())
            self.assertEqual(result["publication_status"], "committed")
            with Corpus(self.root, self.run_id) as corpus:
                self.assertEqual(corpus.state["revision"], self.revision + 1)
                self.assertEqual(corpus.observation("O-NEW")["status"], "ready")
                self.assertTrue(corpus.stable())

    def test_commit_marker_sync_failure_reports_committed_with_durability_warning(self):
        original = publication._sync_directory
        failed = False

        def fail_after_marker(folder):
            nonlocal failed
            if Path(folder) == self.root / ".publication" and (Path(folder) / "committed").exists():
                failed = True
                raise OSError("synthetic commit directory sync failure")
            return original(folder)

        with patch("publication._sync_directory", side_effect=fail_after_marker):
            result = publish(self.root, self.run_id, self.batch())
        self.assertTrue(failed)
        self.assert_committed(result)
        self.assertIn("publication_durability_uncertain", {warning["code"] for warning in result["warnings"]})

    def test_failed_stability_check_keeps_external_edit_and_leaves_no_rollback(self):
        state = json.loads(self.before["state.json"])
        state["revision"] += 10
        external = json.dumps(state).encode("utf-8")

        def changed():
            (self.root / "state.json").write_bytes(external)
            return False

        with publication.writer(self.root, self.run_id):
            with self.assertRaisesRegex(ValueError, "changed"):
                publication.install(self.root, self.run_id, {"state.json": b"proposed revision"},
                                    set(), stable=changed)
        self.assertFalse(publication.pending(self.root))
        self.assertEqual((self.root / "state.json").read_bytes(), external)
        publication.recover(self.root, self.run_id)
        self.assertEqual(self.authoritative_files(), {**self.before, "state.json": external})

    def crash_during_install(self):
        script = """
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import publication
from store import publish
root = Path(sys.argv[2])
original = publication.os.replace
def crash(source, target, *args, **kwargs):
    if Path(target) == root / 'wiki/manifest.json':
        os._exit(73)
    return original(source, target, *args, **kwargs)
publication.os.replace = crash
publish(root, sys.argv[3], json.loads(sys.argv[4]))
"""
        result = subprocess.run([sys.executable, "-c", script, str(SCRIPTS), str(self.root),
                                 self.run_id, json.dumps(self.batch())],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertTrue(publication.pending(self.root))
        # Prove this was a partial install, not merely an interruption in preparation.
        self.assertNotEqual((self.root / "state.json").read_bytes(), self.before["state.json"])

    def test_fresh_corpus_recovers_after_process_dies_during_install(self):
        self.crash_during_install()
        with Corpus(self.root, self.run_id, lazy_metadata=True) as corpus:
            self.assertEqual(corpus.state["revision"], self.revision)
            self.assertEqual(corpus.records["Q-1"]["summary"], "Original question")
        self.assertFalse(publication.pending(self.root))
        self.assert_old_revision()

    def test_start_reuse_recovers_before_returning_session_revision(self):
        self.crash_during_install()
        resumed = start(self.session_id, "Do not overwrite the original goal", self.project)
        self.assertEqual(resumed["status"], "reused")
        self.assertEqual(resumed["state_revision"], self.revision)
        self.assertFalse(publication.pending(self.root))
        self.assert_old_revision()

    def test_start_reuse_holds_read_lock_until_state_has_been_read(self):
        original = Path.read_text
        attempted = False

        with ThreadPoolExecutor(max_workers=1) as executor:
            def contend_while_reading(path, *args, **kwargs):
                nonlocal attempted
                if path == self.root / "state.json" and not attempted:
                    attempted = True
                    future = executor.submit(publish, self.root, self.run_id, self.batch())
                    with self.assertRaisesRegex(ValueError, "publication in progress"):
                        future.result(timeout=5)
                return original(path, *args, **kwargs)

            with patch.object(Path, "read_text", contend_while_reading):
                resumed = start(self.session_id, "Resume the existing session", self.project)
        self.assertTrue(attempted)
        self.assertEqual(resumed["state_revision"], self.revision)
        self.assert_old_revision()
        result = publish(self.root, self.run_id, self.batch())
        self.assertEqual(result["publication_status"], "committed")
        self.assertEqual(result["state_revision"], self.revision + 1)

    def test_crash_after_commit_keeps_new_revision_on_recovery(self):
        script = """
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import publication
from store import publish
root = Path(sys.argv[2])
original = publication._cleanup
def crash(root):
    if (root / '.publication/committed').exists():
        os._exit(75)
    return original(root)
publication._cleanup = crash
publish(root, sys.argv[3], json.loads(sys.argv[4]))
"""
        result = subprocess.run([sys.executable, "-c", script, str(SCRIPTS), str(self.root),
                                 self.run_id, json.dumps(self.batch())],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 75, result.stderr)
        self.assertTrue((self.root / ".publication/committed").exists())
        self.assertFalse(publication.pending(self.root))
        committed = self.authoritative_files()
        self.assertNotEqual(committed, self.before)
        with Corpus(self.root, self.run_id) as corpus:
            self.assertEqual(corpus.state["revision"], self.revision + 1)
            self.assertEqual(corpus.records["Q-1"]["summary"], "Revised question")
            self.assertEqual(corpus.observation("O-NEW")["status"], "ready")
            self.assertFalse(corpus.page_issues["WK-Q-1"])
        self.assertFalse(publication.pending(self.root))
        self.assertEqual(self.authoritative_files(), committed)

    def test_recovery_can_resume_after_process_dies_during_rollback(self):
        self.crash_during_install()
        script = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import publication
original = publication.os.replace
def crash(source, target, *args, **kwargs):
    result = original(source, target, *args, **kwargs)
    if Path(source).name == 'restore.tmp':
        os._exit(74)
    return result
publication.os.replace = crash
publication.recover(Path(sys.argv[2]), sys.argv[3])
"""
        result = subprocess.run([sys.executable, "-c", script, str(SCRIPTS), str(self.root), self.run_id],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 74, result.stderr)
        self.assertTrue(publication.pending(self.root))
        with Corpus(self.root, self.run_id) as corpus:
            self.assertEqual(corpus.state["revision"], self.revision)
        self.assertFalse(publication.pending(self.root))
        self.assert_old_revision()

    def test_record_cli_reports_committed_when_analysis_and_response_logs_fail(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (patch("sys.stdin", io.StringIO(json.dumps(self.batch()))),
              patch("discovery.discover", side_effect=OSError("synthetic analysis failure")),
              patch("session.log", side_effect=OSError("synthetic operation log failure")),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = main(["record", "--root", str(self.root), "--run-id", self.run_id, "--input", "-"])
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        result = json.loads(stdout.getvalue())
        self.assert_committed(result)
        self.assertEqual({warning["code"] for warning in result["warnings"]}, {
            "post_publish_analysis_failed", "record_log_failed", "response_log_failed",
        })

    def test_unexpected_post_commit_errors_still_report_each_completed_stage(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        original = Path.open

        def fail_store_log(path, mode="r", *args, **kwargs):
            if path == self.root / "logs/store.jsonl" and "a" in mode:
                raise RuntimeError("synthetic store logger failure")
            return original(path, mode, *args, **kwargs)

        with (patch("sys.stdin", io.StringIO(json.dumps(self.batch()))),
              patch("store.PageChecks.save", side_effect=KeyError("synthetic page cache failure")),
              patch("retrieval_index.sync_publication", side_effect=TypeError("synthetic index failure")),
              patch("discovery.discover", side_effect=AttributeError("synthetic analysis failure")),
              patch("session.log", side_effect=TypeError("synthetic operation logger failure")),
              patch.object(Path, "open", fail_store_log),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = main(["record", "--root", str(self.root), "--run-id", self.run_id, "--input", "-"])
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        result = json.loads(stdout.getvalue())
        self.assert_committed(result)
        self.assertEqual({warning["code"] for warning in result["warnings"]}, {
            "page_check_cache_failed", "retrieval_index_update_failed", "store_log_failed",
            "post_publish_analysis_failed", "record_log_failed", "response_log_failed",
        })

    def test_active_install_rejects_another_writer_and_new_readers(self):
        existing = Corpus(self.root, self.run_id, lazy_pages=True)
        self.addCleanup(existing.close)
        self.assertTrue(existing.stable())
        script = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import publication
from store import publish
root = Path(sys.argv[2])
original = publication.os.replace
def pause(source, target, *args, **kwargs):
    if Path(target) == root / 'wiki/manifest.json':
        Path(sys.argv[5]).write_text('INSTALLING', encoding='utf-8')
        sys.stdin.readline()
    return original(source, target, *args, **kwargs)
publication.os.replace = pause
publish(root, sys.argv[3], json.loads(sys.argv[4]))
"""
        ready = self.project / "install-ready"
        child = subprocess.Popen([sys.executable, "-c", script, str(SCRIPTS), str(self.root),
                                  self.run_id, json.dumps(self.batch()), str(ready)], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), "writer did not reach staged installation")
            self.assertFalse(existing.stable())
            during_install = self.authoritative_files()
            for operation in ("publish", "read", "start"):
                with self.subTest(operation=operation):
                    contender = """
import sys
sys.path.insert(0, sys.argv[1])
from rag import Corpus
from session import start
from store import publish
try:
    if sys.argv[4] == 'publish':
        publish(sys.argv[2], sys.argv[3], {'records': [{'id': 'Q-OTHER', 'kind': 'Question'}]})
    elif sys.argv[4] == 'read':
        with Corpus(sys.argv[2], sys.argv[3]):
            pass
    else:
        start(sys.argv[5], 'Concurrent open', sys.argv[6])
except ValueError:
    sys.exit(0)
sys.exit(2)
"""
                    result = subprocess.run(
                        [sys.executable, "-c", contender, str(SCRIPTS), str(self.root),
                         self.run_id, operation, self.session_id, str(self.project)],
                        capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.authoritative_files(), during_install)
            stdout, stderr = child.communicate("continue\n", timeout=10)
            self.assertEqual(child.returncode, 0, stderr + stdout)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)
        with Corpus(self.root, self.run_id) as corpus:
            self.assertEqual(corpus.records["Q-1"]["summary"], "Revised question")
            self.assertEqual(corpus.observation("O-NEW")["status"], "ready")
            self.assertNotIn("Q-OTHER", corpus.records)
            self.assertFalse(corpus.page_issues["WK-Q-1"])


class PublicationJournalValidationTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix="webounty-journal-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        folder = root / ".publication"
        folder.mkdir()
        before, after = b"previous authority", b"new authority"
        (root / "state.json").write_bytes(after)
        (folder / "0.old").write_bytes(before)
        journal = {"version": 1, "run_id": "RUN-JOURNAL", "files": [{
            "path": "state.json", "before": hashlib.sha256(before).hexdigest(),
            "after": hashlib.sha256(after).hexdigest(),
        }]}
        return root, folder, journal, after

    def test_missing_before_signature_is_not_treated_as_new_file(self):
        root, folder, journal, after = self.fixture()
        del journal["files"][0]["before"]
        (folder / "journal.json").write_text(json.dumps(journal), encoding="utf-8")
        with self.assertRaises(ValueError):
            publication.recover(root, "RUN-JOURNAL")
        self.assertEqual((root / "state.json").read_bytes(), after)
        self.assertTrue((folder / "journal.json").exists())

    def test_invalid_terminal_markers_refuse_recovery_without_changing_authority(self):
        for marker in ("committed", "rolled_back"):
            for value in (b"not JSON", b"[]", b'{"run_id":"RUN-OTHER"}'):
                with self.subTest(marker=marker, value=value):
                    root, folder, journal, after = self.fixture()
                    (folder / "journal.json").write_text(json.dumps(journal), encoding="utf-8")
                    (folder / marker).write_bytes(value)
                    with self.assertRaises(ValueError):
                        publication.recover(root, "RUN-JOURNAL")
                    self.assertEqual((root / "state.json").read_bytes(), after)
                    self.assertEqual((folder / marker).read_bytes(), value)


if __name__ == "__main__":
    unittest.main()
