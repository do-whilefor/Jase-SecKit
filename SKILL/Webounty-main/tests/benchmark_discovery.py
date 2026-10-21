"""Reproducible in-memory discovery benchmark; no services or target traffic.

Run: python tests/benchmark_discovery.py --sizes 1000 3000 > result.json
Use --module to compare another discovery.py against the identical corpus.
"""

import argparse
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter

sys.dont_write_bytecode = True


def corpus(size):
    class Corpus:
        def __init__(self):
            self.records, self.observations, self.pages, self.blocks = {}, {}, {}, {}
            self.observation_reads = 0

        def observation(self, oid):
            self.observation_reads += 1
            return {"status": "ready"}

    result = Corpus()
    for offset in range(size):
        index, side = divmod(offset, 2)
        tenant = f"tenant-{index // 5}"
        prefix, field = (("producer", "provides"), ("consumer", "needs"))[side]
        rid = f"{prefix}-{index:04d}"
        oid = "obs-" + rid
        result.records[rid] = {
            "id": rid, "kind": "Capability", "revision": 1,
            "status": "verified", "summary": rid,
            "capability": {field: [{"type": "export-task-id", "aliases": ["任务标识"],
                                    "constraints": {"tenant": tenant, "purpose": "export"}}]},
            "observation_refs": [oid],
        }
        result.observations[oid] = {"id": oid, "revision": 1}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path,
                        default=Path(__file__).resolve().parents[1] / "scripts" / "discovery.py")
    parser.add_argument("--output", type=Path, help="Optionally save the same JSON printed to stdout.")
    parser.add_argument("--sizes", type=int, nargs="+", default=[1000, 3000])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1 or any(size < 2 for size in args.sizes):
        parser.error("--repeats must be positive and each --sizes value must be at least 2")
    module_path = args.module.resolve()
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("bench_discovery", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_check = module._constraint_check
    checks = [0]

    def measured_check(*values):
        checks[0] += 1
        return original_check(*values)

    module._constraint_check = measured_check
    results = {
        "module": str(module_path),
        "scenario": "shared type, distinct tenant groups of five producers and five consumers; one consumer anchor",
        "clock": "time.perf_counter; median of independent in-memory runs; includes result construction, excludes canonical digest",
        "measurements": [],
    }
    for size in args.sizes:
        runs = []
        for _ in range(args.repeats):
            sample = corpus(size)
            gc.collect()
            checks[0] = 0
            started = perf_counter()
            found = module.discover(sample, anchors=["consumer-0000"])
            elapsed = perf_counter() - started
            serialized = json.dumps(found, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
            runs.append({"elapsed_seconds": elapsed, "constraint_checks": checks[0],
                         "observation_reads": sample.observation_reads,
                         "candidates": len(found["candidates"]), "paths": len(found["paths"]),
                         "sha256": hashlib.sha256(serialized).hexdigest()})
            del found, sample, serialized
        results["measurements"].append({
            "record_count": size,
            "median_seconds": median(run["elapsed_seconds"] for run in runs),
            "runs": runs,
        })
    rendered = json.dumps(results, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
