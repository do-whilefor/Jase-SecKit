"""Rebuildable, row-addressed query metadata and authored relation indexes.

JSON and Wiki files remain authoritative. Readers hold a SQLite snapshot whose
source file fingerprints must still match; evidence bytes are verified by Corpus.
"""

from collections.abc import Mapping
import json
import sqlite3

from evidence_io import fingerprint
from telemetry import count


VERSION = 1
PATH = "cache/metadata.sqlite"
GROUPS = {"record": "records", "entity": "entities", "observation": "observations",
          "artifact": "artifacts", "page": "pages", "block": "blocks"}
TABLE_COLUMNS = {"metadata": {"name", "value"},
                 "rows": {"kind", "rid", "owner", "payload"},
                 "relations": {"name", "lookup", "owner", "value"}}


def _corrupt(error):
    if not isinstance(error, sqlite3.DatabaseError):
        return False
    code = getattr(error, "sqlite_errorcode", None)
    if code is not None:
        return code & 255 in {11, 26}  # SQLITE_CORRUPT / SQLITE_NOTADB, including extended codes.
    # Python 3.10 does not expose SQLite error codes. Be deliberately narrow:
    # lock, permission and I/O failures must never discard a usable database.
    return str(error).lower().startswith(("database disk image is malformed",
                                         "file is not a database", "malformed database schema"))


def _discard(path):
    # Only called for confirmed SQLite corruption, after closing our connection.
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)


def _schema_current(db):
    return all(columns <= {row[1] for row in db.execute("PRAGMA table_info(" + table + ")")}
               for table, columns in TABLE_COLUMNS.items())


def _header(db):
    row = db.execute("SELECT value FROM metadata WHERE name='header'").fetchone()
    try:
        header = json.loads(row[0]) if row else {}
    except (ValueError, TypeError, UnicodeError):
        return {}
    if not isinstance(header, dict) or any(not isinstance(header.get(key), dict)
                                          for key in ("files", "state", "manifest")):
        return {}
    if (type(header["state"].get("revision")) is not int
            or any(header[key].get("run_id") != header.get("run_id") for key in ("state", "manifest"))):
        return {}
    return header


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def frozen(value):
    return tuple(frozen(part) for part in value) if isinstance(value, list) else value


class Rows(Mapping):
    def __init__(self, metadata, kind):
        self.metadata, self.kind, self.loaded = metadata, kind, {}

    def __getitem__(self, rid):
        if rid not in self.loaded:
            row = self.metadata.db.execute(
                "SELECT payload FROM rows WHERE kind=? AND rid=?", (self.kind, rid)).fetchone()
            if row is None:
                raise KeyError(rid)
            self.loaded[rid] = json.loads(row[0])
            count(self.metadata.metrics, "metadata_rows_loaded")
        return self.loaded[rid]

    def __contains__(self, rid):
        return rid in self.loaded or self.metadata.db.execute(
            "SELECT 1 FROM rows WHERE kind=? AND rid=?", (self.kind, rid)).fetchone() is not None

    def __iter__(self):
        return (row[0] for row in self.metadata.db.execute(
            "SELECT rid FROM rows WHERE kind=? ORDER BY rid", (self.kind,)))

    def __len__(self):
        return self.metadata.sizes.get(self.kind, 0)

    @property
    def relations(self):
        return self.metadata


class Links(Mapping):
    """A persisted adjacency lookup; absent keys have no declared links."""
    def __init__(self, metadata, name):
        self.metadata, self.name, self.loaded = metadata, name, {}

    def __getitem__(self, key):
        if self.name == "derived_path":
            key = str(key)
        key = frozen(key)
        if key not in self.loaded:
            self.loaded[key] = {frozen(json.loads(row[0])) for row in self.metadata.db.execute(
                "SELECT value FROM relations WHERE name=? AND lookup=?", (self.name, encoded(key)))}
            count(self.metadata.metrics, "relation_lookups")
        return self.loaded[key]

    def __contains__(self, key):
        return bool(self[key])

    def __iter__(self):
        return (frozen(json.loads(row[0])) for row in self.metadata.db.execute(
            "SELECT DISTINCT lookup FROM relations WHERE name=? ORDER BY lookup", (self.name,)))

    def __len__(self):
        return self.metadata.db.execute(
            "SELECT COUNT(DISTINCT lookup) FROM relations WHERE name=?", (self.name,)).fetchone()[0]


class Documents(Mapping):
    def __init__(self, corpus):
        self.groups = {kind: getattr(corpus, GROUPS[kind]) for kind in
                       ("record", "entity", "observation", "block")}

    def __getitem__(self, key):
        return self.groups[key[0]][key[1]]

    def __contains__(self, key):
        return key[0] in self.groups and key[1] in self.groups[key[0]]

    def __iter__(self):
        return ((kind, rid) for kind, group in self.groups.items() for rid in group)

    def __len__(self):
        return sum(map(len, self.groups.values()))


class CycleDependencies:
    def __init__(self, corpus):
        self.corpus, self.loaded = corpus, {}

    def __getitem__(self, rid):
        if rid not in self.loaded:
            from rag import dependencies, ref_ids
            row = self.corpus.records[rid]
            contradicted = set(ref_ids(row.get("contradicts", [])))
            paired = {target for target in contradicted if rid in ref_ids(
                self.corpus.records.get(target, {}).get("contradicted_by", []))}
            self.loaded[rid] = dependencies({**row, "contradicts": sorted(contradicted - paired)})
        return self.loaded[rid]


class ImpactEdges:
    def __init__(self, corpus, nodes):
        self.corpus, self.nodes, self.loaded = corpus, nodes, {}

    def __getitem__(self, node):
        if node not in self.loaded:
            metadata = self.corpus.metadata
            values = set(metadata.links("impact")[node[1]])
            if node[0] in {"record", "observation"}:
                row = getattr(self.corpus, GROUPS[node[0]])[node[1]]
                for pid in metadata.union("scoped_page", row.get("subject_refs", [])):
                    values.add((pid, "scoped_" + node[0] + "_changed"))
            self.loaded[node] = {(self.nodes[target], reason) for target, reason in values if target in self.nodes}
        return self.loaded[node]


class Metadata:
    def __init__(self, db, header, metrics):
        self.db, self.header, self.metrics = db, header, metrics
        self.sizes = dict(db.execute("SELECT kind, COUNT(*) FROM rows GROUP BY kind"))
        self.lookups = {}

    def links(self, name):
        if name not in self.lookups:
            self.lookups[name] = Links(self, name)
        return self.lookups[name]

    def union(self, name, keys):
        lookup = self.links(name)
        return set().union(*(lookup[key] for key in keys))

    def bind(self, corpus):
        corpus.metadata = self
        for kind, group in GROUPS.items():
            setattr(corpus, group, Rows(self, kind))
        corpus.state = {**self.header["state"], **{
            group: getattr(corpus, group) for group in ("records", "entities", "observations", "artifacts")}}
        corpus.manifest = {**self.header["manifest"], "pages": corpus.pages.values()}
        corpus.subject_index = self.links("subject")
        corpus.record_dependencies = self.links("dependency")
        corpus.reverse_corrections = self.links("reverse_correction")
        corpus.cycle_dependencies = CycleDependencies(corpus)
        corpus.derived_paths = self.links("derived_path")
        corpus.derived_hashes = self.links("derived_hash")
        corpus.navigation_paths = Rows(self, "navigation")
        for relative, previous in self.header["files"].items():
            corpus.read_files[corpus.path(relative)] = tuple(previous)
        count(corpus.metrics, "metadata_cache_hits")

    def close(self):
        self.db.close()


def open_current(corpus):
    path = corpus.path(PATH)
    if not path.exists():
        return None
    db = sqlite3.connect(path)
    try:
        db.execute("BEGIN")
        header = _header(db) if _schema_current(db) else {}
        current = {relative: list(fingerprint(corpus.path(relative))) for relative in
                   ("state.json", corpus.manifest_path) if corpus.path(relative).exists()}
        if (header.get("version") != VERSION or header.get("run_id") != corpus.run_id
                or header.get("files") != current or len(current) != 2):
            db.close()
            return None
        return Metadata(db, header, corpus.metrics)
    except BaseException as error:
        db.close()
        if not _corrupt(error):
            raise
        _discard(path)
        return None


def save(corpus, before=None, changes=None):
    try:
        _save(corpus, before, changes)
    except sqlite3.DatabaseError as error:
        if not _corrupt(error):
            raise
        _discard(corpus.path(PATH))
        _save(corpus)  # A recovered cache always needs every owner and relation.


def _save(corpus, before=None, changes=None):
    """Update changed owners, including their old edges and removed Wiki blocks."""
    from discovery import CORRECTIONS, _names, _support_refs, _terms
    from capability_hints import _spec_terms, _terms as hint_terms
    from rag import dependencies, ref_ids
    from wiki_structure import navigation_paths

    if corpus.load_issues or not corpus.stable():
        return
    path = corpus.path(PATH)
    path.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(path)
    try:
        # An existing reader may finish against its old snapshot while the sole
        # publisher advances the cache. No source validity is inferred from WAL.
        db.execute("PRAGMA journal_mode=WAL")
        reset = "" if _schema_current(db) else "".join(
            "DROP TABLE IF EXISTS " + table + ";" for table in TABLE_COLUMNS)
        db.executescript("BEGIN;" + reset + """
            CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS rows (
                kind TEXT NOT NULL, rid TEXT NOT NULL, owner TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(kind,rid));
            CREATE INDEX IF NOT EXISTS rows_owner ON rows(owner);
            CREATE TABLE IF NOT EXISTS relations (
                name TEXT NOT NULL, lookup TEXT NOT NULL, owner TEXT NOT NULL, value TEXT NOT NULL,
                PRIMARY KEY(name,lookup,owner,value));
            CREATE INDEX IF NOT EXISTS relations_owner ON relations(owner);
        """)
        previous = _header(db)
        prior_files = ({relative: list(before.read_files[before.path(relative)]) for relative in
                        ("state.json", before.manifest_path)} if before else {})
        incremental = bool(changes and previous.get("version") == VERSION
                           and previous.get("run_id") == corpus.run_id and previous.get("files") == prior_files)
        owners = []
        if incremental:
            for kind, field in (("record", "changed_record_ids"), ("entity", "changed_entity_ids"),
                                ("observation", "observation_ids"), ("page", "changed_page_ids")):
                owners.extend((kind, rid) for rid in changes[field])
            for oid in changes["observation_ids"]:
                observation = corpus.observations[oid]
                owners.extend(("artifact", observation[key]) for key in ("artifact_id", "source_artifact_id")
                              if observation.get(key))
        else:
            db.execute("DELETE FROM rows")
            db.execute("DELETE FROM relations")
            owners = [(kind, rid) for kind, group in GROUPS.items() if kind != "block"
                      for rid in getattr(corpus, group)]
        inserted = 0

        for kind, rid in sorted(set(owners)):
            owner = encoded((kind, rid))
            db.execute("DELETE FROM rows WHERE owner=?", (owner,))
            db.execute("DELETE FROM relations WHERE owner=?", (owner,))
            group = getattr(corpus, GROUPS[kind])
            if rid not in group:
                continue
            row = group[rid]
            relations = set()

            def link(name, key, value):
                relations.add((name, encoded(key), owner, encoded(value)))

            def write(row_kind, row_id, value):
                db.execute("INSERT INTO rows VALUES(?,?,?,?)", (row_kind, row_id, owner, encoded(value)))

            def searchable(row_kind, row_id, value):
                ids = [row_id] + ([value["block_id"], value["page_id"]] if row_kind == "block" else [])
                for identifier in ids:
                    identifier = identifier.casefold()
                    link("search_name", identifier[:2], ("id", identifier, "", row_kind, row_id))
                if row_kind != "block":
                    alias_kind = value.get("kind", row_kind).casefold()
                    for alias in [value.get("title", ""), *value.get("aliases", [])]:
                        if alias:
                            alias = alias.casefold()
                            link("search_name", alias[:2], ("alias", alias, alias_kind, row_kind, row_id))

            def impact(source, target, reason):
                link("impact", source, (target, reason))

            write(kind, rid, row)
            inserted += 1
            if kind in {"record", "entity", "observation"}:
                searchable(kind, rid, row)
                for subject in row.get("subject_refs", []):
                    link("subject", subject, (kind, rid))
                uncertain = row.get("classification") in {"unclassified", "uncertain", "unlinked"}
                if uncertain or (kind == "observation" and not row.get("subject_refs")):
                    link("flag", "unclassified", (kind, rid))
            if kind == "record":
                contradictions = set(ref_ids(row.get("contradicts", [])))
                corrections = {target for field in CORRECTIONS for target in ref_ids(row.get(field, []))}
                for target in dependencies(row):
                    link("dependency", rid, target)
                    if target not in contradictions:
                        impact(target, rid, "counterevidence_changed" if target in corrections else "dependency_changed")
                for field in (*CORRECTIONS, "contradicts"):
                    for target in ref_ids(row.get(field, [])):
                        link("reverse_correction", target, rid)
                for target in ref_ids(row.get("contradicts", [])):
                    link("contradiction", target, rid)
                    impact(rid, target, "counterevidence_changed")
                for target in ref_ids(_support_refs(row)):
                    link("reverse_support", target, rid)
                for target in row.get("subject_refs", []) + ref_ids(row.get("observation_refs", [])):
                    link("record_anchor", target, rid)
                for target in ref_ids(row.get("observation_refs", [])):
                    impact(target, rid, "observation_changed")
                for ref in row.get("artifact_refs", []):
                    impact(ref["artifact_id"], rid, "artifact_changed")
                for connection in row.get("links", []):
                    for target in ref_ids(connection.get("evidence_refs", [])):
                        impact(target, rid, "connection_evidence_changed")
                for subject in ref_ids(row.get("subject_refs", [])):
                    impact(subject, rid, "subject_changed")
                authored = json.dumps({key: row.get(key) for key in
                                      ("id", "summary", "title", "capability", "subject_refs")}, ensure_ascii=False)
                for term in set(_terms(authored)):
                    link("seed_term", term, rid)
                if row.get("kind") == "Goal" and row.get("status") == "active":
                    link("flag", "goals", rid)
                if row.get("kind") == "Step" and row.get("status") == "blocked":
                    link("flag", "blockers", rid)
                if row.get("capability", {}).get("needs") and row.get("status") in {"active", "blocked"}:
                    link("flag", "default_seeds", rid)
                context = hint_terms(row.get("summary", "")) | hint_terms(row.get("title", ""))
                for field in ("provides", "needs"):
                    for index, spec in enumerate(row.get("capability", {}).get(field, [])):
                        key = (rid, index)
                        link("record_" + field, rid, key)
                        for name in _names(spec):
                            link(field, key, name)
                            link("named_" + field, name, key)
                        if field == "provides":
                            for term in _spec_terms(spec) | context:
                                link("hint_term", term, key)
            if kind == "observation":
                for field in ("artifact_id", "source_artifact_id"):
                    if row.get(field):
                        impact(row[field], rid, "artifact_changed")
                for subject in ref_ids(row.get("subject_refs", [])):
                    impact(subject, rid, "subject_changed")
            if kind == "entity":
                for field in ("owner_ref", "tenant_ref", "asset_ref"):
                    if row.get(field):
                        impact(row[field], rid, "entity_context_changed")
                for field in ("source_refs", "observation_refs"):
                    for target in ref_ids(row.get(field, [])):
                        impact(target, rid, "entity_source_changed")
            if kind == "page":
                link("derived_path", str(corpus.path(row["path"])), True)
                link("derived_hash", row["content_hash"], True)
                for subject in row.get("discovery_scope", {}).get("subject_refs", []):
                    link("scoped_page", subject, rid)
                for field in ("source_refs", "record_refs", "subject_refs"):
                    for target in ref_ids(row.get(field, [])):
                        impact(target, rid, "page_source_changed")
                for block in row["blocks"]:
                    bid = rid + "/" + block["block_id"]
                    value = {**block, "page_id": rid, "text": "", "_issues": []}
                    write("block", bid, value)
                    searchable("block", bid, value)
                    for target in ref_ids(block.get("source_refs", [])):
                        link("source_block", target, bid)
                    for subject in ref_ids(block.get("subject_refs", row.get("subject_refs", []))):
                        link("subject_block", subject, bid)
                    for field in ("source_refs", "subject_refs"):
                        for target in ref_ids(block.get(field, [])):
                            impact(target, bid, "block_source_changed")
                    for ref in block.get("artifact_refs", []):
                        impact(ref["artifact_id"], bid, "artifact_changed")
                    for ref in block.get("required_block_refs", []):
                        impact(ref["page_id"] + "/" + ref["block_id"], bid, "required_block_changed")
                    impact(bid, rid, "block_changed")
            db.executemany("INSERT INTO relations VALUES(?,?,?,?)", sorted(relations))

        # Directory projections are tiny compared with authored pages. Their
        # updates include descendants when an ancestor is renamed or moved.
        for pid, titles in navigation_paths(corpus.pages).items():
            db.execute("""INSERT INTO rows VALUES('navigation',?,?,?)
                ON CONFLICT(kind,rid) DO UPDATE SET payload=excluded.payload
                WHERE payload<>excluded.payload""", (pid, encoded(("page", pid)), encoded(titles)))
        for relative in ("state.json", "manifest.json", "wiki/manifest.json", "wiki-knowledge.json"):
            db.execute("INSERT OR IGNORE INTO relations VALUES(?,?,?,?)",
                       ("derived_path", encoded(str(corpus.path(relative))), "root", "true"))
        header = {"version": VERSION, "run_id": corpus.run_id,
                  "files": {relative: list(corpus.read_files[corpus.path(relative)])
                            for relative in ("state.json", corpus.manifest_path)},
                  "state": {key: value for key, value in corpus.state.items()
                            if key not in {"records", "entities", "observations", "artifacts"}},
                  "manifest": {key: value for key, value in corpus.manifest.items() if key != "pages"}}
        if corpus.stable():
            db.execute("INSERT OR REPLACE INTO metadata VALUES('header',?)", (encoded(header),))
            db.commit()
            count(corpus.metrics, "metadata_owners_indexed", inserted)
        else:
            db.rollback()
    finally:
        db.close()
