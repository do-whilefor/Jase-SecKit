"""Derived metadata recovers from corruption without hiding source or I/O errors."""

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from benchmark_retrieval import make_corpus, RUN_ID, QUERY, CONSUMER
import metadata_cache
from rag import Corpus, retrieve


class MetadataCacheRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        make_corpus(self.root, 6, 128)
        self.path = self.root / metadata_cache.PATH
        self.expected = self.query()

    def query(self, **kwargs):
        return retrieve(self.root, RUN_ID, QUERY, [CONSUMER], view="compact", **kwargs)

    def corpus(self, cached=False, metrics=None):
        corpus = Corpus(self.root, RUN_ID, lazy_pages=True, lazy_metadata=cached, metrics=metrics)
        self.addCleanup(corpus.close)
        return corpus

    def edit_cache(self, sql, values=()):
        db = sqlite3.connect(self.path)
        try:
            db.execute(sql, values)
            db.commit()
        finally:
            db.close()

    def sources(self):
        return {str(path.relative_to(self.root)): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()
                and "cache" not in path.relative_to(self.root).parts}

    def assert_closed(self, db):
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute("SELECT 1")

    def test_corrupt_query_rebuilds_then_reuses_cache_without_changing_sources(self):
        sources = self.sources()
        self.path.write_bytes(b"not a SQLite database")
        self.assertEqual(self.query(), self.expected)
        metrics = {}
        with patch.object(Corpus, "read_json", side_effect=AssertionError("whole JSON reopened")):
            self.assertEqual(self.query(metrics=metrics), self.expected)
        self.assertEqual(metrics["counts"]["metadata_cache_hits"], 1)
        self.assertEqual(self.sources(), sources)

    def test_save_rebuilds_corruption_after_closing_failed_connection(self):
        corpus, connections = self.corpus(), []
        connect, discard = sqlite3.connect, metadata_cache._discard

        def track(*args, **kwargs):
            db = connect(*args, **kwargs)
            connections.append(db)
            return db

        def discard_closed(path):
            for db in connections:
                self.assert_closed(db)
            discard(path)

        self.path.write_bytes(b"damaged SQLite")
        with patch.object(metadata_cache.sqlite3, "connect", side_effect=track), \
                patch.object(metadata_cache, "_discard", side_effect=discard_closed) as removed:
            metadata_cache.save(corpus)
        self.assertEqual(removed.call_count, 1)
        self.assertEqual(len(connections), 2)
        for db in connections:
            self.assert_closed(db)
        self.assertEqual(self.query(), self.expected)

    def test_invalid_header_rebuilds_in_place(self):
        reader = self.corpus(cached=True)
        header = reader.metadata.header
        reader.close()
        malformed = [json.dumps({**header, field: []}) for field in ("state", "manifest", "files")]
        for value in ("{", "null", "[]", "{}", *malformed):
            with self.subTest(header=value):
                self.edit_cache("UPDATE metadata SET value=? WHERE name='header'", (value,))
                with patch.object(metadata_cache, "_discard", side_effect=AssertionError("cache unlinked")):
                    self.assertEqual(self.query(), self.expected)

    def test_missing_schema_rebuilds_all_rows_and_relations_even_with_incremental_changes(self):
        corpus = self.corpus()
        changes = {"changed_record_ids": [CONSUMER], "changed_entity_ids": [],
                   "observation_ids": [], "changed_page_ids": []}
        for table in ("metadata", "rows", "relations"):
            with self.subTest(table=table):
                self.edit_cache("DROP TABLE " + table)
                self.assertIsNone(metadata_cache.open_current(corpus))
                with patch.object(metadata_cache, "_discard", side_effect=AssertionError("cache unlinked")):
                    metadata_cache.save(corpus, before=corpus, changes=changes)
                self.assertEqual(self.query(), self.expected)

    def test_incomplete_or_wrong_scope_header_rebuilds_from_authoritative_sources(self):
        reader = self.corpus(cached=True)
        header = reader.metadata.header
        reader.close()
        malformed = [{**header, "state": {}}, {**header, "manifest": {}},
                     {**header, "state": {**header["state"], "run_id": "another-run"}},
                     {**header, "manifest": {**header["manifest"], "run_id": "another-run"}}]
        malformed.extend({**header, "state": {**header["state"], "revision": revision}}
                         for revision in (None, True, "1", 1.0))
        sources = self.sources()
        for value in malformed:
            with self.subTest(header=value):
                self.edit_cache("UPDATE metadata SET value=? WHERE name='header'", (json.dumps(value),))
                with patch.object(metadata_cache, "_discard", side_effect=AssertionError("cache unlinked")):
                    self.assertEqual(self.query(), self.expected)
        self.assertEqual(self.sources(), sources)

    def test_missing_column_rebuilds_in_place(self):
        self.edit_cache("ALTER TABLE rows RENAME COLUMN payload TO obsolete_payload")
        with patch.object(metadata_cache, "_discard", side_effect=AssertionError("cache unlinked")):
            self.assertEqual(self.query(), self.expected)

    def test_header_repair_preserves_existing_wal_reader_snapshot(self):
        reader = self.corpus(cached=True)
        state_path = self.root / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        old_summary = state["records"][CONSUMER]["summary"]
        state["records"][CONSUMER]["summary"] = "new authoritative summary"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.edit_cache("UPDATE metadata SET value='null' WHERE name='header'")
        with patch.object(metadata_cache, "_discard", side_effect=AssertionError("cache unlinked")):
            metadata_cache.save(self.corpus())
        self.assertEqual(reader.records[CONSUMER]["summary"], old_summary)
        self.assertFalse(reader.stable())
        self.assertEqual(self.corpus(cached=True).records[CONSUMER]["summary"], "new authoritative summary")

    def test_open_and_save_close_connections_on_unexpected_errors(self):
        corpus = self.corpus()
        for operation, target in ((metadata_cache.open_current, "Metadata"),
                                  (metadata_cache.save, "_header")):
            with self.subTest(operation=operation.__name__):
                db = sqlite3.connect(self.path)
                with patch.object(metadata_cache.sqlite3, "connect", return_value=db), \
                        patch.object(metadata_cache, target, side_effect=RuntimeError("injected failure")):
                    with self.assertRaisesRegex(RuntimeError, "injected failure"):
                        operation(corpus)
                self.assert_closed(db)

    def test_lock_permission_and_io_errors_close_connections_without_discarding_cache(self):
        corpus = self.corpus()
        original = self.path.read_bytes()
        for operation in (metadata_cache.open_current, metadata_cache.save):
            for message in ("database is locked", "database table is locked", "disk I/O error",
                            "attempt to write a readonly database", "unable to open database file",
                            "unrecognized database failure"):
                with self.subTest(operation=operation.__name__, error=message):
                    db = Mock()
                    db.execute.side_effect = sqlite3.OperationalError(message)
                    with patch.object(metadata_cache.sqlite3, "connect", return_value=db), \
                            patch.object(metadata_cache, "_discard") as discarded:
                        with self.assertRaisesRegex(sqlite3.OperationalError, message):
                            operation(corpus)
                    db.close.assert_called_once()
                    discarded.assert_not_called()
                    self.assertEqual(self.path.read_bytes(), original)

    def test_corruption_classification_supports_python_310_and_respects_error_codes(self):
        for message in ("database disk image is malformed", "file is not a database",
                        "malformed database schema (rows) - invalid rootpage"):
            error = sqlite3.DatabaseError(message)
            self.assertFalse(hasattr(error, "sqlite_errorcode"))
            self.assertTrue(metadata_cache._corrupt(error))
        error = sqlite3.DatabaseError("file is not a database")
        error.sqlite_errorcode = 10  # SQLITE_IOERR must take precedence over text.
        self.assertFalse(metadata_cache._corrupt(error))
        error.sqlite_errorcode = 11 | (1 << 8)  # An extended SQLITE_CORRUPT code.
        self.assertTrue(metadata_cache._corrupt(error))

    def test_real_exclusive_lock_is_reported_and_cache_remains_usable(self):
        corpus, connections = self.corpus(), []
        connect = sqlite3.connect

        def immediate(*args, **kwargs):
            db = connect(*args, timeout=0, **kwargs)
            connections.append(db)
            return db

        lock = connect(self.path)
        try:
            lock.execute("PRAGMA journal_mode=DELETE")
            lock.execute("BEGIN EXCLUSIVE")
            with patch.object(metadata_cache.sqlite3, "connect", side_effect=immediate), \
                    patch.object(metadata_cache, "_discard") as discarded:
                for operation in (metadata_cache.open_current, metadata_cache.save):
                    with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                        operation(corpus)
                discarded.assert_not_called()
            for db in connections:
                self.assert_closed(db)
        finally:
            lock.close()
        self.assertEqual(self.query(), self.expected)


if __name__ == "__main__":
    unittest.main()
