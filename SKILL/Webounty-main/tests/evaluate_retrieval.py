#!/usr/bin/env python3
"""Measure lexical retrieval over a fixed, synthetic, two-round session corpus.

Example:
  python3 -B tests/evaluate_retrieval.py --scripts-dir /path/to/scripts \
      --output /tmp/retrieval-result.json --label baseline --repeats 5

No network, target requests, score tuning, or pass/fail quality threshold is used.
The fixture is published through the selected version's session/store interfaces.
All benchmark session files are temporary. Only --output is retained when given.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

sys.dont_write_bytecode = True


def item(key):
    return {"kind": key[0], "id": key[1]}


def percentile(values, fraction):
    """Nearest-rank percentile; meaningful here as a descriptive small-sample value."""
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def latency_summary(values):
    return {
        "samples": len(values),
        "median_ms": round(statistics.median(values), 4),
        "p95_ms": round(percentile(values, 0.95), 4),
        "min_ms": round(min(values), 4),
        "max_ms": round(max(values), 4),
    }


def load_fixture(path):
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if fixture.get("schema_version") != 1:
        raise ValueError("unsupported fixture schema")
    seen = set()
    for case in fixture["queries"]:
        if case["id"] in seen or not case["query"].strip():
            raise ValueError("query IDs must be unique and query text must be nonempty")
        seen.add(case["id"])
        relevant = case["primary_relevant"]
        if bool(relevant) == bool(case.get("expect_no_hit")):
            raise ValueError("each query needs primary relevance labels or expect_no_hit")
        keys = [(row["kind"], row["id"]) for row in relevant]
        if len(keys) != len(set(keys)) or any(kind not in {"record", "observation"} for kind, _ in keys):
            raise ValueError("primary labels must be unique record/observation IDs")
    return fixture


def version_info(scripts_dir):
    files = {}
    combined = hashlib.sha256()
    for path in sorted(scripts_dir.glob("*.py")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files[path.name] = digest
        combined.update((path.name + "\0" + digest + "\n").encode("utf-8"))
    return {"scripts_dir": str(scripts_dir), "python_file_sha256": files,
            "combined_sha256": combined.hexdigest()}


def evaluate(args):
    fixture_path = args.cases.resolve(strict=True)
    scripts_dir = args.scripts_dir.resolve(strict=True)
    fixture = load_fixture(fixture_path)
    before = version_info(scripts_dir)
    sys.path.insert(0, str(scripts_dir))
    modules = {name: importlib.import_module(name) for name in ("session", "store", "rag", "search_index")}
    if any(Path(module.__file__).resolve().parent != scripts_dir for module in modules.values()):
        raise ValueError("loaded modules did not all come from --scripts-dir; run in a fresh process")
    session, store, rag, search = (modules[name] for name in ("session", "store", "rag", "search_index"))
    results, all_latencies = [], []
    with tempfile.TemporaryDirectory(prefix="webounty-retrieval-eval-") as folder:
        with patch.object(session, "base_directory", return_value=Path(folder) / "sessions"):
            opened = session.start("offline-retrieval-evaluation", fixture["goal"])
            try:
                for batch in fixture["batches"]:
                    store.publish(opened["root"], opened["run_id"], batch)
                inventory = rag.Corpus(opened["root"], opened["run_id"])
                counts = {name: len(getattr(inventory, name)) for name in
                          ("records", "observations", "entities", "blocks", "pages")}
                counts["rank_documents"] = sum(counts[name] for name in
                                                ("records", "observations", "entities", "blocks"))
                groups = {"record": inventory.records, "observation": inventory.observations}
                for case in fixture["queries"]:
                    for relevant in case["primary_relevant"]:
                        if relevant["id"] not in groups[relevant["kind"]]:
                            raise ValueError(f"unknown relevance label in {case['id']}: {relevant}")
                    first_result = None
                    timings = []
                    for _ in range(args.repeats):
                        # Each sample uses a fresh Corpus. Its construction and
                        # publication are outside timing; rank's evidence reads
                        # and index construction remain inside timing.
                        corpus = rag.Corpus(opened["root"], opened["run_id"])
                        started = time.perf_counter_ns()
                        ranked, issues = search.rank(corpus, case["query"], case.get("anchors", []))
                        timings.append((time.perf_counter_ns() - started) / 1_000_000)
                        result = (ranked, issues)
                        if first_result is None:
                            first_result = result
                        elif first_result != result:
                            raise ValueError(f"non-deterministic rank result for {case['id']}")
                    ranked, issues = first_result
                    positions = {key: index for index, key in enumerate(ranked, 1)}
                    relevant_keys = [(row["kind"], row["id"]) for row in case["primary_relevant"]]
                    found_ranks = [positions[key] for key in relevant_keys if key in positions]
                    answerable = bool(relevant_keys)
                    first_rank = min(found_ranks) if found_ranks else None
                    results.append({
                        "id": case["id"], "category": case["category"],
                        "query": case["query"], "anchors": case.get("anchors", []),
                        "primary_relevant": case["primary_relevant"],
                        "primary_ranks": [{**item(key), "rank": positions.get(key)} for key in relevant_keys],
                        "first_relevant_rank": first_rank,
                        "reciprocal_rank": (1 / first_rank if first_rank else 0.0) if answerable else None,
                        "recall_at_5": (sum(rank <= 5 for rank in found_ranks) / len(relevant_keys)) if answerable else None,
                        "expect_no_hit": case.get("expect_no_hit", False),
                        "no_hit_correct": not ranked if not answerable else None,
                        "ranked_count": len(ranked), "top_10": [item(key) for key in ranked[:10]],
                        "issues": issues, "rank_latency": latency_summary(timings),
                        "rank_latency_samples_ms": [round(value, 4) for value in timings],
                    })
                    all_latencies.extend(timings)
            finally:
                session.finish(opened["root"], opened["run_id"], opened["session_id"])
    if version_info(scripts_dir) != before:
        raise ValueError("selected scripts changed during evaluation; rerun against an immutable snapshot")
    answerable = [row for row in results if row["reciprocal_rank"] is not None]
    no_hit = [row for row in results if row["expect_no_hit"]]
    return {
        "schema_version": 1, "label": args.label,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "version": before,
        "fixture": {"path": str(fixture_path), "sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
                    "description": fixture["description"], "batches": len(fixture["batches"])},
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "measurement": {"repeats_per_query": args.repeats, "rank_scope": fixture["scoring"]["rank_space"],
                        "timing": "Fresh Corpus per repetition; Corpus construction excluded; complete rank call included. No explicit warm-up; a session-local term index is reused when supported by the selected version.",
                        "scoring": fixture["scoring"],
                        "limitations": "Small hand-labelled synthetic benchmark; latency is local and not a production throughput estimate."},
        "corpus_counts": counts,
        "summary": {"queries": len(results), "answerable_queries": len(answerable), "no_hit_queries": len(no_hit),
                    "mrr": statistics.mean(row["reciprocal_rank"] for row in answerable) if answerable else None,
                    "recall_at_5": statistics.mean(row["recall_at_5"] for row in answerable) if answerable else None,
                    "no_hit_accuracy": statistics.mean(row["no_hit_correct"] for row in no_hit) if no_hit else None,
                    "rank_latency": latency_summary(all_latencies)},
        "queries": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scripts-dir", type=Path, default=Path(__file__).resolve().parents[1] / "scripts")
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("retrieval_cases.json"))
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--label", default="measurement")
    parser.add_argument("--output", type=Path, help="Optional JSON output; stdout contains the same complete JSON")
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    result = evaluate(args)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
