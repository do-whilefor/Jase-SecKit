"""Offline behavioral tests for session-wide capability combinations."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from discovery import discover
import discovery


class CorpusFixture:
    def __init__(self, records, *, unavailable=()):
        self.records = {row["id"]: row for row in records}
        self.observations = {oid: {"id": oid} for row in records for oid in row.get("observation_refs", [])}
        self.pages, self.blocks = {}, {}
        self.unavailable = set(unavailable)

    def observation(self, oid):
        return {"status": "unavailable" if oid in self.unavailable else "ready"}


def spec(kind, *, tenant="tenant-a", purpose="export", aliases=(), **constraints):
    return {"type": kind, "aliases": list(aliases),
            "constraints": {"tenant": tenant, "purpose": purpose, **constraints}}


def record(rid, *, provides=(), needs=(), status="verified", evidence=True, **extra):
    return {"id": rid, "kind": "Capability", "revision": 1, "status": status,
            "summary": rid, "capability": {"provides": list(provides), "needs": list(needs)},
            "observation_refs": [f"obs-{rid}"] if evidence else [], **extra}


class DiscoveryTests(unittest.TestCase):
    def test_full_session_backward_search_does_not_need_lexical_overlap_or_links(self):
        corpus = CorpusFixture([
            record("round-2", provides=[spec("export_job_id")], summary="早期获得的编号"),
            record("round-10", needs=[spec("EXPORT-JOB-ID")], summary="当前受阻操作"),
        ])
        result = discover(corpus, query="当前受阻", anchors=["round-10"])
        self.assertEqual(len(result["candidates"]), 1)
        edge = result["candidates"][0]
        self.assertEqual(edge["producer_ref"], "round-2")
        self.assertEqual(edge["compatibility"], "compatible")
        self.assertFalse(edge["evidence"])
        self.assertIn(["round-2", "round-10"], [path["record_refs"] for path in result["paths"]])

    def test_forward_consumer_can_match_explicit_alias(self):
        corpus = CorpusFixture([
            record("new", provides=[spec("job_id", aliases=["任务标识"])]),
            record("old", needs=[spec("任务标识")]),
        ])
        edge = discover(corpus, changed=["new"])["candidates"][0]
        self.assertEqual(edge["consumer_ref"], "old")
        self.assertEqual(edge["matched_names"], ["任务标识"])

    def test_partial_words_do_not_match_distinct_types(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("login credential")]),
            record("b", needs=[spec("download credential")]),
        ])
        self.assertEqual(discover(corpus, anchors=["b"])["candidates"], [])

    def test_explicit_tenant_and_purpose_conflicts_remain_visible(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("credential", tenant="tenant-b", purpose="login")]),
            record("b", needs=[spec("credential")]),
        ])
        result = discover(corpus, anchors=["b"])
        edge = result["candidates"][0]
        self.assertEqual(edge["compatibility"], "incompatible")
        self.assertEqual({item["constraint"] for item in edge["conflicts"]}, {"tenant", "purpose"})
        self.assertEqual(result["paths"], [])
        self.assertTrue(edge["missing_preconditions"])

    def test_missing_condition_never_means_universal_compatibility(self):
        corpus = CorpusFixture([
            record("a", provides=[{"type": "token", "constraints": {"tenant": "tenant-a"}}]),
            record("b", needs=[{"type": "token", "constraints": {}}]),
        ])
        edge = discover(corpus, anchors=["b"])["candidates"][0]
        self.assertEqual(edge["compatibility"], "unknown")
        self.assertEqual(edge["unknown_conditions"][0]["constraint"], "tenant")
        self.assertTrue(edge["missing_preconditions"])

    def test_empty_conditions_and_absent_evidence_stay_unknown(self):
        corpus = CorpusFixture([
            record("a", provides=[{"type": "token"}], evidence=False),
            record("b", needs=[{"type": "token"}], evidence=False),
        ])
        edge = discover(corpus, anchors=["b"])["candidates"][0]
        self.assertEqual(edge["compatibility"], "unknown")
        self.assertIn("no_source_evidence", {item["code"] for item in edge["source_issues"]})
        self.assertFalse(edge["evidence"])

    def test_all_consumer_and_producer_needs_are_accounted_for(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("task")], needs=[spec("session")]),
            record("b", needs=[spec("task"), spec("credential")]),
        ])
        edge = discover(corpus, anchors=["b"])["candidates"][0]
        self.assertEqual({(item["record_ref"], item["type"]) for item in edge["missing_preconditions"]},
                         {("a", "session"), ("b", "credential")})

    def test_multi_input_binding_and_missing_preconditions_in_full_path(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("session"), spec("task")]),
            record("b", needs=[spec("session")], provides=[spec("credential")]),
            record("c", needs=[spec("task"), spec("credential")]),
        ])
        result = discover(corpus, changed=["b"])
        paths = {tuple(path["record_refs"]): path for path in result["paths"]}
        self.assertIn(("a", "b", "c"), paths)
        path = paths[("a", "b", "c")]
        self.assertEqual(path["missing_preconditions"], [])
        self.assertEqual(len(path["bindings"]), 3)
        self.assertEqual(path["status"], "candidate")
        self.assertFalse(path["evidence"])
        self.assertIn("simultaneous", path["validation_required"])

    def test_two_outputs_from_same_provider_account_for_two_inputs(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("task"), spec("credential")]),
            record("b", needs=[spec("task"), spec("credential")]),
        ])
        result = discover(corpus, anchors=["b"])
        self.assertEqual(len(result["candidates"]), 2)
        for edge in result["candidates"]:
            self.assertEqual(edge["missing_preconditions"], [])
            self.assertEqual(len(edge["bindings"]), 2)

    def test_refuted_provider_is_diagnostic_only(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("task")], status="refuted"),
            record("b", needs=[spec("task")]),
        ])
        result = discover(corpus, anchors=["b"])
        edge = result["candidates"][0]
        self.assertEqual(edge["compatibility"], "unknown")
        self.assertFalse(edge["producer_usable"])
        self.assertTrue(edge["missing_preconditions"])
        self.assertEqual(result["paths"], [])

    def test_new_counterevidence_invalidates_existing_provider(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("task")]),
            record("b", needs=[spec("task")]),
            record("correction", contradicts=["a"]),
        ])
        result = discover(corpus, anchors=["b"])
        self.assertFalse(result["candidates"][0]["producer_usable"])
        self.assertIn("correction", result["record_refs"])
        self.assertEqual(result["paths"], [])

    def test_changed_counterevidence_is_itself_a_discovery_focus(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("task")]),
            record("b", needs=[spec("task")]),
            record("correction", contradicts=["a"]),
        ])
        result = discover(corpus, changed=["correction"])
        self.assertEqual(len(result["candidates"]), 1)
        self.assertFalse(result["candidates"][0]["producer_usable"])

    def test_correction_owner_is_invalidated_without_invalidating_replacement(self):
        for relation in ("corrected_by", "superseded_by", "correction_refs", "contradicted_by"):
            with self.subTest(relation=relation):
                corpus = CorpusFixture([
                    record("old", provides=[spec("task")], **{relation: ["new"]}),
                    record("new", provides=[spec("task")]),
                    record("consumer", needs=[spec("task")]),
                ])
                result = discover(corpus, anchors=["consumer"])
                edges = {edge["producer_ref"]: edge for edge in result["candidates"]}
                self.assertFalse(edges["old"]["producer_usable"])
                self.assertEqual(edges["old"]["compatibility"], "unknown")
                self.assertTrue(edges["new"]["producer_usable"])
                self.assertEqual(edges["new"]["compatibility"], "compatible")
                self.assertIn(["new", "consumer"], [path["record_refs"] for path in result["paths"]])
                self.assertNotIn(["old", "consumer"], [path["record_refs"] for path in result["paths"]])

    def test_contradicts_invalidates_target_without_invalidating_author(self):
        corpus = CorpusFixture([
            record("old", provides=[spec("task")]),
            record("new", provides=[spec("task")], contradicts=["old"]),
            record("consumer", needs=[spec("task")]),
        ])
        result = discover(corpus, anchors=["consumer"])
        edges = {edge["producer_ref"]: edge for edge in result["candidates"]}
        self.assertFalse(edges["old"]["producer_usable"])
        self.assertEqual(edges["old"]["compatibility"], "unknown")
        self.assertTrue(edges["new"]["producer_usable"])
        self.assertEqual(edges["new"]["compatibility"], "compatible")

    def test_changed_source_brings_derived_capability_into_focus(self):
        corpus = CorpusFixture([
            record("source"),
            record("a", provides=[spec("task")], source_refs=["source"]),
            record("b", needs=[spec("task")]),
        ])
        self.assertEqual(len(discover(corpus, changed=["source"])["candidates"]), 1)

    def test_stale_or_unavailable_source_cannot_produce_usable_path(self):
        source = record("source")
        source["revision"] = 2
        corpus = CorpusFixture([
            source,
            record("a", provides=[spec("task")], evidence=False, source_refs=[{"id": "source", "revision": 1}]),
            record("b", needs=[spec("task")]),
        ], unavailable=["obs-source"])
        result = discover(corpus, anchors=["b"])
        edge = result["candidates"][0]
        self.assertFalse(edge["producer_usable"])
        self.assertIn("stale_source", {item["code"] for item in edge["source_issues"]})
        self.assertEqual(result["paths"], [])

    def test_valid_source_record_provides_traceable_evidence(self):
        corpus = CorpusFixture([
            record("source"),
            record("a", provides=[spec("task")], evidence=False, source_refs=[{"id": "source", "revision": 1}]),
            record("b", needs=[spec("task")]),
        ])
        edge = discover(corpus, anchors=["b"])["candidates"][0]
        self.assertEqual(edge["compatibility"], "compatible")
        self.assertIn("obs-source", edge["observation_refs"])

    def test_own_observation_cannot_override_refuted_supporting_fact(self):
        corpus = CorpusFixture([
            record("source", status="refuted"),
            record("a", provides=[spec("task")], supporting_fact_ids=["source"]),
            record("b", needs=[spec("task")]),
        ])
        result = discover(corpus, changed=["source"])
        edge = result["candidates"][0]
        self.assertEqual(edge["compatibility"], "unknown")
        self.assertFalse(edge["producer_usable"])
        self.assertIn("obs-a", edge["observation_refs"])
        self.assertEqual(result["paths"], [])

    def test_revision_checks_apply_to_all_forward_supporting_refs(self):
        for field in ("requires", "evidence_refs", "step_refs", "supporting_fact_ids"):
            with self.subTest(field=field):
                source = record("source")
                source["revision"] = 2
                corpus = CorpusFixture([
                    source,
                    record("a", provides=[spec("task")], **{field: [{"id": "source", "revision": 1}]}),
                    record("b", needs=[spec("task")]),
                ])
                edge = discover(corpus, anchors=["b"])["candidates"][0]
                self.assertFalse(edge["producer_usable"])
                self.assertIn("stale_source", {issue["code"] for issue in edge["source_issues"]})

    def test_chain_navigation_does_not_turn_steps_into_original_evidence(self):
        chain = record("chain", provides=[spec("task")], evidence=False,
                       status="candidate", steps=["source"], links=[])
        chain["kind"] = "Chain"
        corpus = CorpusFixture([record("source"), chain, record("b", needs=[spec("task")])])
        edge = discover(corpus, anchors=["b"])["candidates"][0]
        self.assertEqual(edge["compatibility"], "unknown")
        self.assertNotIn("obs-source", edge["observation_refs"])
        self.assertIn("no_source_evidence", {issue["code"] for issue in edge["source_issues"]})

    def test_source_cycle_is_unknown_and_terminates(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("task")], source_refs=["source"]),
            record("source", source_refs=["a"]),
            record("b", needs=[spec("task")]),
        ])
        result = discover(corpus, anchors=["b"])
        self.assertEqual(result["candidates"][0]["compatibility"], "unknown")
        self.assertIn("source_cycle", {issue["code"] for issue in result["issues"]})

    def test_cycle_avoidance_and_unrelated_component_exclusion(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("task")], needs=[spec("token")]),
            record("b", provides=[spec("token")], needs=[spec("task")]),
            record("other-a", provides=[spec("unrelated")]),
            record("other-b", needs=[spec("unrelated")]),
        ])
        result = discover(corpus, anchors=["a"])
        self.assertNotIn("other-a", result["record_refs"])
        for path in result["paths"]:
            self.assertEqual(len(path["record_refs"]), len(set(path["record_refs"])))

    def test_conflicting_neighbor_does_not_expand_an_unrelated_branch(self):
        corpus = CorpusFixture([
            record("focus", needs=[spec("task")]),
            record("rival", provides=[spec("task", tenant="tenant-b")], needs=[spec("rival-session", tenant="tenant-b")]),
            record("rival-source", provides=[spec("rival-session", tenant="tenant-b")]),
        ])
        result = discover(corpus, anchors=["focus"])
        self.assertEqual(len(result["candidates"]), 1)
        self.assertNotIn("rival-source", result["record_refs"])

    def test_unrelated_component_does_not_open_raw_evidence(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("task")]),
            record("b", needs=[spec("task")]),
            record("other-a", provides=[spec("unrelated")]),
            record("other-b", needs=[spec("unrelated")]),
        ])
        read = []
        def observed(oid):
            read.append(oid)
            return {"status": "ready"}
        corpus.observation = observed
        discover(corpus, anchors=["b"])
        self.assertEqual(set(read), {"obs-a", "obs-b"})

    def test_low_cvss_provider_is_never_pruned(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("task")], cvss={"score": 0.0}),
            record("b", needs=[spec("task")]),
        ])
        self.assertEqual(len(discover(corpus, anchors=["b"])["candidates"]), 1)

    def test_page_anchor_resolves_source_records(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("task")]),
            record("b", needs=[spec("task")]),
        ])
        corpus.pages["question"] = {"page_id": "question", "source_refs": [{"id": "b", "revision": 1}], "blocks": []}
        result = discover(corpus, anchors=["question"])
        self.assertEqual(len(result["candidates"]), 1)

    def test_default_blocked_step_is_a_focus(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("task")]),
            record("b", needs=[spec("task")], status="blocked"),
        ])
        self.assertTrue(discover(corpus)["paths"])

    def test_focused_join_checks_only_incident_pairs_once(self):
        rows = []
        for index in range(10):
            item = spec("task", tenant=f"tenant-{index // 2}", aliases=["任务标识"])
            rows.append(record(f"producer-{index}", provides=[item]))
            rows.append(record(f"consumer-{index}", needs=[item]))
        corpus = CorpusFixture(rows)
        with patch("discovery._constraint_check", wraps=discovery._constraint_check) as checked:
            result = discover(corpus, anchors=["consumer-0"])
        # The anchored tenant has 2 producers and 2 consumers. Keep every edge
        # incident on those records, including conflicting boundary diagnostics,
        # but never assess the unrelated 8-by-8 producer/consumer product.
        expected = {(pid, cid) for pid in range(10) for cid in range(10) if pid < 2 or cid < 2}
        actual = {(int(edge["producer_ref"].split("-")[1]), int(edge["consumer_ref"].split("-")[1]))
                  for edge in result["candidates"]}
        self.assertEqual(actual, expected)
        self.assertEqual(checked.call_count, len(expected))
        self.assertTrue(all(edge["matched_names"] == ["task", "任务标识"] for edge in result["candidates"]))

    def test_unfocused_join_keeps_every_actual_type_match(self):
        corpus = CorpusFixture([
            record("a", provides=[spec("task", aliases=["任务标识"])]),
            record("b", provides=[spec("任务标识")]),
            record("c", needs=[spec("task", aliases=["任务标识"])]),
            record("d", needs=[spec("任务标识")]),
            record("unrelated", needs=[spec("credential")]),
        ])
        result = discover(corpus)
        self.assertEqual({(edge["producer_ref"], edge["consumer_ref"]) for edge in result["candidates"]},
                         {("a", "c"), ("a", "d"), ("b", "c"), ("b", "d")})


if __name__ == "__main__":
    unittest.main()
