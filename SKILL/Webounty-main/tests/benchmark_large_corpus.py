"""Large local-source benchmark. Run: python3 -B tests/benchmark_large_corpus.py --mib 128

Uses uncompressed synthetic UTF-8 originals, no model, network, target traffic or
third-party Python package. Reports this machine's wall time and process RSS;
does not claim arbitrary-file or end-to-end Claude performance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sys
import tempfile
from time import perf_counter

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rag import Corpus, retrieve
from search_index import rank
from session import read_ids, start
from store import publish


def benchmark(mib):
    with tempfile.TemporaryDirectory(prefix="webounty-large-") as temporary:
        project = Path(temporary)
        source = project / "synthetic-responses.txt"
        # Mixed routes, fields, status codes and Chinese notes; repeated blocks
        # make the fixture reproducible, not representative of term diversity.
        rows = [f'{i} GET /reports/{i % 17} tenant-{i % 7} status={200 if i % 3 else 403} '
                'baseline observed 权限复核 conditions remain explicit\n' for i in range(257)]
        block = "".join(rows).encode()
        size = mib * 1024 * 1024
        checksum = hashlib.sha256()
        with source.open("wb") as stream:
            remaining = size
            while remaining:
                piece = block if remaining >= len(block) else b" " * remaining
                stream.write(piece)
                checksum.update(piece)
                remaining -= len(piece)
            marker = b"\nlastsourceonlyneedle\n"
            stream.write(marker)
            checksum.update(marker)
        owner = start("large-source", "Review local source records and current conditions", project)
        root, run_id = Path(owner["root"]), owner["run_id"]
        begun = perf_counter()
        publication = publish(root, run_id, {
            "observations": [{"id": "O-BIG", "summary": "Synthetic captured source",
                "source_path": str(source), "content": {"environment": "local-fixture", "response": {"status": 200}}}],
            "records": [{"id": "F-BIG", "kind": "Fact", "status": "observed",
                "summary": "Local body saved; business effect is unverified", "observation_refs": ["O-BIG"]}]})
        publication_seconds = perf_counter() - begun
        state = json.loads((root / "state.json").read_text())
        assert state["artifacts"]["SRC-O-BIG"]["sha256"] == checksum.hexdigest()
        begun = perf_counter()
        context = retrieve(root, run_id, "lastsourceonlyneedle", view="compact", cursor="large")
        query_seconds = perf_counter() - begun
        observation = next(row for row in context["observations"] if row["id"] == "O-BIG")
        assert observation["status"] == "ready" and observation["raw_expanded"] is False
        hit = observation["source_match"]
        assert hit["evidence"] is False
        expanded = read_ids(Corpus(root, run_id, lazy_pages=True), [hit["artifact_id"]],
                            offset=hit["offset"], length=hit["length"])
        artifact = expanded["package"]["artifacts"][0]
        assert "lastsourceonlyneedle" in artifact["content"]
        assert artifact["range"]["sha256"] == hit["sha256"]
        begun = perf_counter()
        update = publish(root, run_id, {"records": [{"id": "F-BIG", "summary": "Current interpretation revised",
                    "change_reason": "Local benchmark updates the interpretation without changing original evidence."}]})
        update_seconds = perf_counter() - begun
        assert update["retrieval_index"]["source_chunks_indexed"] == 0
        corpus = Corpus(root, run_id, lazy_pages=True)
        assert ("observation", "O-BIG") in rank(corpus, "lastsourceonlyneedle", [])[0]
        assert corpus.retrieval_index_stats["signature_checks"] == 0
        assert corpus.retrieval_index_stats["tokenized_fields"] == 0
        db_bytes = (root / "cache/retrieval.sqlite").stat().st_size
        shutil.rmtree(root / "cache")
        begun = perf_counter()
        rebuilt = Corpus(root, run_id, lazy_pages=True)
        assert ("observation", "O-BIG") in rank(rebuilt, "lastsourceonlyneedle", [])[0]
        rebuild_seconds = perf_counter() - begun
        # Make an actual source change and ensure the old derived hit disappears.
        with (root / "evidence/O-BIG.source").open("r+b") as stream:
            stream.seek(size)
            stream.write(b"X")
        assert ("observation", "O-BIG") not in rank(
            Corpus(root, run_id, lazy_pages=True), "lastsourceonlyneedle", [])[0]
        return {"source_bytes": source.stat().st_size, "source_sha256": checksum.hexdigest(),
                "index_bytes_before_rebuild": db_bytes, "publication_seconds": publication_seconds,
                "compact_query_seconds": query_seconds, "interpretation_update_seconds": update_seconds,
                "cold_rebuild_seconds": rebuild_seconds,
                "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                "compact_response_characters": len(json.dumps(context, ensure_ascii=False)),
                "range_bytes": artifact["range"]["length"], "initial_index": publication["retrieval_index"],
                "update_index": update["retrieval_index"], "warm_index": corpus.retrieval_index_stats,
                "checks": {"tail_recalled": True, "range_hash_matches_original": True,
                           "unchanged_source_not_reindexed": True, "cold_rebuild_recalled": True,
                           "tampered_source_rejected": True}, "model_calls": 0,
                "limitations": "One synthetic UTF-8 source with repeated text blocks; Linux process RSS, not an arbitrary-corpus capacity guarantee."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mib", type=int, default=128)
    args = parser.parse_args()
    if args.mib < 1:
        parser.error("--mib must be positive")
    print(json.dumps(benchmark(args.mib), ensure_ascii=False, indent=2))
