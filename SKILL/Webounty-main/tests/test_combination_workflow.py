"""Multi-turn combination delivery and explicit expression review over local evidence."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import session
from context_views import finalize_context
from rag import Corpus, retrieve


def spec(name, aliases=()):
    return {"type": name, "aliases": list(aliases),
            "constraints": {"tenant": "lab-a", "environment": "synthetic"}}


def capability(rid, provides=(), needs=()):
    return {"id": rid, "kind": "Capability", "status": "observed", "summary": rid,
            "observation_refs": ["O-" + rid],
            "capability": {"provides": list(provides), "needs": list(needs)}}


class CombinationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        opened = session.start("combination-workflow", "Review local candidate inputs", self.project)
        self.root, self.run_id = Path(opened["root"]), opened["run_id"]

    def publish(self, records):
        state = json.loads((self.root / "state.json").read_text())
        observations = [{"id": oid, "content": {"synthetic": True, "observed": row["id"]}}
                        for row in records for oid in row.get("observation_refs", [])
                        if oid not in state["observations"]]
        path = self.project / "batch.json"
        path.write_text(json.dumps({"records": records, "observations": observations}), encoding="utf-8")
        args = session.parser().parse_args(["record", "--root", str(self.root), "--run-id", self.run_id,
                                            "--input", str(path)])
        return session.dispatch(args)

    def query(self, anchor="C", **options):
        return retrieve(self.root, self.run_id, "", [anchor], view="compact", cursor="main", **options)

    def initial(self):
        return self.publish([capability("A", [spec("job")]),
                             capability("C", needs=[spec("job"), spec("grant")])])

    def test_independent_inputs_become_one_candidate_then_counterevidence_reopens_gap(self):
        first = self.initial()
        self.assertEqual(first["chain_discovery"]["combinations"][0]["id"], "combination:C")
        initial = self.query()
        self.assertFalse(initial["chain_discovery"]["combinations"][0]["plan"]["coverage"]["complete"])
        repeat = self.query()
        self.assertEqual(repeat["chain_discovery"]["combinations"], [])
        self.assertIn({"kind": "chain_discovery.combinations", "id": "combination:C"}, repeat["unchanged_refs"])

        added = self.publish([capability("B", [spec("grant")])])
        self.assertIn("combination:C", {row["id"] for row in added["change_impact"]["affected_combinations"]})
        together = self.query()
        combined = together["chain_discovery"]["combinations"][0]
        self.assertEqual(combined["plan"]["record_refs"], ["A", "B", "C"])
        self.assertEqual({(edge["producer_ref"], edge["consumer_ref"]) for edge in combined["plan"]["bindings"]},
                         {("A", "C"), ("B", "C")})
        self.assertTrue(combined["plan"]["coverage"]["complete"])
        self.assertEqual(combined["status"], "candidate")
        self.assertFalse(combined["evidence"])
        delta = together["delta"]["combination_changes"][0]
        self.assertEqual([(row["need_index"], row["previous"], row["current"]) for row in delta["inputs"]],
                         [(1, "unresolved", "candidate_ready")])
        self.assertTrue(any(row["id"] == "type-review:C:1" for row in together["delta"]["retired_refs"]))

        self.publish([{"id": "REVOKED", "kind": "Fact", "status": "observed", "summary": "Synthetic revocation",
                       "observation_refs": ["O-REVOKED"], "contradicts": ["B"]}])
        revised = self.query()
        self.assertFalse(revised["chain_discovery"]["combinations"][0]["plan"]["coverage"]["complete"])
        lost = revised["delta"]["combination_changes"][0]["inputs"]
        self.assertEqual([(row["need_index"], row["current"]) for row in lost], [(1, "unresolved")])
        review = revised["chain_discovery"]["type_reviews"][0]
        self.assertEqual(review["reason"], "all_complete_matches_unusable_review_alternatives")
        self.assertIn("O-REVOKED", {row["id"] for row in revised["observations"]})
        refreshed = self.query(refresh=True)
        self.assertTrue(refreshed["chain_discovery"]["combinations"])
        self.assertFalse(refreshed["unchanged_refs"])
        self.assertNotIn("combination_changes", refreshed["delta"])

    def test_expression_hint_never_creates_edge_until_explicit_alias_is_written(self):
        self.publish([capability("P", [spec("ephemeral-token")]),
                      capability("Q", needs=[spec("temporary-token")]),
                      {"id": "OTHER", "kind": "Question", "status": "open", "summary": "Another question"}])
        first = self.query("Q")
        self.assertEqual(first["chain_discovery"]["candidates"], [])
        review = first["chain_discovery"]["type_reviews"][0]
        self.assertEqual(review["suggestions"][0]["producer_ref"], "P")
        self.assertFalse(review["evidence"])
        self.assertNotIn("P", {row["id"] for row in first["records"]})
        unrelated = self.query("OTHER")
        self.assertFalse(unrelated["delta"].get("retired_refs"))
        repeated = self.query("Q")
        self.assertEqual(repeated["chain_discovery"]["type_reviews"], [])

        self.publish([capability("P", [spec("ephemeral-token", aliases=["temporary-token"])])])
        matched = self.query("Q")
        self.assertTrue(any(row["producer_ref"] == "P" for row in matched["chain_discovery"]["candidates"]))
        self.assertEqual(matched["chain_discovery"]["type_reviews"], [])
        self.assertIn("type-review:Q:0", {row["id"] for row in matched["delta"]["retired_refs"]})

    def test_budget_omission_does_not_retire_a_still_relevant_review(self):
        self.initial()
        self.query()
        current = retrieve(self.root, self.run_id, "", ["C"], view="compact")
        current["chain_discovery"]["type_reviews"] = []
        current["budget"]["omitted_units"] = 1
        current["omissions"] = [{"kind": "chain_discovery.type_reviews", "reason": "budget_exhausted"}]
        partial = finalize_context(Corpus(self.root, self.run_id), current, cursor="main")
        self.assertFalse(partial["delta"].get("retired_refs"))
        again = self.query()
        self.assertIn({"kind": "chain_discovery.type_reviews", "id": "type-review:C:1"}, again["unchanged_refs"])

    def test_revoked_exact_match_does_not_hide_a_new_expression_for_its_replacement(self):
        self.publish([capability("A", [spec("job")]), capability("B", [spec("download-grant")]),
                      capability("C", needs=[spec("job"), spec("download-grant")])])
        self.query()
        self.publish([{"id": "REVOKED", "kind": "Fact", "status": "observed", "summary": "Revocation",
                       "observation_refs": ["O-REVOKED"], "contradicts": ["B"]}])
        self.query()
        replacement = spec("short-lived-pass")
        replacement["description"] = "May represent a download grant; verify actual consumption"
        self.publish([capability("D", [replacement])])
        before_query = (self.root / "state.json").read_bytes()
        result = self.query()
        review = result["chain_discovery"]["type_reviews"][0]
        self.assertEqual(review["reason"], "all_complete_matches_unusable_review_alternatives")
        self.assertEqual({row["producer_ref"] for row in review["suggestions"]}, {"D"})
        self.assertFalse(review["evidence"])
        self.assertFalse(any(row["producer_ref"] == "D" for row in result["chain_discovery"]["candidates"]))
        self.assertNotIn("D", {row["id"] for row in result["records"]})
        self.assertEqual(json.loads(before_query)["records"]["B"]["status"], "needs_review")
        self.assertEqual((self.root / "state.json").read_bytes(), before_query)

    def test_removing_a_required_input_retires_only_the_old_combination(self):
        self.initial()
        self.query()
        self.publish([capability("C", needs=[spec("job")])])
        result = self.query()
        self.assertEqual(result["chain_discovery"]["combinations"], [])
        self.assertIn("combination:C", {row["id"] for row in result["delta"]["retired_refs"]})

    def test_upstream_evidence_revision_marks_only_its_branch_even_when_coverage_is_unchanged(self):
        upstream = capability("UP", [spec("prerequisite")])
        self.publish([upstream, capability("A", [spec("job")], [spec("prerequisite")]),
                      capability("B", [spec("grant")]),
                      capability("C", needs=[spec("job"), spec("grant")])])
        self.query()
        upstream["observation_refs"].append("O-UP-NEW")
        self.publish([upstream])
        revised = self.query()
        change = next(row for row in revised["delta"]["combination_changes"]
                      if row["id"] == "combination:C")
        self.assertEqual([(row["need_index"], row["previous"], row["current"])
                          for row in change["inputs"]], [(0, "candidate_ready", "candidate_ready")])
        self.assertFalse(change["evidence"])


if __name__ == "__main__":
    unittest.main()
