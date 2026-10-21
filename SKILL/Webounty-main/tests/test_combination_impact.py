"""Combination impact reuses candidate plans and preserves current judgments."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from change_impact import build_impact
from rag import dependencies


def record(rid, **extra):
    return {"id": rid, "kind": "Fact", "status": "verified", "revision": 1,
            "observation_refs": ["O-" + rid], **extra}


class Corpus:
    def __init__(self, records):
        self.records = {row["id"]: row for row in records}
        self.record_dependencies = {rid: dependencies(row) for rid, row in self.records.items()}
        self.observations = {oid: {"id": oid} for row in records for oid in row["observation_refs"]}
        self.entities, self.artifacts, self.pages, self.blocks = {}, {}, {}, {}


def binding(producer, consumer, need_index):
    return {"producer_ref": producer, "provide_index": 0,
            "consumer_ref": consumer, "need_index": need_index}


def combination(consumer, providers):
    inputs = [{"need_index": index, "type": "input-" + str(index),
               "coverage": "candidate_ready" if producer else "unresolved",
               "alternatives": [binding(producer, consumer, index)] if producer else []}
              for index, producer in enumerate(providers)]
    refs = sorted({consumer, *(producer for producer in providers if producer)})
    return {"id": "combination:" + consumer, "consumer_ref": consumer,
            "record_refs": refs, "inputs": inputs,
            "plan": {"record_refs": list(refs),
                     "bindings": [{**edge, "compatibility": "compatible"}
                                  for item in inputs for edge in item["alternatives"]],
                     "coverage": {"required": len(inputs), "covered": sum(bool(p) for p in providers),
                                  "complete": all(providers)},
                     "missing_preconditions": [
                         {"record_ref": consumer, "need_index": index, "type": "input-" + str(index),
                          "reason": "no_candidate_provider", "candidate_provider_refs": []}
                         for index, producer in enumerate(providers) if not producer],
                     "conflicts": [], "unknown_conditions": []},
            "status": "candidate", "evidence": False}


class CombinationImpactTests(unittest.TestCase):
    def impact(self, corpus, changed, combinations, candidates=()):
        found = {"combinations": combinations, "candidates": list(candidates)}
        before = deepcopy((corpus.__dict__, found))
        with patch("change_impact.discover", side_effect=AssertionError("must reuse supplied discovery")):
            result = build_impact(corpus, changed, discovery=found)
        self.assertEqual((corpus.__dict__, found), before)
        self.assertFalse(result["evidence"])
        for row in result["affected_combinations"]:
            self.assertEqual(row["assessment"], "candidate")
            self.assertFalse(row["evidence"])
            self.assertNotIn("plan", row)
            self.assertNotIn("bindings", row)
            for item in row["affected_inputs"]:
                self.assertNotIn("alternatives", item)
        return result["affected_combinations"]

    def test_two_independent_inputs_only_mark_changed_branch(self):
        corpus = Corpus([record(rid) for rid in ("A", "B", "C", "X", "Y", "Z")])
        group = combination("C", ["A", "B"])
        rows = self.impact(corpus, ["O-A"], [group, combination("Z", ["X", "Y"])],
                           group["plan"]["bindings"])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["id"], row["consumer_ref"]), ("combination:C", "C"))
        self.assertEqual(row["source_refs"], ["O-A"])
        self.assertEqual(row["via_refs"], ["A", "C"])
        self.assertEqual([item["need_index"] for item in row["affected_inputs"]], [0])
        self.assertEqual(row["affected_inputs"][0]["via_refs"], ["A"])
        self.assertEqual(row["affected_inputs"][0]["coverage"], "candidate_ready")
        self.assertEqual(row["coverage"], group["plan"]["coverage"])

    def test_new_provider_revisits_blocked_group_without_satisfying_other_input(self):
        corpus = Corpus([record("NEW"), record("OLD", status="blocked")])
        group = combination("OLD", ["NEW", None])
        rows = self.impact(corpus, ["NEW"], [group], group["plan"]["bindings"])
        self.assertEqual([item["need_index"] for item in rows[0]["affected_inputs"]], [0])
        self.assertEqual(rows[0]["coverage"], {"required": 2, "covered": 1, "complete": False})
        self.assertEqual(rows[0]["missing_preconditions"], [
            {"record_ref": "OLD", "need_index": 1, "type": "input-1", "reason": "no_candidate_provider"}])
        self.assertEqual(corpus.records["OLD"]["status"], "blocked")

    def test_withdrawn_upstream_of_selected_branch_marks_downstream_input(self):
        corpus = Corpus([record("UP", status="withdrawn"), *(record(rid) for rid in ("A", "B", "C"))])
        group = combination("C", ["A", "B"])
        group["record_refs"].append("UP")
        # Current discovery drops the unusable UP -> A binding. Its reference
        # remains in A's unresolved prerequisite, and A is still selected for C.
        group["plan"]["missing_preconditions"] = [
            {"record_ref": "A", "need_index": 0, "type": "upstream",
             "reason": "sources_unusable", "candidate_provider_refs": ["UP"]}]
        group["inputs"][0]["coverage"] = "unresolved"
        group["plan"]["coverage"] = {"required": 3, "covered": 1, "complete": False}
        rows = self.impact(corpus, ["UP"], [group])
        self.assertEqual([item["need_index"] for item in rows[0]["affected_inputs"]], [0])
        self.assertEqual(rows[0]["affected_inputs"][0]["via_refs"], ["UP"])
        self.assertEqual(rows[0]["affected_inputs"][0]["coverage"], "unresolved")
        self.assertEqual(rows[0]["missing_preconditions"][0]["record_ref"], "A")

    def test_selected_upstream_bindings_and_joint_conflicts_remain_reviewable(self):
        corpus = Corpus([record(rid) for rid in ("UP", "MID", "A", "B", "C")])
        group = combination("C", ["A", "B"])
        group["record_refs"] += ["UP", "MID"]
        group["plan"]["record_refs"] = list(group["record_refs"])
        group["plan"]["bindings"] += [
            {**binding("UP", "MID", 0), "compatibility": "compatible"},
            {**binding("MID", "A", 0), "compatibility": "compatible"}]
        group["plan"]["conflicts"] = [
            {"code": "cross_branch_constraint_conflict", "constraint": "tenant", "values": [
                {"record_ref": "A", "role": "provide", "index": 0, "value": "one"},
                {"record_ref": "B", "role": "provide", "index": 0, "value": "two"}]}]
        group["plan"]["unknown_conditions"] = [
            {"code": "cross_branch_constraint_unknown", "constraint": "scope", "record_refs": ["UP"]}]
        group["plan"]["coverage"] = {"required": 4, "covered": 4, "complete": False}
        rows = self.impact(corpus, ["O-UP"], [group])
        self.assertEqual([item["need_index"] for item in rows[0]["affected_inputs"]], [0])
        self.assertEqual(rows[0]["affected_inputs"][0]["source_refs"], ["O-UP"])
        self.assertEqual(rows[0]["conflicts"], group["plan"]["conflicts"])
        self.assertEqual(rows[0]["unknown_conditions"], group["plan"]["unknown_conditions"])

    def test_alternative_change_is_reviewed_even_when_not_selected(self):
        corpus = Corpus([record(rid) for rid in ("A", "ALT", "B", "C")])
        group = combination("C", ["A", "B"])
        group["record_refs"].append("ALT")
        group["inputs"][0]["alternatives"].append(binding("ALT", "C", 0))
        rows = self.impact(corpus, ["ALT"], [group])
        self.assertEqual([item["need_index"] for item in rows[0]["affected_inputs"]], [0])
        self.assertEqual(rows[0]["affected_inputs"][0]["via_refs"], ["ALT"])

    def test_direct_consumer_change_marks_its_inputs(self):
        corpus = Corpus([record(rid) for rid in ("A", "B", "C")])
        rows = self.impact(corpus, ["C"], [combination("C", ["A", "B"])])
        self.assertEqual([item["need_index"] for item in rows[0]["affected_inputs"]], [0, 1])

    def test_unchanged_unknown_and_unrelated_records_do_not_report_combinations(self):
        corpus = Corpus([record(rid) for rid in ("A", "B", "C", "OTHER")])
        for changed in ([], ["UNKNOWN"], ["OTHER"]):
            with self.subTest(changed=changed):
                self.assertEqual(self.impact(corpus, changed, [combination("C", ["A", "B"])]), [])


if __name__ == "__main__":
    unittest.main()
