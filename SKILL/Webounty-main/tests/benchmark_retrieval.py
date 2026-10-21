"""Synthetic local retrieval microbenchmark; no models, services or target traffic.

Run: python tests/benchmark_retrieval.py --sizes 100 300 --repeats 3
Reports Python retrieval wall time and serialized Unicode characters, NOT Claude
tokens or end-to-end agent latency. Cold means a missing derived index, not a
flushed operating-system file cache. Publication and query times are separate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from statistics import median
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from rag import encode, retrieve
import retrieval_index
from store import publish


RUN_ID = "BENCH-RUN"
QUERY = "exportpermissionneedle"
PRODUCER, CONSUMER, COUNTER = "R-0000", "R-0001", "R-0002"
EXPECTED_RECORDS = {PRODUCER, CONSUMER, COUNTER}
EXPECTED_OBSERVATIONS = {"O-0000", "O-0001", "O-0002"}


def page(number):
    parent = ("BRANCH-PRODUCER", "BRANCH-CONSUMER")[number == 1] if number < 2 else "BRANCH-OTHER"
    return {"id": f"P-{number:04d}", "title": "验证结果", "parent_page_id": parent,
            "record_refs": [f"R-{number:04d}"],
            "questions": ["What does exportpermissionneedle require?"] if number == 1 else []}


def make_corpus(root, size, body_chars):
    """Publish real Wiki files from a small, intentionally mostly unrelated corpus."""
    (root / "wiki").mkdir()
    (root / "evidence").mkdir()
    state = {"run_id": RUN_ID, "session_id": "BENCH-SESSION", "revision": 1,
             "records": {}, "entities": {}, "observations": {}, "artifacts": {}}
    (root / "state.json").write_text(encode(state), encoding="utf-8")
    (root / "wiki/manifest.json").write_text(encode({"run_id": RUN_ID, "pages": []}), encoding="utf-8")
    batch = {"entities": [], "observations": [], "records": [], "pages": [
        {"id": "BRANCH-PRODUCER", "title": "早期任务产物", "blocks": []},
        {"id": "BRANCH-CONSUMER", "title": "报表下载授权", "blocks": []},
        {"id": "BRANCH-OTHER", "title": "其他独立调查", "blocks": []},
    ]}
    segment = "synthetic local response segment "
    padding = (segment * (body_chars // len(segment) + 1))[:body_chars]
    for number in range(size):
        rid, oid, eid = f"R-{number:04d}", f"O-{number:04d}", f"E-{number:04d}"
        batch["entities"].append({"id": eid, "kind": "endpoint", "summary": f"Independent endpoint {number}"})
        batch["observations"].append({"id": oid, "subject_refs": [eid],
            "summary": f"Observation {number}", "content": {
                "request": {"method": "GET", "url": f"/synthetic/item/{number}"},
                "response": {"status": 200, "body": padding}}})
        row = {"id": rid, "kind": "Fact", "status": "observed",
               "summary": f"Unrelated local observation {number}", "subject_refs": [eid],
               "observation_refs": [oid]}
        if number < 2:
            row.update(kind="Capability", summary=("早期观察的任务引用", QUERY + " 下载前提")[number])
            spec = {"type": "report-reference", "constraints": {"tenant": "synthetic-demo", "purpose": "export"}}
            row["capability"] = {"provides": [spec] if number == 0 else [],
                                 "needs": [spec] if number == 1 else []}
        elif number == 2:
            row.update(summary="Independent counterevidence limits the earlier claim", contradicts=[PRODUCER])
        batch["records"].append(row)
        batch["pages"].append(page(number))
    started = perf_counter()
    publish(root, RUN_ID, batch)
    return perf_counter() - started


def measured(root, **options):
    stats, metrics = {}, {}
    original = retrieval_index.lexical_projection

    def traced(corpus, *args, **kwargs):
        result = original(corpus, *args, **kwargs)
        stats.update(corpus.retrieval_index_stats)
        return result

    with patch.object(retrieval_index, "lexical_projection", traced):
        started = perf_counter()
        result = retrieve(root, RUN_ID, QUERY, [CONSUMER], metrics=metrics, **options)
        seconds = perf_counter() - started
    return result, {"seconds": seconds, "characters": len(encode(result)), "index": stats, "metrics": metrics}


def check_context(result):
    """Check recall/source identity, without treating candidate links as proof."""
    assert EXPECTED_RECORDS <= {row["id"] for row in result["records"]}, "record or counterevidence lost"
    assert EXPECTED_OBSERVATIONS <= {row["id"] for row in result["observations"]}, "observation reference lost"
    candidates = result["chain_discovery"]["candidates"]
    assert any(row["producer_ref"] == PRODUCER and row["consumer_ref"] == CONSUMER
               for row in candidates), "cross-branch capability relation lost"
    assert all(row["evidence"] is False for row in candidates), "candidate upgraded to evidence"
    assert result["budget"]["limit_chars"] is None, "benchmark must not impose an output cap"
    assert result["budget"]["omitted_units"] == 0, "benchmark must not drop retrieval units"
    for row in result["observations"]:
        if row["id"] in EXPECTED_OBSERVATIONS:
            assert row["status"] == "ready", "source became unavailable"
            assert row["index"]["artifact_id"] == "ART-" + row["id"], "original observation locator lost"
            if result.get("view") == "compact":
                assert row["read_ref"] == row["id"] and row["raw_expanded"] is False


def series(root, repeats, **options):
    results = [measured(root, **options) for _ in range(repeats)]
    for result, _ in results:
        check_context(result)
    return {"median_seconds": median(row["seconds"] for _, row in results),
            "runs": [row for _, row in results]}


def benchmark(size, repeats, body_chars):
    with tempfile.TemporaryDirectory(prefix="webounty-retrieval-bench-") as directory:
        root = Path(directory)
        publication_seconds = make_corpus(root, size, body_chars)
        # Publication builds the index now; explicitly remove it for a cold query.
        shutil.rmtree(root / "cache")
        evidence, cold_evidence = measured(root, view="evidence")
        check_context(evidence)
        warm_evidence = series(root, repeats, view="evidence")
        shutil.rmtree(root / "cache")
        compact, cold_compact = measured(root, view="compact")
        check_context(compact)
        warm_compact = series(root, repeats, view="compact")
        first, first_cursor = measured(root, view="compact", cursor="bench")
        check_context(first)
        unchanged, second_cursor = measured(root, view="compact", cursor="bench")
        assert second_cursor["characters"] < first_cursor["characters"], "unchanged cursor did not reduce output"
        assert EXPECTED_RECORDS <= {row["id"] for row in unchanged["unchanged_refs"]
                                   if row["kind"] == "record"}, "unchanged record identities lost"

        started = perf_counter()
        publish(root, RUN_ID, {"records": [{"id": CONSUMER, "summary": QUERY + " 下载前提已复核"}],
                               "pages": [page(1)]})
        record_publish_seconds = perf_counter() - started
        record_delta, record_query = measured(root, view="compact", cursor="bench")
        assert any(row["id"] == CONSUMER and row["revision"] == 2 for row in record_delta["records"]), \
            "record revision was not delivered after update"

        started = perf_counter()
        publish(root, RUN_ID, {"pages": [{"id": "BRANCH-CONSUMER", "title": "报表下载权限复核"}]})
        parent_publish_seconds = perf_counter() - started
        parent_delta, parent_query = measured(root, view="compact", cursor="bench")
        assert parent_delta["delta"]["metadata_changes"], "parent rename was not delivered as metadata change"
        refreshed, refresh_query = measured(root, view="compact", cursor="bench", refresh=True)
        check_context(refreshed)
        assert "报表下载权限复核" in encode(refreshed), "renamed parent missing from retrieval view"
        return {
            "record_count": size, "observation_count": size, "wiki_page_count": size + 3,
            "response_body_characters_each": body_chars,
            "query_recalled_records": len(compact["records"]),
            "query_recalled_observations": len(compact["observations"]),
            "initial_publication_seconds": publication_seconds,
            "cold_evidence": cold_evidence, "warm_evidence": warm_evidence,
            "cold_compact": cold_compact, "warm_compact": warm_compact,
            "cursor_first": first_cursor, "cursor_second_unchanged": second_cursor,
            "record_change": {"publication_seconds": record_publish_seconds, "query": record_query},
            "parent_title_change": {"publication_seconds": parent_publish_seconds, "query": parent_query},
            "refresh_after_context_compaction": refresh_query,
            "checks": {"cross_branch_candidate": True, "counterevidence": True,
                       "observation_locators": True, "updated_record_delivered": True,
                       "parent_title_visible": True, "refresh_restores_context": True},
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 300])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--body-chars", type=int, default=4096)
    args = parser.parse_args()
    if args.repeats < 1 or any(size < 3 for size in args.sizes) or args.body_chars < 1:
        parser.error("positive repeats/body-chars and at least three records per size are required")
    result = {
        "scenario": "One consumer query in a mostly unrelated session; producer and counterevidence in other Wiki branches.",
        "measurement": "Synthetic Python/local-filesystem microbenchmark; no model or network calls. Characters are Unicode JSON characters, not tokens.",
        "cold_definition": "Derived lexical and metadata caches absent; operating-system file cache is not flushed.",
        "query_timing": "time.perf_counter includes retrieval, source validation, view construction and cursor persistence; excludes final JSON serialization.",
        "limitations": "Same-process warm runs and repetitive synthetic response bodies; no claim about Claude end-to-end latency, real token savings or arbitrary corpora.",
        "measurements": [benchmark(size, args.repeats, args.body_chars) for size in args.sizes],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
