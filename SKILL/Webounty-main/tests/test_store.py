"""Offline checks for the author's publication boundary, without target requests."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from rag import Corpus, RetrievalError, dependencies
from discovery import discover
from store import audit, publish


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "run"
        (self.root / "wiki").mkdir(parents=True)
        self.run_id = "RUN-TEST"
        self.write("state.json", {"run_id": self.run_id, "revision": 1, "session_id": "test",
                   "records": {"G-1": {"id": "G-1", "kind": "Goal", "revision": 1,
                                "status": "active", "summary": "Local example", "subject_refs": []}},
                   "entities": {}, "observations": {}, "artifacts": {}})
        self.write("wiki/manifest.json", {"run_id": self.run_id, "pages": []})

    def write(self, relative, value):
        (self.root / relative).write_text(json.dumps(value), encoding="utf-8")

    def read(self, relative):
        return json.loads((self.root / relative).read_text())

    def publish(self, batch):
        return publish(self.root, self.run_id, batch)

    def observation(self, oid, subjects=()):
        return {"id": oid, "summary": oid + " observation", "subject_refs": list(subjects),
                "content": {"response": {"status": 200, "data": oid}, "environment": "test"}}

    def basic(self):
        return {"entities": [{"id": "E-1", "kind": "endpoint", "title": "Upload"}],
                "observations": [self.observation("O-1", ["E-1"])],
                "records": [{"id": "F-1", "kind": "Fact", "status": "observed",
                             "summary": "An observed upload result", "subject_refs": ["E-1"],
                             "observation_refs": ["O-1"]}]}

    def chain_batch(self):
        return {"observations": [self.observation(oid) for oid in ("O-A", "O-B", "O-END")],
                "records": [
                    {"id": "C-A", "kind": "Capability", "status": "observed", "observation_refs": ["O-A"],
                     "summary": "Produces an example object", "capability": {"provides": [{"type": "object", "constraints": {"environment": "test"}}]}},
                    {"id": "C-B", "kind": "Capability", "status": "observed", "observation_refs": ["O-B"],
                     "summary": "Consumes an example object", "capability": {"needs": [{"type": "object", "constraints": {"environment": "test"}}]}},
                    {"id": "CH-1", "kind": "Chain", "status": "verified", "summary": "Author-verified example",
                     "steps": ["C-A", "C-B"], "observation_refs": ["O-END"], "conditions": {"environment": "test"},
                     "links": [{"producer_ref": "C-A", "consumer_ref": "C-B", "provide_index": 0, "need_index": 0,
                                "assessment": "verified", "evidence_refs": ["O-A", "O-B"], "conditions": {"environment": "test"}}]}]}

    def test_publish_empty_run_to_readable_wiki_and_raw_evidence(self):
        result = self.publish(self.basic())
        self.assertEqual(result["state_revision"], 2)
        self.assertEqual(result["changed_page_ids"], ["WK-F-1"])
        corpus = Corpus(self.root, self.run_id)
        package, issues = corpus.package(block_keys=["WK-F-1/B-F-1"])
        self.assertIsNotNone(package)
        self.assertEqual(package["observations"][0]["raw"]["response"]["data"], "O-1")
        self.assertFalse(issues)
        page = corpus.pages["WK-F-1"]
        self.assertEqual(page["content_hash"], hashlib.sha256((self.root / page["path"]).read_bytes()).hexdigest())
        self.assertIn("../../evidence/O-1.jsonl", (self.root / page["path"]).read_text())

    def test_duplicate_observation_rejected_without_partial_write(self):
        self.publish(self.basic())
        before = (self.root / "state.json").read_bytes()
        with self.assertRaises(RetrievalError):
            self.publish({"observations": [self.observation("O-2"), self.observation("O-1")]})
        self.assertEqual((self.root / "state.json").read_bytes(), before)
        self.assertFalse((self.root / "evidence/O-2.jsonl").exists())

    def test_invalid_reference_rejected_before_any_evidence_write(self):
        batch = self.basic()
        batch["records"][0]["observation_refs"] = ["O-MISSING"]
        with self.assertRaises(RetrievalError):
            self.publish(batch)
        self.assertFalse((self.root / "evidence/O-1.jsonl").exists())
        self.assertEqual(self.read("state.json")["revision"], 1)

    def test_source_file_is_copied_and_referenced(self):
        source = Path(self.temp.name) / "capture.txt"
        original = b"HTTP/1.1 200 OK\r\n\r\noriginal response"
        source.write_bytes(original)
        batch = self.basic()
        batch["observations"][0]["source_path"] = str(source)
        self.publish(batch)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual((self.root / "evidence/O-1.source").read_bytes(), original)
        corpus = Corpus(self.root, self.run_id)
        package, _ = corpus.package(record_ids=["F-1"])
        sources = {artifact["id"]: artifact for artifact in package["artifacts"]}
        self.assertEqual(sources["SRC-O-1"]["content"].encode(), original)

    def test_explicit_page_has_source_closure_and_rejects_broken_knowledge(self):
        batch = self.basic()
        batch["pages"] = [{"id": "P-1", "kind": "question", "title": "Result",
                           "record_refs": ["F-1"], "blocks": [{"id": "B-1", "title": "Observed result",
                           "text": "A narrow observation.", "knowledge": {"supporting_refs": ["F-MISSING"]}}]}]
        with self.assertRaises(RetrievalError):
            self.publish(batch)
        self.assertFalse((self.root / "evidence/O-1.jsonl").exists())

    def test_new_related_material_is_not_automatically_marked_read(self):
        self.publish(self.basic())
        self.publish({"observations": [self.observation("O-2", ["E-1"])],
                      "records": [{"id": "F-2", "kind": "Fact", "subject_refs": ["E-1"],
                                   "observation_refs": ["O-2"], "summary": "New related observation"}]})
        corpus = Corpus(self.root, self.run_id)
        checked = {item["id"] for item in corpus.pages["WK-F-1"]["checked_candidates"]}
        self.assertNotIn("F-2", checked)
        fresh = corpus.page_check("WK-F-1")
        self.assertEqual(fresh["status"], "review_required")
        self.assertIn("F-2", {item["id"] for item in fresh["new_candidates"]})

    def test_record_revision_refreshes_main_page_but_not_other_pages(self):
        batch = self.basic()
        batch["pages"] = [{"id": "P-LINK", "kind": "flow", "title": "Dependent flow", "record_refs": [],
                           "blocks": [{"id": "B-LINK", "title": "Dependency", "text": "Uses the observation.", "source_refs": ["F-1"]}]}]
        self.publish(batch)
        before = (self.root / "wiki/pages/P-LINK.md").read_bytes()
        result = self.publish({"records": [{"id": "F-1", "summary": "Revised narrow interpretation", "change_reason": "User clarified the claim"}]})
        self.assertEqual(self.read("state.json")["records"]["F-1"]["revision"], 2)
        self.assertEqual((self.root / "wiki/pages/P-LINK.md").read_bytes(), before)
        self.assertEqual(result["changed_page_ids"], ["WK-F-1"])
        check = Corpus(self.root, self.run_id).page_check("P-LINK")
        self.assertIn("stale_source", {issue["code"] for issue in check["issues"]})

    def test_chain_needs_review_after_dependency_update(self):
        self.publish(self.chain_batch())
        result = self.publish({"records": [{"id": "C-A", "summary": "Narrower output scope"}]})
        self.assertEqual(result["needs_review_chain_ids"], ["CH-1"])
        self.assertEqual(self.read("state.json")["records"]["CH-1"]["status"], "needs_review")
        self.assertEqual(Corpus(self.root, self.run_id).page_check("WK-CH-1")["status"], "review_required")

    def test_new_explicit_counterevidence_marks_chain_for_review(self):
        self.publish(self.chain_batch())
        result = self.publish({"observations": [self.observation("O-NEW")],
                               "records": [{"id": "F-NEW", "kind": "Fact", "observation_refs": ["O-NEW"],
                                            "contradicts": ["CH-1"], "summary": "A contrary observation"}]})
        self.assertEqual(result["needs_review_chain_ids"], ["CH-1"])
        corpus = Corpus(self.root, self.run_id)
        package, _ = corpus.package(record_ids=["CH-1"])
        self.assertIn("F-NEW", {row["id"] for row in package["records"]})

    def test_verified_chain_requires_final_and_two_sided_evidence(self):
        batch = self.chain_batch()
        batch["records"][-1]["observation_refs"] = []
        with self.assertRaises(RetrievalError):
            self.publish(batch)
        self.assertFalse((self.root / "evidence/O-A.jsonl").exists())
        batch = self.chain_batch()
        batch["records"][-1]["links"][0]["evidence_refs"] = ["O-A"]
        with self.assertRaises(RetrievalError):
            self.publish(batch)

    def test_audit_keeps_authored_verification_distinct_from_proof(self):
        self.publish(self.chain_batch())
        result = audit(self.root, self.run_id)
        self.assertEqual(result["chains"], [{"id": "CH-1", "status": "verified", "claims_verified": False}])

    def test_authored_main_page_is_preserved_for_explicit_revision(self):
        batch = self.basic()
        batch["pages"] = [{"id": "MY-PAGE", "kind": "capability", "title": "Author's explanation",
                           "record_refs": ["F-1"], "blocks": [{"id": "B-OWN", "title": "Meaning",
                           "text": "This text contains the author's conditional interpretation."}]}]
        self.publish(batch)
        before = (self.root / "wiki/pages/MY-PAGE.md").read_bytes()
        result = self.publish({"records": [{"id": "F-1", "summary": "An updated observation interpretation"}]})
        self.assertEqual(result["changed_page_ids"], [])
        self.assertFalse((self.root / "wiki/pages/WK-F-1.md").exists())
        self.assertEqual((self.root / "wiki/pages/MY-PAGE.md").read_bytes(), before)
        self.assertEqual(Corpus(self.root, self.run_id).page_check("MY-PAGE")["status"], "review_required")

    def test_changed_entity_invalidates_a_chain_using_it(self):
        batch = self.chain_batch()
        batch["entities"] = [{"id": "ACTOR", "kind": "actor", "title": "Test identity"}]
        batch["records"][0]["subject_refs"] = ["ACTOR"]
        self.publish(batch)
        result = self.publish({"entities": [{"id": "ACTOR", "title": "Changed identity conditions"}]})
        self.assertEqual(result["needs_review_chain_ids"], ["CH-1"])

    def test_binary_source_and_observation_only_batch_are_supported(self):
        source = Path(self.temp.name) / "capture.bin"
        source.write_bytes(b"\xff\x00\xfe")
        observation = self.observation("O-BIN")
        observation["source_path"] = str(source)
        self.publish({"observations": [observation]})
        corpus = Corpus(self.root, self.run_id)
        self.assertEqual(corpus.observation("O-BIN")["status"], "ready")
        self.assertEqual(corpus.artifact("SRC-O-BIN")["data"], b"\xff\x00\xfe")

    def test_verified_multi_input_graph_and_multiple_output_bindings(self):
        batch = self.chain_batch()
        producer, consumer, chain = batch["records"]
        producer["capability"]["provides"].append({"type": "permission", "constraints": {"environment": "test"}})
        consumer["capability"]["needs"].extend([
            {"type": "permission", "constraints": {"environment": "test"}},
            {"type": "metadata", "constraints": {"environment": "test"}}])
        other = {"id": "C-OTHER", "kind": "Capability", "status": "observed", "observation_refs": ["O-OTHER"],
                 "capability": {"provides": [{"type": "metadata", "constraints": {"environment": "test"}}]}}
        batch["records"].insert(1, other)
        batch["observations"].append(self.observation("O-OTHER"))
        chain["steps"] = ["C-A", "C-OTHER", "C-B"]
        chain["links"].extend([
            {"producer_ref": "C-A", "consumer_ref": "C-B", "provide_index": 1, "need_index": 1,
             "assessment": "verified", "evidence_refs": ["O-A", "O-B"], "conditions": {"environment": "test"}},
            {"producer_ref": "C-OTHER", "consumer_ref": "C-B", "provide_index": 0, "need_index": 2,
             "assessment": "verified", "evidence_refs": ["O-OTHER", "O-B"], "conditions": {"environment": "test"}}])
        self.publish(batch)
        self.assertEqual(self.read("state.json")["records"]["CH-1"]["status"], "verified")
        self.assertIn("pages/WK-CH-1.md", (self.root / "wiki/index.md").read_text())
        self.assertIn("能力", (self.root / "wiki/index.md").read_text())

    def test_verified_chain_rejects_uncovered_need_and_known_conflicts(self):
        batch = self.chain_batch()
        batch["records"][1]["capability"]["needs"].append({"type": "missing", "constraints": {"environment": "test"}})
        with self.assertRaisesRegex(RetrievalError, "unprovided input"):
            self.publish(batch)
        batch = self.chain_batch()
        batch["records"][1]["capability"]["needs"][0]["constraints"]["environment"] = "other"
        with self.assertRaisesRegex(RetrievalError, "conflicting environment"):
            self.publish(batch)
        batch = self.chain_batch()
        batch["records"][-1]["links"][0]["conditions"]["environment"] = "other"
        with self.assertRaisesRegex(RetrievalError, "conflicting environment"):
            self.publish(batch)
        batch = self.chain_batch()
        batch["records"][1]["capability"]["needs"][0]["type"] = "unrelated-capability"
        with self.assertRaisesRegex(RetrievalError, "matching capability types"):
            self.publish(batch)
        self.assertEqual(self.read("state.json")["revision"], 1)

    def test_changed_capability_can_invalidate_an_old_verified_binding(self):
        self.publish(self.chain_batch())
        result = self.publish({"records": [{"id": "C-A", "capability": {"provides": []},
                                            "summary": "This capability was retracted."}]})
        self.assertEqual(result["needs_review_chain_ids"], ["CH-1"])
        chain = self.read("state.json")["records"]["CH-1"]
        self.assertEqual(chain["status"], "needs_review")
        self.assertEqual(chain["links"][0]["assessment"], "verified")
        self.assertEqual(audit(self.root, self.run_id)["chains"][0]["status"], "needs_review")

    def test_discovered_normalized_type_can_be_published_as_verified(self):
        batch = self.chain_batch()
        batch["records"][0]["capability"]["provides"][0]["type"] = "export_job_id"
        batch["records"][1]["capability"]["needs"][0]["type"] = "EXPORT-JOB-ID"
        chain = batch["records"].pop()
        self.publish(batch)
        discovery = discover(Corpus(self.root, self.run_id), anchors=["C-A"])
        edge = next(item for item in discovery["candidates"]
                    if item["producer_ref"] == "C-A" and item["consumer_ref"] == "C-B")
        self.assertEqual(edge["compatibility"], "compatible")
        self.publish({"records": [chain]})
        self.assertEqual(self.read("state.json")["records"]["CH-1"]["status"], "verified")

    def test_optional_reasoning_preserves_counterevidence_and_unverified_impact(self):
        batch = self.basic()
        row = batch["records"][0]
        row.update({"kind": "Finding", "status": "candidate", "hypothesis": "The response may expose another object's content.",
                    "actual_result": {"observed": "The request was rejected.", "content_read": False},
                    "controls": [{"note": "The legitimate baseline also failed.", "validity": "invalid", "observation_refs": ["O-1"]}],
                    "counterevidence": "The response contains no object content.",
                    "unresolved_preconditions": ["A valid baseline is still missing."],
                    "impact": {"status": "unknown", "possible": "Cross-object disclosure", "confirmed": False,
                               "limitation": "No disclosure has been observed."},
                    "retest": {"status": "inconclusive", "normal_control_passed": False},
                    "reopen_when": ["A valid identity and baseline become available."]})
        self.publish(batch)
        text = (self.root / "wiki/pages/WK-F-1.md").read_text()
        for required in (row["hypothesis"], "content_read：false", "validity：invalid", row["counterevidence"],
                         "A valid baseline is still missing.", "confirmed：false", "No disclosure has been observed.",
                         "normal_control_passed：false", row["reopen_when"][0], "影响验证状态：未验证"):
            self.assertIn(required, text)
        self.assertIn("[O-1](../../evidence/O-1.jsonl)", text)
        self.assertNotIn('"data":"O-1"', text)
        self.assertEqual(self.read("state.json")["records"]["F-1"]["status"], "candidate")

    def test_index_groups_records_and_negative_results_without_promoting_failures(self):
        self.publish(self.basic())
        self.publish({"records": [
            {"id": "S-1", "kind": "Step", "status": "blocked", "summary": "Missing a required observation."},
            {"id": "N-1", "kind": "Finding", "status": "candidate", "summary": "An unverified lead.", "observation_refs": ["O-1"]},
            {"id": "N-NEG", "kind": "Finding", "status": "refuted", "summary": "This narrow claim was refuted.",
             "observation_refs": ["O-1"], "reopen_when": ["The deployment changes."]},
            {"id": "S-FAILED", "kind": "Step", "status": "failed", "summary": "The observer could not run."}]})
        index = (self.root / "wiki/index.md").read_text()
        for heading in ("当前目标", "活动问题", "发现", "负结果与关闭命题", "能力", "链与阻断"):
            self.assertIn("## " + heading, index)
        negative = index.split("## 负结果与关闭命题\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("WK-N-NEG.md", negative)
        self.assertNotIn("WK-S-FAILED.md", negative)
        self.assertEqual(index.count("[发现 · N-1](pages/WK-N-1.md)"), 1)
        self.assertIn("未验证", index)

    def test_new_correction_is_visible_in_index_without_rewriting_old_claim(self):
        self.publish(self.basic())
        old = (self.root / "wiki/pages/WK-F-1.md").read_bytes()
        self.publish({"observations": [self.observation("O-CORR")],
                      "records": [{"id": "F-CORR", "kind": "Fact", "observation_refs": ["O-CORR"],
                                   "contradicts": ["F-1"], "summary": "A new contrary observation."}]})
        self.assertEqual((self.root / "wiki/pages/WK-F-1.md").read_bytes(), old)
        index = (self.root / "wiki/index.md").read_text()
        original_line = next(line for line in index.splitlines() if line.startswith("- [事实 · F-1]"))
        self.assertIn("页面待复核", original_line)
        self.assertIn("[F-CORR](pages/WK-F-CORR.md)", original_line)
        self.assertEqual(self.read("state.json")["records"]["F-1"]["status"], "observed")

    def test_change_history_preserves_reason_but_does_not_revive_old_support(self):
        self.publish(self.basic())
        self.publish({"observations": [self.observation("O-OLD"), self.observation("O-NOW")],
                      "records": [{"id": "F-OLD", "kind": "Fact", "observation_refs": ["O-OLD"], "summary": "An earlier basis."},
                                  {"id": "F-1", "source_refs": ["F-OLD"], "summary": "An intermediate interpretation.",
                                   "change_reason": "Read an additional source."}]})
        self.publish({"records": [{"id": "F-1", "source_refs": [], "observation_refs": ["O-NOW"],
                                   "summary": "A narrower current interpretation.", "change_reason": "The new observation limits the claim."}]})
        current = self.read("state.json")["records"]["F-1"]
        self.assertEqual(len(current["history"]), 2)
        self.assertEqual(current["history"][0]["record_refs"], ["F-OLD"])
        self.assertEqual(current["history"][1]["previous_summary"], "An intermediate interpretation.")
        self.assertNotIn("F-OLD", dependencies(current))
        package, _ = Corpus(self.root, self.run_id).package(record_ids=["F-1"])
        self.assertNotIn("F-OLD", {row["id"] for row in package["records"]})
        rendered = (self.root / "wiki/pages/WK-F-1.md").read_text()
        self.assertIn("修订记录（历史判断，不作为当前结论）", rendered)
        self.assertIn("The new observation limits the claim.", rendered)
        self.assertIn("An intermediate interpretation.", rendered)


if __name__ == "__main__":
    unittest.main()
