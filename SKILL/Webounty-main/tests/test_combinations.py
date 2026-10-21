"""Offline behavioral tests for compact, unverified AND/OR plans."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from combinations import build_combinations
from discovery import discover


def spec(kind, **constraints):
    return {"type": kind, "constraints": {"environment": "lab", **constraints}}


def record(rid, provides=(), needs=(), **extra):
    return {"id": rid, "kind": "Capability", "status": "verified", "revision": 1,
            "observation_refs": ["obs-" + rid],
            "capability": {"provides": list(provides), "needs": list(needs)}, **extra}


class Corpus:
    def __init__(self, records, unavailable=()):
        self.records = {row["id"]: row for row in records}
        self.observations = {oid: {} for row in records for oid in row.get("observation_refs", [])}
        self.pages, self.blocks = {}, {}
        self.unavailable = set(unavailable)

    def observation(self, oid):
        return {"status": "unavailable" if oid in self.unavailable else "ready"}


def combination(rows, consumer="C", unavailable=()):
    corpus = Corpus(rows, unavailable)
    candidates = discover(corpus, anchors=[consumer])["candidates"]
    return build_combinations(corpus.records, candidates, [consumer])[0]


def edge(producer, consumer, need_index=0, provide_index=0):
    return {"producer_ref": producer, "consumer_ref": consumer,
            "need_index": need_index, "provide_index": provide_index,
            "compatibility": "compatible", "producer_usable": True,
            "consumer_usable": True, "conflicts": [], "unknown_conditions": [],
            "source_issues": []}


class CombinationTests(unittest.TestCase):
    def test_independent_inputs_form_and_without_invented_dependency(self):
        result = combination([
            record("A", provides=[spec("task")]),
            record("B", provides=[spec("token")]),
            record("C", needs=[spec("task"), spec("token")]),
        ])
        self.assertEqual(result["operator"], "AND")
        self.assertEqual(result["plan"]["record_refs"], ["A", "B", "C"])
        self.assertEqual({(item["producer_ref"], item["consumer_ref"]) for item in result["plan"]["bindings"]},
                         {("A", "C"), ("B", "C")})
        self.assertEqual(result["plan"]["coverage"], {"required": 2, "covered": 2, "complete": True})
        self.assertEqual(result["plan"]["missing_preconditions"], [])
        self.assertEqual([item["coverage"] for item in result["inputs"]], ["candidate_ready"] * 2)
        self.assertEqual(result["status"], "candidate")
        self.assertFalse(result["evidence"])
        self.assertFalse(result["plan"]["joint_conditions"]["evidence"])

    def test_two_outputs_from_one_provider_bind_both_inputs_once_each(self):
        result = combination([
            record("A", provides=[spec("task"), spec("token")]),
            record("C", needs=[spec("task"), spec("token")]),
        ])
        self.assertEqual(result["plan"]["record_refs"], ["A", "C"])
        self.assertEqual({(item["provide_index"], item["need_index"]) for item in result["plan"]["bindings"]},
                         {(0, 0), (1, 1)})
        self.assertTrue(result["plan"]["coverage"]["complete"])

    def test_or_alternatives_are_references_and_only_one_is_selected(self):
        result = combination([
            record("A1", provides=[spec("task")]),
            record("A2", provides=[spec("task")]),
            record("B", provides=[spec("token")]),
            record("C", needs=[spec("task"), spec("token")]),
        ])
        self.assertEqual([item["producer_ref"] for item in result["inputs"][0]["alternatives"]], ["A1", "A2"])
        self.assertEqual(set(result["inputs"][0]["alternatives"][0]),
                         {"producer_ref", "provide_index", "consumer_ref", "need_index"})
        self.assertEqual(len(result["plan"]["bindings"]), 2)
        self.assertNotIn("A2", result["plan"]["record_refs"])
        self.assertIn("A2", result["record_refs"])

    def test_recursive_upstream_gap_is_retained_at_exact_record_and_need(self):
        result = combination([
            record("A", provides=[spec("task")], needs=[spec("session")]),
            record("B", provides=[spec("token")]),
            record("C", needs=[spec("task"), spec("token")]),
        ])
        gaps = {(item["record_ref"], item["need_index"]): item for item in result["plan"]["missing_preconditions"]}
        self.assertEqual(gaps[("A", 0)]["type"], "session")
        self.assertEqual(gaps[("C", 0)]["reason"], "upstream_preconditions_unresolved")
        self.assertEqual(result["plan"]["coverage"], {"required": 3, "covered": 1, "complete": False})
        self.assertEqual(result["inputs"][0]["coverage"], "unresolved")

    def test_recursive_provider_can_be_started_by_an_independent_leaf(self):
        result = combination([
            record("S", provides=[spec("session")]),
            record("A", provides=[spec("task")], needs=[spec("session")]),
            record("B", provides=[spec("token")]),
            record("C", needs=[spec("task"), spec("token")]),
        ])
        self.assertEqual(result["plan"]["coverage"], {"required": 3, "covered": 3, "complete": True})
        self.assertIn("S", result["plan"]["record_refs"])

    def test_dependency_cycle_cannot_bootstrap_itself(self):
        result = combination([
            record("A", provides=[spec("task")], needs=[spec("session")]),
            record("S", provides=[spec("session")], needs=[spec("task")]),
            record("B", provides=[spec("token")]),
            record("C", needs=[spec("task"), spec("token")]),
        ])
        self.assertFalse(result["plan"]["coverage"]["complete"])
        self.assertEqual(result["inputs"][0]["coverage"], "unresolved")
        self.assertIn("dependency_cycle", {gap["reason"] for gap in result["plan"]["missing_preconditions"]})

    def test_complete_alternative_is_preferred_over_lexically_first_dead_end(self):
        result = combination([
            record("A-dead", provides=[spec("task")], needs=[spec("absent")]),
            record("Z-ready", provides=[spec("task")]),
            record("B", provides=[spec("token")]),
            record("C", needs=[spec("task"), spec("token")]),
        ])
        self.assertIn("Z-ready", result["plan"]["record_refs"])
        self.assertNotIn("A-dead", result["plan"]["record_refs"])
        self.assertTrue(result["plan"]["coverage"]["complete"])

    def test_independent_alternative_breaks_recursive_cycle(self):
        result = combination([
            record("A", provides=[spec("task")], needs=[spec("session")]),
            record("S-cycle", provides=[spec("session")], needs=[spec("task")]),
            record("Z-start", provides=[spec("session")]),
            record("B", provides=[spec("token")]),
            record("C", needs=[spec("task"), spec("token")]),
        ])
        self.assertTrue(result["plan"]["coverage"]["complete"])
        self.assertNotIn("S-cycle", result["plan"]["record_refs"])

    def test_refuted_counterevidence_and_unavailable_observation_cannot_cover(self):
        variants = [({"status": "refuted"}, [], ()),
                    ({}, [record("counter", contradicts=["A"])], ()),
                    ({}, [], ("obs-A",))]
        for extra, additions, unavailable in variants:
            with self.subTest(extra=extra, additions=additions, unavailable=unavailable):
                result = combination([
                    record("A", provides=[spec("task")], **extra),
                    record("B", provides=[spec("token")]),
                    record("C", needs=[spec("task"), spec("token")]),
                    *additions,
                ], unavailable=unavailable)
                self.assertEqual(result["inputs"][0]["coverage"], "unresolved")
                self.assertNotIn("A", result["plan"]["record_refs"])
                self.assertFalse(result["plan"]["coverage"]["complete"])
                self.assertEqual(result["plan"]["missing_preconditions"][0]["reason"], "sources_unusable")

    def test_unknown_and_incompatible_connections_keep_specific_gaps(self):
        for provided, reason_field in [(spec("task", tenant="other"), "conflicts"),
                                       (spec("task"), "unknown_conditions")]:
            with self.subTest(provided=provided):
                result = combination([
                    record("A", provides=[provided]),
                    record("B", provides=[spec("token", tenant="target")]),
                    record("C", needs=[spec("task", tenant="target"), spec("token", tenant="target")]),
                ])
                self.assertEqual(result["inputs"][0]["coverage"], "unresolved")
                self.assertFalse(result["plan"]["coverage"]["complete"])
                gap = next(item for item in result["plan"]["missing_preconditions"] if item["record_ref"] == "C")
                self.assertTrue(gap[reason_field])

    def test_pairwise_compatible_edges_do_not_prove_joint_conditions(self):
        result = combination([
            record("A", provides=[spec("task", tenant="alpha")]),
            record("B", provides=[spec("token", tenant="beta")]),
            record("C", needs=[spec("task", tenant="alpha"), spec("token", tenant="beta")]),
        ])
        self.assertTrue(all(binding["compatibility"] == "compatible" for binding in result["plan"]["bindings"]))
        self.assertEqual(result["plan"]["coverage"]["covered"], 2)
        self.assertFalse(result["plan"]["coverage"]["complete"])
        conflict = next(item for item in result["plan"]["conflicts"] if item["constraint"] == "tenant")
        self.assertEqual({item["value"] for item in conflict["values"]}, {"alpha", "beta"})
        self.assertTrue({"A", "B"}.issubset({item["record_ref"] for item in conflict["values"]}))

    def test_record_conditions_are_checked_and_lower_conflict_alternative_is_preferred(self):
        result = combination([
            record("A-conflict", provides=[spec("task")], conditions={"tenant": "other"}),
            record("Z-aligned", provides=[spec("task")], conditions={"tenant": "target"}),
            record("B", provides=[spec("token")], conditions={"tenant": "target"}),
            record("C", needs=[spec("task"), spec("token")], conditions={"tenant": "target"}),
        ])
        self.assertIn("Z-aligned", result["plan"]["record_refs"])
        self.assertNotIn("A-conflict", result["plan"]["record_refs"])
        self.assertTrue(result["plan"]["coverage"]["complete"])

    def test_record_condition_conflict_and_missing_branch_declaration_require_review(self):
        for b_conditions, field in [({"tenant": "other"}, "conflicts"), ({}, "unknown_conditions")]:
            with self.subTest(b_conditions=b_conditions):
                result = combination([
                    record("A", provides=[spec("task")], conditions={"tenant": "target"}),
                    record("B", provides=[spec("token")], conditions=b_conditions),
                    record("C", needs=[spec("task"), spec("token")], conditions={"tenant": "target"}),
                ])
                self.assertFalse(result["plan"]["coverage"]["complete"])
                self.assertTrue(result["plan"][field])
                self.assertEqual(result["plan"]["joint_conditions"]["assessment"], "unresolved")

    def test_longer_complete_alternative_can_avoid_current_condition_conflict(self):
        result = combination([
            record("A-short", provides=[spec("task")], conditions={"tenant": "other"}),
            record("Z-long", provides=[spec("task")], needs=[spec("session")], conditions={"tenant": "target"}),
            record("S", provides=[spec("session")], conditions={"tenant": "target"}),
            record("B", provides=[spec("token")], conditions={"tenant": "target"}),
            record("C", needs=[spec("task"), spec("token")], conditions={"tenant": "target"}),
        ])
        self.assertIn("Z-long", result["plan"]["record_refs"])
        self.assertNotIn("A-short", result["plan"]["record_refs"])
        self.assertTrue(result["plan"]["coverage"]["complete"])

    def test_less_conflicting_branch_cannot_depend_on_its_active_consumer(self):
        result = combination([
            record("A-loop", provides=[spec("task")], needs=[spec("root-output")], conditions={"tenant": "target"}),
            record("Z-start", provides=[spec("task")], conditions={"tenant": "other"}),
            record("B", provides=[spec("token")], conditions={"tenant": "target"}),
            record("C", provides=[spec("root-output")], needs=[spec("task"), spec("token")], conditions={"tenant": "target"}),
        ])
        self.assertIn("Z-start", result["plan"]["record_refs"])
        self.assertNotIn("A-loop", result["plan"]["record_refs"])
        self.assertEqual(result["plan"]["missing_preconditions"], [])
        self.assertTrue(result["plan"]["conflicts"])

    def test_focus_and_stable_identity_ignore_order_and_alternative_count(self):
        rows = [record("A", provides=[spec("task"), spec("token")]),
                record("C", needs=[spec("task"), spec("token")]),
                record("single", needs=[spec("task")]),
                record("unrelated", needs=[spec("x"), spec("y")])]
        first = combination(rows)
        second = combination(list(reversed(rows)) + [record("B", provides=[spec("task")])])
        self.assertEqual(first["id"], second["id"])
        corpus = Corpus(rows)
        candidates = discover(corpus, anchors=["C"])["candidates"]
        self.assertEqual([item["consumer_ref"] for item in build_combinations(corpus.records, candidates, ["C", "single"])], ["C"])

    def test_many_alternatives_stay_compact_without_cartesian_plan_enumeration(self):
        rows = [record("C", needs=[spec("task"), spec("token"), spec("session")])]
        candidates = []
        for index, kind in enumerate(("task", "token", "session")):
            for alternative in range(70):
                rid = f"P-{index}-{alternative:03}"
                rows.append(record(rid, provides=[spec(kind)]))
                candidates.append(edge(rid, "C", index))
        results = build_combinations({row["id"]: row for row in rows}, candidates, ["C"])
        self.assertEqual(len(results), 1)
        self.assertEqual(sum(len(item["alternatives"]) for item in results[0]["inputs"]), 210)
        self.assertEqual(len(results[0]["plan"]["bindings"]), 3)

    def test_deep_upstream_chain_has_no_python_recursion_limit(self):
        depth = 1100
        rows = [record("S", provides=[spec("session")]),
                record("C", needs=[spec("value-1099"), spec("session")])]
        candidates = [edge("S", "C", 1), edge("P-1099", "C")]
        for index in range(depth):
            needs = [spec(f"value-{index - 1}")] if index else []
            rows.append(record(f"P-{index}", provides=[spec(f"value-{index}")], needs=needs))
            if index:
                candidates.append(edge(f"P-{index - 1}", f"P-{index}"))
        result = build_combinations({row["id"]: row for row in rows}, candidates, ["C"])[0]
        self.assertTrue(result["plan"]["coverage"]["complete"])
        self.assertEqual(result["plan"]["coverage"]["required"], depth + 1)


if __name__ == "__main__":
    unittest.main()
