"""Repeatable offline ranking evaluation over explicitly fictional fixtures.

Run each implementation in its own process, using the same cases file:
    python tests/evaluate_local_ranking.py --scripts-dir scripts --output result.json

This measures candidate relevance and redundancy, not evidence validity, factual
accuracy or an inferred vulnerability. No quality threshold is asserted.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib
import json
from math import isclose, log2
from pathlib import Path
import sys
from types import SimpleNamespace


def metrics(ranked, relevance, k=5):
    """Binary recall/precision and graded nDCG; RR considers the full ranking.

    Missing results count against recall. Precision's denominator is the number
    actually returned up to K, as requested; empty positive queries score zero.
    No-answer cases are measured separately, rather than as perfect recall.
    """
    relevant = {ref for ref, grade in relevance.items() if grade > 0}
    if not relevant:
        return {"reciprocal_rank": None, "recall_at_5": None,
                "precision_at_5": None, "ndcg_at_5": None,
                "no_answer_correct": not ranked}
    top = ranked[:k]
    hits = sum(ref in relevant for ref in top)
    first = next((position for position, ref in enumerate(ranked, 1)
                  if ref in relevant), None)
    dcg = sum((2 ** relevance.get(ref, 0) - 1) / log2(position + 1)
              for position, ref in enumerate(top, 1))
    ideal = sum((2 ** grade - 1) / log2(position + 1)
                for position, grade in enumerate(
                    sorted(relevance.values(), reverse=True)[:k], 1))
    return {"reciprocal_rank": 1 / first if first else 0.0,
            "recall_at_5": hits / len(relevant),
            "precision_at_5": hits / len(top) if top else 0.0,
            "ndcg_at_5": dcg / ideal,
            "no_answer_correct": None}


def check_metrics():
    """Fixed arithmetic checks, independent of the implementation being scored."""
    result = metrics(["noise", "best", "context"], {"best": 3, "context": 1})
    assert result["reciprocal_rank"] == 0.5
    assert result["recall_at_5"] == 1
    assert result["precision_at_5"] == 2 / 3
    assert isclose(result["ndcg_at_5"], (7 / log2(3) + 1 / 2) / (7 + 1 / log2(3)))
    assert metrics([], {"best": 3})["recall_at_5"] == 0
    assert metrics([], {"best": 3})["precision_at_5"] == 0
    assert metrics([], {})["no_answer_correct"] is True
    assert metrics(["noise"], {})["no_answer_correct"] is False
    assert metrics(["noise"] * 5 + ["best"], {"best": 3})["recall_at_5"] == 0
    assert metrics(["noise"] * 5 + ["best"], {"best": 3})["reciprocal_rank"] == 1 / 6


def make_corpus(dataset, conditions):
    data = deepcopy(dataset)
    return SimpleNamespace(
        records={row["id"]: row for row in data.get("records", [])},
        entities={}, observations={},
        pages={row["page_id"]: row for row in data.get("pages", [])},
        blocks={row["page_id"] + "/" + row["block_id"]: row
                for row in data.get("blocks", [])},
        page_issues={}, current_conditions=deepcopy(conditions),
    )


def evaluate(rank, fixture):
    results = []
    for case in fixture["cases"]:
        corpus = make_corpus(fixture["datasets"][case["dataset"]],
                             case.get("current_conditions", {}))
        ranked, issues = rank(corpus, case["query"], case.get("anchors", []))
        references = [kind + ":" + rid for kind, rid in ranked]
        known = {"record:" + rid for rid in corpus.records}
        known.update("block:" + rid for rid in corpus.blocks)
        if not set(case["relevance"]).issubset(known):
            raise ValueError("Unknown relevance reference in " + case["id"])
        if len(references) != len(set(references)):
            raise ValueError("Duplicate candidate ID in " + case["id"])
        if not all(grade in {0, 1, 2, 3} for grade in case["relevance"].values()):
            raise ValueError("Invalid relevance grade in " + case["id"])
        results.append({
            "case_id": case["id"], "query": case["query"],
            "description": case["description"],
            "current_conditions": case.get("current_conditions", {}),
            "relevance": case["relevance"], "returned_count": len(references),
            "top_results": [{"rank": index, "ref": ref,
                             "relevance": case["relevance"].get(ref, 0)}
                            for index, ref in enumerate(references[:5], 1)],
            "metrics": metrics(references, case["relevance"]), "issues": issues,
        })
    positive = [row for row in results if row["metrics"]["reciprocal_rank"] is not None]
    unanswered = [row for row in results if row["metrics"]["no_answer_correct"] is not None]
    aggregate = {"case_count": len(results), "positive_case_count": len(positive),
                 "no_answer_case_count": len(unanswered)}
    for name in ("reciprocal_rank", "recall_at_5", "precision_at_5", "ndcg_at_5"):
        aggregate["mean_" + name] = (sum(row["metrics"][name] for row in positive)
                                      / len(positive)) if positive else None
    aggregate["no_answer_accuracy"] = (sum(row["metrics"]["no_answer_correct"]
                                           for row in unanswered) / len(unanswered)
                                       if unanswered else None)
    return {"fixture_notice": fixture["notice"], "grading": fixture["grading"],
            "metric_notes": {
                "reciprocal_rank": "First positive-grade candidate in the complete ranking.",
                "precision_at_5": "Positive-grade results / min(5, returned count); empty is 0.",
                "recall_at_5": "Positive-grade results in top 5 / all positive-grade references.",
                "ndcg_at_5": "Graded gain 2^grade - 1, logarithmic rank discount.",
                "aggregate": "Macro average over positive cases; no-answer accuracy is separate.",
                "no_answer_accuracy": "Fraction of labeled no-answer queries with zero candidates; candidate retrieval may legitimately return related context.",
            }, "aggregate": aggregate, "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scripts-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "scripts")
    parser.add_argument("--cases", type=Path,
                        default=Path(__file__).with_name("local_ranking_cases.json"))
    parser.add_argument("--output", type=Path,
                        help="Write full UTF-8 JSON here and print only aggregate metrics.")
    args = parser.parse_args()
    check_metrics()
    sys.path.insert(0, str(args.scripts_dir.resolve()))
    rank = importlib.import_module("search_index").rank
    report = evaluate(rank, json.loads(args.cases.read_text(encoding="utf-8")))
    report["scripts_dir"] = str(args.scripts_dir.resolve())
    report["cases_file"] = str(args.cases.resolve())
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps(report["aggregate"], indent=2))
    else:
        print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
