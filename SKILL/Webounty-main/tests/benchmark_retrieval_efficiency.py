"""Repeatable sparse-query benchmark; synthetic index data is never evidence.

Run with --scripts-dir to compare implementations. Fixture creation is excluded
from timings. This isolates warm SQLite lookup cost, not end-to-end retrieval.
The fixture has no evidence files; source file checks and hashing are excluded.
"""

from contextlib import closing
import json
from pathlib import Path
from statistics import median
import sys
import tempfile
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch


def fixture(directory, documents, terms_per_document=12):
    import retrieval_index as index

    root = Path(directory)
    (root / "state.json").write_text("{}", encoding="utf-8")
    (root / "manifest.json").write_text("{}", encoding="utf-8")
    data = SimpleNamespace(root=root, run_id="synthetic-efficiency", state={"revision": 1},
                           manifest_path="manifest.json", navigation_paths={},
                           path=lambda name: root / name, stable=lambda: True)
    rows = {("observation", "O-HIT" if n == 1 else f"O-{n}"): {} for n in range(1, documents + 1)}
    with closing(index._open(data)) as db:
        db.executemany("INSERT INTO documents VALUES(?, 'observation', ?, 'fixture', NULL, 1)",
                       ((n, "O-HIT" if n == 1 else f"O-{n}") for n in range(1, documents + 1)))
        db.executemany("INSERT INTO fields VALUES(?, 'body', ?)",
                       ((n, terms_per_document) for n in range(1, documents + 1)))
        db.execute("INSERT INTO field_totals VALUES('body', ?, ?)",
                   (documents * terms_per_document, documents))
        db.executemany("INSERT INTO terms VALUES(?, ?, 'body', 1)",
                       ((f"noise-{n}-{m}", n) for n in range(1, documents + 1)
                        for m in range(terms_per_document)))
        db.execute("INSERT INTO terms VALUES('alpha', 1, 'body', 1)")
        db.executemany("INSERT INTO dependencies VALUES(?, ?)",
                       (("id:O-HIT" if n == 1 else f"id:O-{n}", n)
                        for n in range(1, documents + 1)))
        db.executemany("INSERT INTO source_chunks VALUES(?, 0, ?, 0, 100, ?)",
                       ((n, f"A-{n}", "0" * 64) for n in range(1, documents + 1)))
        db.executemany("INSERT INTO source_terms VALUES(?, ?, 0)",
                       ((f"noise-{n}-{m}", n) for n in range(1, documents + 1)
                        for m in range(terms_per_document)))
        db.execute("INSERT INTO source_chunks VALUES(1, 1, 'A-1', 100, 100, ?)", ("1" * 64,))
        db.executemany("INSERT INTO source_terms VALUES(?, 1, ?)",
                       (("beta", 0), ("alpha", 1), ("beta", 1)))
        db.executemany("INSERT INTO metadata VALUES(?, ?)", index.snapshot(data).items())
        db.commit()
    return data, rows


def projection(data, rows, terms=("alpha", "beta")):
    import retrieval_index as index

    def no_rebuild(*args):
        raise AssertionError("warm lookup rebuilt the index")

    return index.lexical_projection(data, rows, terms, no_rebuild, no_rebuild, no_rebuild,
                                    original_terms={"alpha"})


def projection_steps(data, rows, terms=("alpha", "beta")):
    import retrieval_index as index

    steps, opener = [0], index._open

    def progress():
        steps[0] += 1

    def tracked(corpus):
        db = opener(corpus)
        db.set_progress_handler(progress, 1)
        return db

    with patch.object(index, "_open", tracked):
        result = projection(data, rows, terms)
    return steps[0], result


def dependency_steps(data, rows):
    import retrieval_index as index

    steps = [0]

    def progress():
        steps[0] += 1

    with closing(index._open(data)) as db:
        db.set_progress_handler(progress, 1)
        result = index._changed_keys(db, rows, {"id:O-HIT"}, ())
    return steps[0], result


def benchmark(data, rows, repeats):
    steps, result = projection_steps(data, rows)
    durations = []
    for _ in range(repeats):
        begin = perf_counter()
        assert projection(data, rows) == result
        durations.append((perf_counter() - begin) * 1000)
    dependency_work, changed = dependency_steps(data, rows)
    assert changed == {("observation", "O-HIT")}
    return {"documents": len(rows), "median_ms": round(median(durations), 3),
            "min_ms": round(min(durations), 3), "query_vm_steps": steps,
            "dependency_vm_steps": dependency_work,
            "matched_documents": len(result[0]["alpha"]),
            "selected_source_offset": data.retrieval_source_matches["O-HIT"]["offset"],
            "matching_source_chunks": data.retrieval_source_matches["O-HIT"]["matching_chunks"],
            "indexed_documents": data.retrieval_index_stats["indexed_documents"],
            "file_checks": data.retrieval_index_stats["file_checks"]}


if __name__ == "__main__":
    import argparse
    import sqlite3

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scripts-dir", type=Path, default=Path(__file__).resolve().parents[1] / "scripts")
    parser.add_argument("--documents", type=int, nargs="+", default=[100, 10000])
    parser.add_argument("--repeats", type=int, default=9)
    args = parser.parse_args()
    if args.repeats < 1 or any(size < 1 for size in args.documents):
        parser.error("documents and repeats must be positive")
    sys.path.insert(0, str(args.scripts_dir.resolve()))
    results = []
    for size in args.documents:
        with tempfile.TemporaryDirectory() as directory:
            results.append(benchmark(*fixture(directory, size), args.repeats))
    print(json.dumps({"sqlite_version": sqlite3.sqlite_version, "repeats": args.repeats,
                      "terms_per_document": 12, "results": results}, indent=2))
