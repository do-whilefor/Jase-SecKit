"""Changes identify review work without promoting candidates to evidence."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from change_impact import build_impact
from discovery import discover
from rag import dependencies


def spec(name, tenant="lab-a"):
    return {"type": name, "constraints": {"tenant": tenant}}


def record(rid, **extra):
    return {"id": rid, "kind": "Fact", "revision": 1, "status": "verified",
            "observation_refs": ["O-" + rid], **extra}


class Fixture:
    def __init__(self, records, pages=()):
        self.records = {row["id"]: row for row in records}
        self.observations = {oid: {"id": oid, "artifact_id": "ART-" + oid}
                             for row in records for oid in row.get("observation_refs", [])}
        self.artifacts = {row["artifact_id"]: {"id": row["artifact_id"]}
                          for row in self.observations.values()}
        self.entities = {}
        self.pages = {page["page_id"]: page for page in pages}
        self.blocks = {page["page_id"] + "/" + block["block_id"]: {**block, "page_id": page["page_id"]}
                       for page in pages for block in page.get("blocks", [])}
        self.record_dependencies = {rid: dependencies(row) for rid, row in self.records.items()}

    def observation(self, oid):
        return {"status": "ready"}


def page(pid, rid, required=()):
    return {"page_id": pid, "source_refs": [rid], "blocks": [
        {"block_id": "B", "source_refs": [rid], "required_block_refs": list(required)}]}


def ids(rows):
    return {row["id"] for row in rows}


class ChangeImpactTests(unittest.TestCase):
    def test_empty_or_unknown_changes_do_not_discover_unrelated_research(self):
        corpus = Fixture([record("OLD", status="blocked", capability={"needs": [spec("ticket")]})])
        with patch("change_impact.discover") as discovery:
            for changed in ([], ["not-in-this-session"]):
                result = build_impact(corpus, changed)
                self.assertEqual(result["changed_refs"], [])
                self.assertEqual(result["affected_records"], [])
                self.assertEqual(result["connections_to_review"], [])
            discovery.assert_not_called()

    def test_artifact_change_reaches_observation_judgment_page_and_chain(self):
        corpus = Fixture([
            record("F"), record("CAP", source_refs=[{"id": "F", "revision": 1}]),
            record("CHAIN", kind="Chain", steps=["CAP"]), record("UNRELATED"),
        ], [page("P", "CAP"), page("OTHER", "UNRELATED")])
        before = deepcopy(corpus.__dict__)
        result = build_impact(corpus, ["ART-O-F"], discovery={})
        self.assertEqual(ids(result["affected_records"]), {"F", "CAP"})
        self.assertEqual(ids(result["affected_chains"]), {"CHAIN"})
        self.assertEqual({row["page_id"] for row in result["affected_pages"]}, {"P"})
        self.assertEqual(result["affected_pages"][0]["block_refs"], ["P/B"])
        self.assertEqual(result["affected_chains"][0]["source_refs"], ["ART-O-F"])
        self.assertEqual(corpus.__dict__, before)
        self.assertFalse(result["evidence"])

    def test_new_counterevidence_reaches_target_and_its_downstream_chain(self):
        corpus = Fixture([
            record("OLD"), record("CAP", supporting_fact_ids=["OLD"]),
            record("CHAIN", kind="Chain", steps=["CAP"]),
            record("NEGATIVE", contradicts=["OLD"]),
        ])
        result = build_impact(corpus, [{"id": "NEGATIVE", "change": "new"}], discovery={})
        self.assertEqual(ids(result["affected_records"]), {"NEGATIVE", "OLD", "CAP"})
        self.assertEqual(ids(result["affected_chains"]), {"CHAIN"})
        target = next(row for row in result["affected_records"] if row["id"] == "OLD")
        self.assertIn({"code": "counterevidence_changed", "via_refs": ["NEGATIVE"]}, target["reasons"])
        self.assertEqual(result["affected_chains"][0]["source_refs"], ["NEGATIVE"])

    def test_replacement_does_not_depend_on_old_judgment(self):
        corpus = Fixture([record("OLD", corrected_by=["NEW"]), record("NEW")])
        old = build_impact(corpus, ["OLD"], discovery={})
        self.assertEqual(ids(old["affected_records"]), {"OLD"})
        new = build_impact(corpus, ["NEW"], discovery={})
        self.assertEqual(ids(new["affected_records"]), {"OLD", "NEW"})

    def test_required_block_reaches_other_page_without_unrelated_siblings(self):
        original = page("P", "F")
        original["blocks"].append({"block_id": "UNRELATED", "source_refs": ["OTHER"]})
        corpus = Fixture([record("F"), record("OTHER"), record("ASSESSMENT")], [
            original, page("DEPENDENT", "ASSESSMENT", [{"page_id": "P", "block_id": "B"}]),
        ])
        result = build_impact(corpus, ["P/B"], discovery={})
        pages = {row["page_id"]: row for row in result["affected_pages"]}
        self.assertEqual(set(pages), {"P", "DEPENDENT"})
        self.assertEqual(pages["P"]["block_refs"], ["P/B"])
        self.assertEqual(pages["DEPENDENT"]["block_refs"], ["DEPENDENT/B"])
        self.assertEqual(pages["DEPENDENT"]["source_refs"], ["P/B"])
        self.assertEqual(result["affected_records"], [])
        whole_page = build_impact(corpus, ["P"], discovery={})
        root = next(row for row in whole_page["affected_pages"] if row["page_id"] == "P")
        self.assertEqual(root["block_refs"], ["P/B", "P/UNRELATED"])

    def test_new_observation_in_page_scope_marks_review_without_inventing_fact_relation(self):
        p = page("P", "F")
        p["discovery_scope"] = {"subject_refs": ["APP"]}
        corpus = Fixture([record("F"), record("NEW")], [p])
        corpus.entities["APP"] = {"id": "APP"}
        corpus.observations["O-NEW"]["subject_refs"] = ["APP"]
        result = build_impact(corpus, ["O-NEW"], discovery={})
        self.assertEqual(ids(result["affected_records"]), {"NEW"})
        self.assertEqual(result["affected_pages"][0]["page_id"], "P")
        self.assertEqual(result["affected_pages"][0]["block_refs"], [])
        self.assertIn({"code": "scoped_observation_changed", "via_refs": ["O-NEW"]},
                      result["affected_pages"][0]["reasons"])

    def test_new_provider_points_to_old_failed_need_without_reopening_it(self):
        corpus = Fixture([
            record("NEW", capability={"provides": [spec("ticket")]}),
            record("OLD", status="failed", capability={"needs": [spec("account"), spec("ticket")]}),
            record("CHAIN", kind="Chain", steps=["OLD"]),
        ], [page("OLD-PAGE", "OLD")])
        found = discover(corpus, changed=["NEW"])
        before = deepcopy(corpus.__dict__)
        with patch("change_impact.discover", side_effect=AssertionError("must reuse discovery")):
            result = build_impact(corpus, ["NEW"], discovery=found)
        self.assertEqual(corpus.__dict__, before)
        edge = result["connections_to_review"][0]
        self.assertEqual((edge["consumer_ref"], edge["need_index"]), ("OLD", 1))
        self.assertEqual(edge["assessment"], "candidate")
        self.assertFalse(edge["consumer_usable"])
        self.assertFalse(edge["evidence"])
        self.assertEqual(corpus.records["OLD"]["status"], "failed")
        self.assertIn("OLD", ids(result["affected_records"]))
        self.assertEqual(ids(result["affected_chains"]), {"CHAIN"})
        self.assertEqual(result["affected_pages"][0]["page_id"], "OLD-PAGE")

    def test_conflicting_and_unknown_candidates_keep_their_conditions(self):
        corpus = Fixture([
            record("NEW", capability={"provides": [spec("ticket")]}),
            record("CONFLICT", capability={"needs": [spec("ticket", "lab-b")]}),
            record("UNKNOWN", capability={"needs": [{"type": "ticket"}]}),
        ])
        result = build_impact(corpus, ["NEW"])
        edges = {row["consumer_ref"]: row for row in result["connections_to_review"]}
        self.assertEqual(edges["CONFLICT"]["compatibility"], "incompatible")
        self.assertEqual(edges["CONFLICT"]["conflicts"][0]["constraint"], "tenant")
        self.assertEqual(edges["UNKNOWN"]["compatibility"], "unknown")
        self.assertTrue(edges["UNKNOWN"]["unknown_conditions"])
        self.assertTrue(all(row["assessment"] == "candidate" for row in edges.values()))

    def test_supplied_global_discovery_does_not_report_unrelated_component(self):
        corpus = Fixture([
            record("A", capability={"provides": [spec("ticket")]}),
            record("B", capability={"needs": [spec("ticket")]}),
            record("C", capability={"provides": [spec("account")]}),
            record("D", capability={"needs": [spec("account")]}),
        ])
        found = discover(corpus)
        found["paths"] = [{"record_refs": ["A", "B"]}, {"record_refs": ["C", "D"]}]
        result = build_impact(corpus, ["A"], discovery=found)
        self.assertEqual(len(result["connections_to_review"]), 1)
        self.assertEqual(ids(result["affected_records"]), {"A", "B"})
        self.assertEqual([row["record_refs"] for row in result["affected_paths"]], [["A", "B"]])

    def test_multiple_changed_sources_and_cycles_are_aggregated_once(self):
        corpus = Fixture([
            record("A", requires=["B"]), record("B", requires=["A"]),
            record("CHAIN", kind="Chain", steps=["A", "B"]),
        ])
        result = build_impact(corpus, ["O-A", "O-B", "O-A"], discovery={})
        self.assertEqual(len(result["affected_records"]), 2)
        self.assertEqual(result["affected_chains"][0]["source_refs"], ["O-A", "O-B"])
        self.assertEqual(result["changed_refs"], ["O-A", "O-B"])


if __name__ == "__main__":
    unittest.main()
