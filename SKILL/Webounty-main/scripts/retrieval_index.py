"""Rebuildable SQLite term projection. State, Wiki and evidence remain authoritative.

Warm reads inspect metadata/stat signatures and fetch only query postings. A hit
must still pass Corpus.package's current source/hash checks before evidence use.
No cached text or cached validation verdict is returned as evidence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import sqlite3

from lexical_proximity import pairs, lexical_length


FORMAT_VERSION = "6"


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_encode(value).encode()).hexdigest()


def _metadata(row):
    return {key: value for key, value in row.items() if not key.startswith("_") and key != "text"}


def _references(value):
    """Explicit structured links only, including links nested in knowledge facets."""
    if isinstance(value, dict):
        for field, child in value.items():
            if field.endswith(("_ref", "_refs", "_ids")) or field in {
                    "requires", "steps", "contradicts", "corrected_by", "superseded_by", "contradicted_by"}:
                for item in child if isinstance(child, list) else [child]:
                    if isinstance(item, str):
                        yield item
                    elif isinstance(item, dict) and "id" in item:
                        yield item["id"]
            if isinstance(child, (dict, list)):
                yield from _references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _references(child)


class _Signatures:
    def __init__(self, corpus):
        self.corpus = corpus
        self.files, self.page_candidates = {}, {}
        self.refs = set()

    def file(self, relative):
        self.refs.add("file:" + relative)
        if relative not in self.files:
            path = self.corpus.path(relative)
            try:
                stat = path.stat()
                value = (str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
            except FileNotFoundError:
                value = (str(path), "missing")
            self.files[relative] = value
        return self.files[relative]

    def artifact(self, aid):
        self.refs.add("id:" + aid)
        meta = self.corpus.artifacts.get(aid)
        if meta is None:
            return aid, "missing"
        derived = (meta.get("sha256") in self.corpus.derived_hashes or
                   self.corpus.path(meta["path"]) in self.corpus.derived_paths)
        return meta, self.file(meta["path"]), derived

    def linked_sources(self, block):
        """Invalidate knowledge fields when any reachable premise or source changes.

        This follows provenance metadata; it does not open all source files or
        treat references as proof. Reverse correction edges and page discovery
        candidates ensure newly arrived counterevidence invalidates old entries.
        """
        corpus = self.corpus
        pending_blocks = [block["page_id"] + "/" + block["block_id"]]
        seen_blocks, pending, values = set(), [], []
        while pending_blocks:
            key = pending_blocks.pop()
            if key in seen_blocks:
                continue
            seen_blocks.add(key)
            self.refs.add("id:" + key)
            row = corpus.blocks.get(key)
            if row is None:
                values.append((key, "missing"))
                continue
            page = corpus.pages[row["page_id"]]
            self.refs.add("page:" + row["page_id"])
            self.refs.update("subject:" + sid for sid in page.get("discovery_scope", {}).get("subject_refs", []))
            values.append((key, _metadata(row), self.file(page["path"])))
            pending.extend(_references(row))
            pending.extend(ref if isinstance(ref, str) else ref["id"]
                           for ref in page.get("source_refs", []))
            if hasattr(corpus, "candidates"):
                if row["page_id"] not in self.page_candidates:
                    self.page_candidates[row["page_id"]] = corpus.candidates(page)
                candidates = self.page_candidates[row["page_id"]]
                values.append(("candidates", row["page_id"], candidates))
                pending.extend(item["id"] for item in candidates)
            pending_blocks.extend(ref["page_id"] + "/" + ref["block_id"]
                                  for ref in row.get("required_block_refs", []))
            for ref in row.get("artifact_refs", []):
                values.append(("artifact", ref["artifact_id"], self.artifact(ref["artifact_id"])))
        seen = set()
        while pending:
            rid = pending.pop()
            if rid in seen:
                continue
            seen.add(rid)
            self.refs.add("id:" + rid)
            row = (corpus.records.get(rid) or corpus.entities.get(rid)
                   or corpus.observations.get(rid))
            values.append((rid, row))
            if row is None:
                continue
            pending.extend(_references(row))
            pending.extend(getattr(corpus, "reverse_corrections", {}).get(rid, ()))
            for field in ("artifact_id", "source_artifact_id"):
                if row.get(field):
                    values.append(("artifact", row[field], self.artifact(row[field])))
            for ref in row.get("artifact_refs", []):
                values.append(("artifact", ref["artifact_id"], self.artifact(ref["artifact_id"])))
        return sorted(values, key=_encode)

    def document(self, key, row):
        self.refs = {"id:" + key[1]}
        kind, _ = key
        values = [_metadata(row) if kind == "block" else row]
        if kind == "block":
            page = self.corpus.pages[row["page_id"]]
            pid = row["page_id"]
            while pid:
                self.refs.add("page:" + pid)
                pid = self.corpus.pages[pid].get("parent_page_id")
            # Siblings' prose does not affect this block, but a page file change
            # must be checked to detect unsanctioned edits and broken anchors.
            values.extend(({k: v for k, v in page.items() if k != "blocks"},
                           self.file(page["path"]), self.corpus.navigation_paths[row["page_id"]]))
            if row.get("representation") == "record":
                # Current mirror text is projected from the owner, including
                # external edits that did not advance its declared revision.
                for ref in row.get("source_refs", []):
                    rid = ref if isinstance(ref, str) else ref["id"]
                    self.refs.add("id:" + rid)
                    values.append(self.corpus.records.get(rid))
            if row.get("knowledge"):
                values.append(self.linked_sources(row))
        elif kind == "observation":
            values.extend(self.artifact(row[field]) for field in ("artifact_id", "source_artifact_id")
                          if row.get(field))
        return _digest(values)


def _open(corpus):
    directory = corpus.path("cache")
    directory.mkdir(exist_ok=True)
    connection = sqlite3.connect(corpus.path("cache/retrieval.sqlite"))
    try:
        _initialize(connection, corpus)
    except BaseException:
        connection.close()
        raise
    return connection


def _initialize(connection, corpus):
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents (
            doc_id INTEGER PRIMARY KEY, kind TEXT NOT NULL, rid TEXT NOT NULL,
            signature TEXT NOT NULL, role TEXT, usable INTEGER NOT NULL, UNIQUE(kind, rid));
        CREATE TABLE IF NOT EXISTS fields (
            doc_id INTEGER NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            field TEXT NOT NULL, length INTEGER NOT NULL, PRIMARY KEY(doc_id, field));
        CREATE TABLE IF NOT EXISTS terms (
            term TEXT NOT NULL, doc_id INTEGER NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            field TEXT NOT NULL, count INTEGER NOT NULL, PRIMARY KEY(term, doc_id, field));
        CREATE INDEX IF NOT EXISTS terms_by_document ON terms(doc_id);
        CREATE TABLE IF NOT EXISTS dependencies (
            ref TEXT NOT NULL, doc_id INTEGER NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            PRIMARY KEY(ref, doc_id));
        CREATE INDEX IF NOT EXISTS dependencies_by_document ON dependencies(doc_id);
        CREATE TABLE IF NOT EXISTS file_states (path TEXT PRIMARY KEY, signature TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS field_totals (
            field TEXT PRIMARY KEY, total_length INTEGER NOT NULL, documents INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS source_chunks (
            doc_id INTEGER NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL, artifact_id TEXT NOT NULL,
            byte_offset INTEGER NOT NULL, byte_length INTEGER NOT NULL, sha256 TEXT NOT NULL,
            PRIMARY KEY(doc_id, chunk_index));
        CREATE TABLE IF NOT EXISTS source_terms (
            term TEXT NOT NULL, doc_id INTEGER NOT NULL, chunk_index INTEGER NOT NULL,
            PRIMARY KEY(term, doc_id, chunk_index),
            FOREIGN KEY(doc_id, chunk_index) REFERENCES source_chunks(doc_id, chunk_index) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS source_terms_by_document ON source_terms(doc_id);
    """)
    scope = {"format": FORMAT_VERSION, "run_id": corpus.run_id}
    if dict(connection.execute("SELECT name, value FROM metadata WHERE name IN ('format','run_id')")) != scope:
        connection.execute("DELETE FROM documents")
        connection.execute("DELETE FROM metadata")
        connection.execute("DELETE FROM file_states")
        connection.execute("DELETE FROM field_totals")
        connection.executemany("INSERT INTO metadata VALUES (?, ?)", scope.items())
        connection.commit()


def snapshot(corpus):
    signatures = _Signatures(corpus)
    return {"state_signature": _encode(signatures.file("state.json")),
            "manifest_signature": _encode(signatures.file(corpus.manifest_path))}


def _clear_document(connection, doc_id):
    for field, length in connection.execute("SELECT field, length FROM fields WHERE doc_id=?", (doc_id,)):
        connection.execute("UPDATE field_totals SET total_length=total_length-?, documents=documents-1 WHERE field=?",
                           (length, field))
    for table in ("fields", "terms", "dependencies", "source_chunks"):
        connection.execute("DELETE FROM " + table + " WHERE doc_id=?", (doc_id,))


def _add_field(connection, doc_id, field, counts):
    length = lexical_length(counts)
    if not length:
        return
    connection.execute("INSERT INTO fields VALUES(?,?,?)", (doc_id, field, length))
    connection.execute("""
        INSERT INTO field_totals VALUES(?,?,1) ON CONFLICT(field) DO UPDATE SET
        total_length=total_length+excluded.total_length, documents=documents+1
    """, (field, length))
    connection.executemany("INSERT INTO terms VALUES(?,?,?,?)",
                           ((term, doc_id, field, count) for term, count in counts.items()))


def _index_source(connection, corpus, oid, doc_id, tokenize, totals):
    length = 0
    for number, (locator, text) in enumerate(corpus.source_chunks(oid)):
        counts = Counter(tokenize(text))
        connection.execute("INSERT INTO source_chunks VALUES(?,?,?,?,?,?)",
            (doc_id, number, locator["artifact_id"], locator["offset"], locator["length"], locator["sha256"]))
        connection.executemany("INSERT INTO source_terms VALUES(?,?,?)",
                               ((term, doc_id, number) for term in counts))
        connection.executemany("""
            INSERT INTO terms VALUES(?,?,'source',?) ON CONFLICT(term,doc_id,field) DO UPDATE SET
            count=count+excluded.count
        """, ((term, doc_id, amount) for term, amount in counts.items()))
        length += sum(counts.values())
        totals["source_chunks_indexed"] += 1
    if length:
        connection.execute("INSERT INTO fields VALUES(?,'source',?)", (doc_id, length))
        connection.execute("""
            INSERT INTO field_totals VALUES('source',?,1) ON CONFLICT(field) DO UPDATE SET
            total_length=total_length+excluded.total_length, documents=documents+1
        """, (length,))


def _changed_keys(connection, documents, refs, keys):
    connection.execute("CREATE TEMP TABLE changed_refs (ref TEXT PRIMARY KEY)")
    connection.executemany("INSERT INTO changed_refs VALUES(?)", ((ref,) for ref in refs))
    result = set(keys)
    # Temp tables have no cardinality statistics. Keep the small change set as
    # the outer loop; an ordinary JOIN can scan every persisted dependency.
    result.update((kind, rid) for kind, rid in connection.execute("""
        SELECT DISTINCT d.kind, d.rid FROM changed_refs c
        CROSS JOIN dependencies x ON x.ref=c.ref JOIN documents d ON d.doc_id=x.doc_id
    """))
    return result


def _corrupt_cache_error(error):
    # Python 3.10 exposes neither sqlite_errorcode nor the named result constants.
    # SQLite's stable primary codes are CORRUPT=11 and NOTADB=26.
    code = getattr(error, "sqlite_errorcode", None)
    if code is not None:
        return code & 0xFF in {11, 26}
    return str(error) in {"database disk image is malformed", "file is not a database"}


def lexical_projection(corpus, documents, query_terms, fields_for, tokenize, role_for, *, changes=None,
                       original_terms=None):
    """Rebuild a corrupt derived cache once, without masking lock or I/O errors."""
    for attempt in range(2):
        try:
            return _lexical_projection(corpus, documents, query_terms, fields_for, tokenize, role_for,
                                       changes=changes, original_terms=original_terms)
        except sqlite3.DatabaseError as exc:
            if attempt or not _corrupt_cache_error(exc):
                raise
            # The failed attempt closes its connection before removing only this
            # replaceable projection. Authoritative state and evidence stay intact.
            corpus.path("cache/retrieval.sqlite").unlink()


def _lexical_projection(corpus, documents, query_terms, fields_for, tokenize, role_for, *, changes=None,
                        original_terms=None):
    """Consume publication changes, reconcile external edits, then fetch only query postings."""
    from wiki_structure import navigation_paths

    if not hasattr(corpus, "navigation_paths"):
        corpus.navigation_paths = navigation_paths(corpus.pages)
    signatures, connection = _Signatures(corpus), _open(corpus)
    totals = {"documents": len(documents), "reused_documents": 0, "indexed_documents": 0,
              "deleted_documents": 0, "tokenized_fields": 0, "signature_checks": 0,
              "source_chunks_indexed": 0, "file_checks": 0}
    roles, unavailable, field_cache = {}, set(), {}
    try:
        metadata = dict(connection.execute("SELECT name, value FROM metadata"))
        current_snapshot = snapshot(corpus)
        expected_snapshot = changes["before"] if changes else current_snapshot
        incremental = all(metadata.get(key) == value for key, value in expected_snapshot.items())
        changed_refs = set(changes["refs"]) if changes else set()
        for relative, previous in connection.execute("SELECT path, signature FROM file_states"):
            totals["file_checks"] += 1
            if _encode(signatures.file(relative)) != previous:
                changed_refs.add("file:" + relative)
        totals["full_reconciliation"] = not incremental
        connection.execute("BEGIN")
        if incremental:
            selected = _changed_keys(connection, documents, changed_refs, changes["keys"] if changes else ())
            stored = {}
            for key in selected:
                row = connection.execute(
                    "SELECT doc_id, signature, role, usable FROM documents WHERE kind=? AND rid=?", key).fetchone()
                if row is not None:
                    stored[key] = row
        else:
            stored = {(kind, rid): (doc_id, signature, role, usable)
                      for doc_id, kind, rid, signature, role, usable in connection.execute(
                          "SELECT doc_id, kind, rid, signature, role, usable FROM documents")}
            selected = documents.keys() | stored.keys()
        for key in sorted(selected):
            previous = stored.get(key)
            if key not in documents:
                if previous is not None:
                    _clear_document(connection, previous[0])
                    connection.execute("DELETE FROM documents WHERE doc_id=?", (previous[0],))
                    totals["deleted_documents"] += 1
                continue
            row = documents[key]
            totals["signature_checks"] += 1
            signature = signatures.document(key, row)
            if previous is not None and previous[1] == signature:
                continue
            if key[0] == "block" and hasattr(corpus, "ensure_page"):
                corpus.ensure_page(row["page_id"])
            usable = not (key[0] == "block" and (row.get("_issues") or corpus.page_issues.get(row["page_id"])))
            role = role_for(row) if key[0] == "block" else None
            if previous is not None:
                doc_id = previous[0]
                _clear_document(connection, doc_id)
                connection.execute("UPDATE documents SET signature=?, role=?, usable=? WHERE doc_id=?",
                                   (signature, role, usable, doc_id))
            else:
                doc_id = connection.execute(
                    "INSERT INTO documents(kind,rid,signature,role,usable) VALUES(?,?,?,?,?)",
                    (*key, signature, role, usable)).lastrowid
            connection.executemany("INSERT INTO dependencies VALUES(?,?)",
                                   ((ref, doc_id) for ref in signatures.refs))
            totals["indexed_documents"] += 1
            if not usable:
                continue
            for field, value in fields_for(key[0], row, corpus).items():
                if not value:
                    continue
                counts = field_cache.get(value)
                if counts is None:
                    counts = Counter(tokenize(value))
                    counts.update(pairs(value))
                    totals["tokenized_fields"] += 1
                    if len(value) <= 4096 and len(field_cache) < 128:
                        field_cache[value] = counts
                _add_field(connection, doc_id, field, counts)
            if key[0] == "observation":
                _index_source(connection, corpus, key[1], doc_id, tokenize, totals)
                corpus.release_observation(key[1])
        totals["reused_documents"] = len(documents) - totals["indexed_documents"]
        if selected:
            connection.executemany("""
                INSERT INTO file_states VALUES(?,?) ON CONFLICT(path) DO UPDATE SET signature=excluded.signature
            """, ((relative, _encode(value)) for relative, value in signatures.files.items()))
            connection.execute("DELETE FROM file_states WHERE 'file:'||path NOT IN (SELECT ref FROM dependencies)")
        averages = {field: total / number for field, total, number in connection.execute(
            "SELECT field, total_length, documents FROM field_totals WHERE documents>0")}
        postings, field_lengths = defaultdict(dict), defaultdict(dict)
        original_terms = set(query_terms) if original_terms is None else original_terms
        connection.execute("CREATE TEMP TABLE query_terms (term TEXT PRIMARY KEY, original INTEGER NOT NULL)")
        connection.executemany("INSERT INTO query_terms VALUES(?,?)",
                               ((term, int(term in original_terms)) for term in query_terms))
        # Drive both lookups with the query, not the complete inverted index.
        # CROSS JOIN preserves that order even without ANALYZE statistics for
        # these per-request temp tables; equality still uses the term indexes.
        for term, kind, rid, field, count, length, role, usable in connection.execute("""
            SELECT t.term, d.kind, d.rid, t.field, t.count, f.length, d.role, d.usable
            FROM query_terms q CROSS JOIN terms t ON t.term=q.term
            JOIN documents d ON d.doc_id=t.doc_id
            JOIN fields f ON f.doc_id=t.doc_id AND f.field=t.field
        """):
            key = kind, rid
            postings[term].setdefault(key, {})[field] = count
            field_lengths[key][field] = length
            if kind == "block":
                roles[key] = role
                if not usable:
                    unavailable.add(key)
        corpus.retrieval_source_matches = {}
        for oid, aid, offset, length, checksum, matches, original_matches in connection.execute("""
            SELECT d.rid, c.artifact_id, c.byte_offset, c.byte_length, c.sha256, COUNT(*), SUM(q.original)
            FROM query_terms q CROSS JOIN source_terms t ON q.term=t.term
            JOIN source_chunks c ON c.doc_id=t.doc_id AND c.chunk_index=t.chunk_index
            JOIN documents d ON d.doc_id=c.doc_id
            GROUP BY c.doc_id,c.chunk_index ORDER BY SUM(q.original) DESC,COUNT(*) DESC,c.byte_offset
        """):
            hit = corpus.retrieval_source_matches.get(oid)
            if hit is None:
                corpus.retrieval_source_matches[oid] = {
                    "artifact_id": aid, "offset": offset, "length": length, "sha256": checksum,
                    "matched_query_terms": matches, "matched_original_query_terms": original_matches,
                    "matching_chunks": 1, "selection": "representative_window",
                    "evidence": False}
            else:
                hit["matching_chunks"] += 1
        if corpus.stable():
            connection.executemany("""
                INSERT INTO metadata VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value
            """, {**current_snapshot, "state_revision": str(corpus.state["revision"])}.items())
            connection.commit()
        else:
            connection.rollback()
            totals["snapshot_changed"] = True
        corpus.retrieval_index_stats = totals
        return postings, field_lengths, averages, roles, unavailable
    finally:
        connection.close()


def publication_changes(before, current, result):
    refs, keys = set(), set()
    for group, kind, result_key in (("records", "record", "changed_record_ids"),
                                   ("entities", "entity", "changed_entity_ids"),
                                   ("observations", "observation", "observation_ids")):
        for rid in result[result_key]:
            keys.add((kind, rid))
            refs.add("id:" + rid)
            for corpus in (before, current):
                row = getattr(corpus, group).get(rid, {})
                refs.update("subject:" + sid for sid in row.get("subject_refs", []))
                if kind == "record":
                    refs.update("id:" + target for target in _references(row))
                if kind == "entity":
                    refs.add("subject:" + rid)
    changed_pages = set(result["changed_page_ids"])
    refs.update("page:" + pid for pid in changed_pages)
    keys.update(("block", rid) for rid, row in current.blocks.items() if row["page_id"] in changed_pages)
    return {"before": before.index_snapshot, "refs": refs, "keys": keys}


def sync_publication(before, root, run_id, result, metrics=None):
    from rag import Corpus
    from search_index import _fields, _terms, _role

    with Corpus(root, run_id, lazy_pages=True, metrics=metrics) as corpus:
        documents = {(kind, rid): row for kind, group in (
            ("record", corpus.records), ("entity", corpus.entities),
            ("observation", corpus.observations), ("block", corpus.blocks)) for rid, row in group.items()}
        lexical_projection(corpus, documents, (), _fields, _terms, _role,
                           changes=publication_changes(before, corpus, result))
        if corpus.retrieval_index_stats.get("snapshot_changed"):
            raise ValueError("session changed during indexing; retrieve current state")
        from metadata_cache import save
        save(corpus, before, result)
        return corpus.retrieval_index_stats
