"""A corrupt derived projection is recoverable; unrelated DB errors remain visible."""

from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rag import Corpus
from search_index import rank
import retrieval_index
from session import start
from store import publish


class RetrievalCacheRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.info = start("cache-recovery", "synthetic cache checks", temporary.name)
        self.root = Path(self.info["root"])
        publish(self.root, self.info["run_id"], {"records": [
            {"id": "R-HIT", "kind": "Question", "summary": "needle", "status": "open"}]})
        self.cache = self.root / "cache/retrieval.sqlite"

    def search(self):
        with Corpus(self.root, self.info["run_id"], lazy_pages=True, lazy_metadata=True) as corpus:
            return rank(corpus, "needle", [], with_reasons=True)

    def test_corrupt_cache_rebuilds_and_next_query_reuses_it(self):
        self.cache.unlink()
        expected = self.search()
        state = (self.root / "state.json").read_bytes()
        self.cache.write_bytes(b"broken derived cache")
        connect = sqlite3.connect

        def tracked_connect(*args, **kwargs):
            connection = connect(*args, **kwargs)
            self.addCleanup(connection.close)
            return connection

        with patch.object(retrieval_index.sqlite3, "connect", side_effect=tracked_connect):
            self.assertEqual(self.search(), expected)
        self.assertEqual((self.root / "state.json").read_bytes(), state)
        with patch("search_index._fields", side_effect=AssertionError("warm query rebuilt text")):
            self.assertEqual(self.search(), expected)
        self.cache.unlink()
        self.assertEqual(self.search(), expected)

    def test_source_locator_and_authoritative_files_survive_cache_recovery(self):
        source = self.root.parent / "source.txt"
        source.write_bytes(b" " * 65534 + b"exporter /api/report_download\n")
        publish(self.root, self.info["run_id"], {"observations": [
            {"id": "O-SOURCE", "source_path": str(source), "content": {"note": "original"}}]})
        authoritative = {path: path.read_bytes() for path in self.root.rglob("*")
                         if path.is_file() and "cache" not in path.relative_to(self.root).parts}

        def source_match():
            with Corpus(self.root, self.info["run_id"], lazy_pages=True, lazy_metadata=True) as corpus:
                ranked = rank(corpus, "exporter /api/report_download", [], with_reasons=True)
                self.assertIn(("observation", "O-SOURCE"), ranked[0])
                match = corpus.retrieval_source_matches["O-SOURCE"]
                artifact = corpus.artifacts[match["artifact_id"]]
                raw = (self.root / artifact["path"]).read_bytes()
                window = raw[match["offset"]:match["offset"] + match["length"]]
                self.assertIn(b"exporter /api/report_download", window)
                self.assertEqual(hashlib.sha256(window).hexdigest(), match["sha256"])
                return ranked, match

        expected = source_match()
        self.cache.write_bytes(b"broken source projection")
        self.assertEqual(source_match(), expected)
        with patch("rag.text_chunks", side_effect=AssertionError("warm query reread source chunks")):
            self.assertEqual(source_match(), expected)
        self.assertEqual({path: path.read_bytes() for path in authoritative}, authoritative)

    def test_previous_format_drops_stale_partial_terms_before_reuse(self):
        # Format 5 could index an identifier fragment at a source window edge.
        with closing(sqlite3.connect(self.cache)) as connection:
            connection.execute("UPDATE metadata SET value='5' WHERE name='format'")
            connection.execute("UPDATE terms SET term='need' WHERE term='needle'")
            connection.commit()
        with Corpus(self.root, self.info["run_id"], lazy_pages=True, lazy_metadata=True) as corpus:
            self.assertNotIn(("record", "R-HIT"), rank(corpus, "need", [])[0])
            self.assertIn(("record", "R-HIT"), rank(corpus, "needle", [])[0])
        with closing(sqlite3.connect(self.cache)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM metadata WHERE name='format'").fetchone(),
                             (retrieval_index.FORMAT_VERSION,))
        with patch("search_index._fields", side_effect=AssertionError("migrated cache rebuilt text")):
            self.assertIn(("record", "R-HIT"), self.search()[0])

    def test_failed_initialization_closes_connection(self):
        connection = Mock()
        connection.executescript.side_effect = sqlite3.OperationalError("database is locked")
        with Corpus(self.root, self.info["run_id"], lazy_pages=True) as corpus:
            with patch.object(retrieval_index.sqlite3, "connect", return_value=connection):
                with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                    retrieval_index._open(corpus)
        connection.close.assert_called_once_with()

    def test_non_corruption_error_never_discards_cache(self):
        original = self.cache.read_bytes()
        failure = sqlite3.OperationalError("database is locked")
        failure.sqlite_errorcode = 5  # SQLITE_BUSY; Python 3.10 has no named error constants.
        with patch.object(retrieval_index, "_open", side_effect=failure) as opened:
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                self.search()
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(self.cache.read_bytes(), original)

    def test_corruption_during_postings_read_closes_then_rebuilds(self):
        expected = self.search()
        opener = retrieval_index._open
        failed_connections = []

        def fail_once(corpus):
            connection = opener(corpus)
            if failed_connections:
                return connection
            proxy = Mock(wraps=connection)

            def execute(sql, *args):
                if "FROM query_terms" in sql:
                    failure = sqlite3.DatabaseError("database disk image is malformed")
                    failure.sqlite_errorcode = 11 | (1 << 8)  # Extended SQLITE_CORRUPT.
                    raise failure
                return connection.execute(sql, *args)

            proxy.execute.side_effect = execute
            failed_connections.append(proxy)
            return proxy

        with patch.object(retrieval_index, "_open", side_effect=fail_once) as opened:
            self.assertEqual(self.search(), expected)
        self.assertEqual(opened.call_count, 2)
        failed_connections[0].close.assert_called_once_with()

    def test_repeated_corruption_stops_after_one_rebuild_attempt(self):
        failure = sqlite3.DatabaseError("database disk image is malformed")
        failure.sqlite_errorcode = 11  # SQLITE_CORRUPT.
        with patch.object(retrieval_index, "_open", side_effect=failure) as opened:
            with self.assertRaises(sqlite3.DatabaseError):
                self.search()
        self.assertEqual(opened.call_count, 2)

    def test_legacy_python_recovers_only_exact_native_corruption_messages(self):
        expected = self.search()
        opener = retrieval_index._open
        for message in ("file is not a database", "database disk image is malformed"):
            with self.subTest(message=message):
                failures = [sqlite3.DatabaseError(message)]
                self.assertFalse(hasattr(failures[0], "sqlite_errorcode"))

                def fail_once(corpus):
                    if failures:
                        raise failures.pop()
                    return opener(corpus)

                with patch.dict(sqlite3.__dict__):
                    for name in ("SQLITE_CORRUPT", "SQLITE_NOTADB", "SQLITE_BUSY"):
                        sqlite3.__dict__.pop(name, None)
                    with patch.object(retrieval_index, "_open", side_effect=fail_once) as opened:
                        self.assertEqual(self.search(), expected)
                self.assertEqual(opened.call_count, 2)

    def test_legacy_python_keeps_cache_for_other_database_errors(self):
        original = self.cache.read_bytes()
        for message in ("database is locked", "disk I/O error", "attempt to write a readonly database",
                        "database disk image is malformed: unrelated custom error"):
            with self.subTest(message=message), patch.dict(sqlite3.__dict__):
                for name in ("SQLITE_CORRUPT", "SQLITE_NOTADB", "SQLITE_BUSY"):
                    sqlite3.__dict__.pop(name, None)
                failure = sqlite3.DatabaseError(message)
                with patch.object(retrieval_index, "_open", side_effect=failure) as opened:
                    with self.assertRaises(sqlite3.DatabaseError):
                        self.search()
                self.assertEqual(opened.call_count, 1)
                self.assertEqual(self.cache.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
