#!/usr/bin/env python3
"""Replay six labelled local conversation turns, without a model or target traffic.

python -B tests/replay_session.py --output /tmp/session-replay.json
python -B tests/replay_session.py --scripts-dir /path/to/baseline/scripts --label before

The same fixture is published and queried in order in one temporary session.
`unchanged_refs` count only if their earlier bodies remain in the replay's host
cache; refresh clears that cache. This simulates retained context, not Claude's
understanding. No ranking cutoff, token cap or automatic pass threshold is used.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import platform
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch

sys.dont_write_bytecode = True
DEFAULT_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
DEFAULT_CASES = Path(__file__).with_name("session_replay_cases.json")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def identity(group, row):
    if group == "chain_discovery.candidates":
        return encoded([row["producer_ref"], row["provide_index"], row["consumer_ref"], row["need_index"]])
    if group == "chain_discovery.paths":
        return encoded(row["record_refs"])
    return row["id"]


class DeliveredContext:
    """Only bodies actually delivered by query responses, never state.json."""
    def __init__(self):
        self.rows = {}

    def accept(self, result, refresh=False):
        if refresh:
            self.rows.clear()
        groups = {"record": result.get("records", []), "observation": result.get("observations", [])}
        groups.update({"chain_discovery." + name: result.get("chain_discovery", {}).get(name, [])
                       for name in ("candidates", "paths", "combinations", "type_reviews")})
        current = {group: {} for group in groups}
        for ref in result.get("delta", {}).get("retired_refs", []):
            self.rows.pop((ref["kind"], ref["id"]), None)
        for group, rows in groups.items():
            for row in rows:
                key = identity(group, row)
                self.rows[(group, key)] = row
                current[group][key] = row
        missing_bodies = []
        for ref in result.get("unchanged_refs", []):
            group, key = ref["kind"], ref["id"]
            if group not in current:
                continue
            if (group, key) in self.rows:
                current[group][key] = self.rows[(group, key)]
            else:
                missing_bodies.append(ref)
        return current, missing_bodies


@contextmanager
def file_reads(root):
    """Count Python Path reads, not operating-system disk/cache operations."""
    counts = {}
    root = Path(root)

    def classify(path):
        try:
            relative = Path(path).absolute().relative_to(root.absolute())
        except ValueError:
            return None
        if relative.parts[:2] == ("wiki", "pages"):
            return "wiki_pages"
        if relative == Path("wiki/manifest.json"):
            return "wiki_manifest"
        if relative == Path("state.json"):
            return "state"
        if relative.parts[:1] == ("evidence",):
            return "evidence"
        return None

    original_open = Path.open

    class TrackedReader:
        def __init__(self, stream, group):
            self.stream = stream
            self.counts = counts.setdefault(group, {"opens": 0, "calls": 0, "bytes": 0})
            self.counts["opens"] += 1

        def record(self, value):
            self.counts["calls"] += 1
            self.counts["bytes"] += len(value if isinstance(value, bytes) else value.encode("utf-8"))
            return value

        def read(self, *args, **kwargs):
            return self.record(self.stream.read(*args, **kwargs))

        def readline(self, *args, **kwargs):
            return self.record(self.stream.readline(*args, **kwargs))

        def readlines(self, *args, **kwargs):
            lines = self.stream.readlines(*args, **kwargs)
            self.counts["calls"] += 1
            self.counts["bytes"] += sum(len(line if isinstance(line, bytes) else line.encode("utf-8")) for line in lines)
            return lines

        def __iter__(self):
            return self

        def __next__(self):
            return self.record(next(self.stream))

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.stream, name)

    def opened(path, mode="r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        group = classify(path)
        if group and "r" in mode and not any(flag in mode for flag in "+wax"):
            return TrackedReader(stream, group)
        return stream

    # Path.read_bytes/read_text themselves use Path.open. Instrument only the
    # returned stream so those helpers, Corpus.open/read and stable re-reads
    # all count once at the same layer.
    with patch.object(Path, "open", opened):
        yield counts


def measured_call(root, function, *args, **kwargs):
    """Metrics compatibility is confined to this offline comparison harness."""
    metrics = {} if "metrics" in inspect.signature(function).parameters else None
    if metrics is not None:
        kwargs["metrics"] = metrics
    with file_reads(root) as reads:
        started = perf_counter()
        result = function(*args, **kwargs)
        elapsed = perf_counter() - started
    started = perf_counter()
    text = encoded(result)
    serialization_seconds = perf_counter() - started
    return result, {"wall_seconds": elapsed, "phase_metrics": metrics,
                    "file_reads": reads, "serialization_seconds": serialization_seconds,
                    "output_characters": len(text)}


def coverage(expected, actual):
    wanted = set(expected)
    return {"required": sorted(wanted), "found": sorted(wanted & actual),
            "missing": sorted(wanted - actual),
            "coverage": len(wanted & actual) / len(wanted) if wanted else None}


def score_turn(turn, result, current, missing_bodies):
    labels = turn["labels"]
    checks = {"retained_bodies_available": not missing_bodies,
              "no_output_cap": result["budget"]["limit_chars"] is None,
              "no_units_omitted": result["budget"]["omitted_units"] == 0}
    relevance, extra = {}, {}
    for kind, plural in (("record", "records"), ("observation", "observations")):
        actual = set(current[kind])
        relevance[plural] = coverage(labels["required_" + plural], actual)
        checks["required_" + plural] = not relevance[plural]["missing"]
        outside = actual - set(labels["allowed_" + plural])
        delivered = {row["id"]: row for row in result[plural]}
        extra[plural] = {"current_count": len(actual), "extra_ids": sorted(outside),
                         "extra_fraction": len(outside) / len(actual) if actual else 0.0,
                         "delivered_extra_characters": sum(len(encoded(delivered[key]))
                            for key in outside & delivered.keys())}
    counter = {plural: coverage(labels.get("counterevidence_" + plural, []), set(current[kind]))
               for kind, plural in (("record", "records"), ("observation", "observations"))}
    for plural, row in counter.items():
        checks["counterevidence_" + plural] = not row["missing"]
    candidates = list(current["chain_discovery.candidates"].values())
    paths = list(current["chain_discovery.paths"].values())
    combinations = list(current["chain_discovery.combinations"].values())
    type_reviews = list(current["chain_discovery.type_reviews"].values())
    checks["candidates_remain_unproven"] = all(row.get("evidence") is False for row in candidates)
    checks["paths_remain_unproven"] = all(row.get("evidence") is False and row.get("status") == "candidate" for row in paths)
    checks["combinations_remain_unproven"] = all(row.get("evidence") is False and row.get("status") == "candidate"
                                                for row in combinations)
    checks["type_reviews_remain_unproven"] = all(row.get("evidence") is False
                                                and row.get("assessment") == "review_required" for row in type_reviews)
    for expected in labels["expected_candidates"]:
        key = expected["producer"] + " -> " + expected["consumer"]
        matches = [row for row in candidates if row["producer_ref"] == expected["producer"]
                   and row["consumer_ref"] == expected["consumer"]]
        checks["candidate " + key] = any(
            row["compatibility"] == expected["compatibility"]
            and ("producer_usable" not in expected or row["producer_usable"] == expected["producer_usable"])
            and set(expected.get("conflict_constraints", [])) <= {item["constraint"] for item in row["conflicts"]}
            for row in matches)
    for expected in labels.get("missing_on_candidate", []):
        wanted = {(row["record_ref"], row["type"]) for row in expected["required"]}
        checks["missing inputs " + expected["producer"] + " -> " + expected["consumer"]] = any(
            row["producer_ref"] == expected["producer"] and row["consumer_ref"] == expected["consumer"]
            and wanted <= {(item["record_ref"], item["type"]) for item in row["missing_preconditions"]}
            for row in candidates)
    for expected in labels.get("expected_paths", []):
        checks["path " + " -> ".join(expected["record_refs"])] = any(
            row["record_refs"] == expected["record_refs"] and row["missing_preconditions"] == expected["missing_preconditions"]
            for row in paths)
    forbidden = set(labels.get("forbidden_path_members", []))
    checks["unusable_providers_excluded_from_paths"] = not any(forbidden.intersection(row["record_refs"]) for row in paths)
    for rid, status in labels.get("record_statuses", {}).items():
        checks["record status " + rid] = current["record"].get(rid, {}).get("status") == status
    unchanged = {row["id"] for row in result.get("unchanged_refs", []) if row["kind"] == "record"}
    delivered = {row["id"] for row in result["records"]}
    checks["expected_unchanged_records"] = set(labels.get("must_be_unchanged_records", [])) <= unchanged
    checks["expected_delivered_records"] = set(labels.get("must_be_delivered_records", [])) <= delivered
    if labels.get("expect_no_unchanged"):
        checks["refresh_restores_bodies"] = not result.get("unchanged_refs")
    if labels.get("expected_navigation_title"):
        checks["renamed_navigation_visible"] = labels["expected_navigation_title"] in encoded(result)
    return {"passed": all(checks.values()), "checks": checks,
            "required_reference_coverage": relevance, "counterevidence_coverage": counter,
            "label_defined_extra_returns": extra, "missing_retained_bodies": missing_bodies,
            "delivered_record_ids": sorted(delivered), "unchanged_record_ids": sorted(unchanged),
            "current_record_revisions": {rid: row["revision"] for rid, row in current["record"].items()},
            "delta_changes": result.get("delta", {}).get("changes", []),
            "change_impact": result.get("change_impact"),
            "candidates": candidates, "paths": paths, "combinations": combinations, "type_reviews": type_reviews}


def replay(scripts_dir=DEFAULT_SCRIPTS, cases_path=DEFAULT_CASES, label="current"):
    scripts_dir, cases_path = Path(scripts_dir).resolve(strict=True), Path(cases_path).resolve(strict=True)
    fixture = json.loads(cases_path.read_text(encoding="utf-8"))
    if fixture["schema_version"] != 1:
        raise ValueError("unsupported replay fixture")
    sys.path.insert(0, str(scripts_dir))
    modules = {name: importlib.import_module(name) for name in ("session", "store", "rag", "retrieval_index")}
    if any(Path(module.__file__).resolve().parent != scripts_dir for module in modules.values()):
        raise ValueError("--scripts-dir comparison must run in a fresh Python process")
    session, store, rag, index = (modules[name] for name in ("session", "store", "rag", "retrieval_index"))
    host = DeliveredContext()
    turns = []
    with tempfile.TemporaryDirectory(prefix="webounty-session-replay-") as directory:
        with patch.object(session, "base_directory", return_value=Path(directory) / "sessions"):
            opened = session.start("offline-six-turn-replay", fixture["goal"])
            root, run_id = opened["root"], opened["run_id"]
            try:
                for turn in fixture["turns"]:
                    publication = None
                    if turn.get("batch"):
                        _, publication = measured_call(root, store.publish, root, run_id, turn["batch"])
                    stats = {}
                    original = index.lexical_projection

                    def traced(corpus, *args, **kwargs):
                        output = original(corpus, *args, **kwargs)
                        stats.update(corpus.retrieval_index_stats)
                        return output

                    with patch.object(index, "lexical_projection", traced):
                        result, query = measured_call(root, rag.retrieve, root, run_id, turn["query"],
                            turn.get("anchors", []), view="compact", cursor="replay-host",
                            refresh=turn.get("refresh", False))
                    query["index"] = stats
                    current, missing = host.accept(result, refresh=turn.get("refresh", False))
                    scored = score_turn(turn, result, current, missing)
                    reads = []
                    for action in turn.get("reads", []):
                        def read():
                            return session.read_ids(rag.Corpus(root, run_id, lazy_pages=True), action["ids"])
                        output, measurement = measured_call(root, read)
                        observations = {row["id"]: row for row in output["package"]["observations"]}
                        checks = {oid: observations.get(oid, {}).get("raw", {}).get("response", {}).get("status") == status
                                  for oid, status in action.get("observation_statuses", {}).items()}
                        reads.append({"ids": action["ids"], "measurement": measurement, "checks": checks,
                                      "passed": output["status"] != "unavailable" and all(checks.values())})
                    scored["passed"] = scored["passed"] and all(row["passed"] for row in reads)
                    turns.append({"id": turn["id"], "query": turn["query"], "anchors": turn.get("anchors", []),
                                  "refresh": turn.get("refresh", False), "state_revision": result["state_revision"],
                                  "publication": publication, "retrieval": query, "reads": reads, **scored})
            finally:
                session.finish(root, run_id, opened["session_id"])
    required_count = sum(len(turn["required_reference_coverage"][kind]["required"])
                         for turn in turns for kind in ("records", "observations"))
    found_count = sum(len(turn["required_reference_coverage"][kind]["found"])
                      for turn in turns for kind in ("records", "observations"))
    counter_count = sum(len(turn["counterevidence_coverage"][kind]["required"])
                        for turn in turns for kind in ("records", "observations"))
    counter_found = sum(len(turn["counterevidence_coverage"][kind]["found"])
                        for turn in turns for kind in ("records", "observations"))
    current_count = sum(turn["label_defined_extra_returns"][kind]["current_count"]
                        for turn in turns for kind in ("records", "observations"))
    extra_count = sum(len(turn["label_defined_extra_returns"][kind]["extra_ids"])
                      for turn in turns for kind in ("records", "observations"))
    return {"schema_version": 1, "label": label, "scenario": fixture["description"],
            "scripts_dir": str(scripts_dir), "fixture_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
            "runtime": {"python": platform.python_version(), "platform": platform.platform()},
            "measurement": {"scoring": fixture["scoring"],
                "timing": "One in-process replay. Publication measures store.publish only, excluding session record discovery/logging; query measures rag.retrieve. JSON serialization is timed separately. Phase timings may be nested and must not be summed.",
                "file_reads": "Counts read-only Path.open streams and their read/readline/readlines/iteration operations under the temporary session, including Corpus validation and stable re-reads. Path.read_bytes/read_text use the same layer and are not double-counted. Byte counts use UTF-8 for text. These are Python reads, not physical disk I/O or OS page-cache misses.",
                "index": "The selected implementation's existing retrieval_index_stats; no invented index-hit estimate.",
                "limitations": "Small hand-labelled synthetic conversation, not production latency, Claude decision success, real repeat-experiment reduction or measured token savings."},
            "summary": {"turns": len(turns), "passed": all(row["passed"] for row in turns),
                "failed_turns": [row["id"] for row in turns if not row["passed"]],
                "required_reference_coverage": found_count / required_count if required_count else None,
                "counterevidence_reference_coverage": counter_found / counter_count if counter_count else None,
                "label_defined_extra_reference_fraction": extra_count / current_count if current_count else 0.0,
                "query_wall_seconds": sum(row["retrieval"]["wall_seconds"] for row in turns),
                "publication_wall_seconds": sum(row["publication"]["wall_seconds"] for row in turns if row["publication"]),
                "query_output_characters": sum(row["retrieval"]["output_characters"] for row in turns),
                "explicit_read_calls": sum(len(row["reads"]) for row in turns),
                "read_output_characters": sum(read["measurement"]["output_characters"] for row in turns for read in row["reads"]),
                "host_tokens": None, "model_calls": 0}, "turns": turns}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scripts-dir", type=Path, default=DEFAULT_SCRIPTS)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--label", default="current")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = replay(args.scripts_dir, args.cases, args.label)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
