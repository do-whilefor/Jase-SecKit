"""Changed invalid sources retain downstream AND groups for evidence review."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import discovery
from change_impact import build_impact
from discovery import discover
from test_change_impact import Fixture, record, spec


def corpus(*, status="withdrawn", consumer_tenant="lab-a", correction=False):
    rows = [
        record("UP", status=status, capability={"provides": [spec("seed")]}),
        record("A", capability={"needs": [spec("seed", consumer_tenant)],
                                  "provides": [spec("ticket", consumer_tenant)]}),
        record("B", capability={"provides": [spec("account", consumer_tenant)]}),
        record("C", status="blocked", capability={"needs": [spec("ticket", consumer_tenant),
                                                                  spec("account", consumer_tenant)]}),
        record("UNRELATED", capability={"needs": [spec("isolated-one"), spec("isolated-two")]}),
    ]
    if correction:
        rows.append(record("CORRECTION", contradicts=["UP"]))
    return Fixture(rows)


class CombinationInvalidationTests(unittest.TestCase):
    def assert_invalidated_combination(self, current, changed):
        before = deepcopy(current.__dict__)
        found = discover(current, changed=changed)
        groups = {group["consumer_ref"]: group for group in found["combinations"]}
        self.assertEqual(set(groups), {"C"})
        group = groups["C"]
        self.assertEqual([item["coverage"] for item in group["inputs"]], ["unresolved", "candidate_ready"])
        self.assertFalse(group["plan"]["coverage"]["complete"])
        self.assertFalse(group["evidence"])
        self.assertEqual(group["status"], "candidate")
        invalid = next(edge for edge in found["candidates"] if edge["producer_ref"] == "UP")
        self.assertFalse(invalid["producer_usable"])
        self.assertEqual(invalid["compatibility"], "unknown")
        self.assertFalse(invalid["evidence"])
        self.assertFalse(any(edge["producer_ref"] == "UP" for edge in group["plan"]["bindings"]))
        self.assertFalse(any("UP" in path["record_refs"] for path in found["paths"]))
        with patch("change_impact.discover", side_effect=AssertionError("reuse changed discovery")):
            impact = build_impact(current, changed, discovery=found)
        self.assertEqual([row["id"] for row in impact["affected_combinations"]], ["combination:C"])
        affected = impact["affected_combinations"][0]
        self.assertEqual([item["need_index"] for item in affected["affected_inputs"]], [0])
        self.assertEqual(affected["source_refs"], changed)
        self.assertFalse(affected["evidence"])
        self.assertEqual(current.__dict__, before)

    def test_changed_withdrawn_upstream_reaches_downstream_combination(self):
        self.assert_invalidated_combination(corpus(), ["UP"])

    def test_new_counterevidence_reaches_downstream_combination(self):
        self.assert_invalidated_combination(corpus(status="verified", correction=True), ["CORRECTION"])

    def test_changed_review_keeps_explicit_tenant_boundary(self):
        current = corpus(consumer_tenant="lab-b")
        found = discover(current, changed=["UP"])
        self.assertEqual(found["combinations"], [])
        self.assertNotIn("C", found["record_refs"])
        self.assertEqual([(edge["producer_ref"], edge["consumer_ref"]) for edge in found["candidates"]],
                         [("UP", "A")])
        self.assertEqual(found["candidates"][0]["compatibility"], "incompatible")

    def test_plain_anchor_keeps_existing_usable_component_focus(self):
        current = corpus()
        upstream = discover(current, anchors=["UP"])
        self.assertNotIn("C", upstream["record_refs"])
        self.assertEqual(upstream["combinations"], [])
        downstream = discover(current, anchors=["C"])
        self.assertEqual([group["consumer_ref"] for group in downstream["combinations"]], ["C"])
        self.assertIn("UP", downstream["combinations"][0]["record_refs"])
        self.assertFalse(downstream["combinations"][0]["plan"]["coverage"]["complete"])

    def test_changed_review_assesses_each_candidate_only_once(self):
        current = corpus()
        with patch("discovery._constraint_check", wraps=discovery._constraint_check) as checked:
            found = discover(current, changed=["UP"])
        self.assertEqual(checked.call_count, len(found["candidates"]))
        self.assertEqual({(edge["producer_ref"], edge["consumer_ref"]) for edge in found["candidates"]},
                         {("UP", "A"), ("A", "C"), ("B", "C")})


if __name__ == "__main__":
    unittest.main()
