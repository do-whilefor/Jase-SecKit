"""RAG integration contracts using small synthetic, local-only session corpora."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rag import Corpus, RetrievalError, digest, encode, retrieve
from search_index import rank


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "evidence").mkdir()
        (self.root / "wiki").mkdir()
        self.state = {"run_id": "R1", "revision": 1, "session_id": "S1",
                      "records": {}, "observations": {}, "entities": {}, "artifacts": {}}
        self.manifest = {"run_id": "R1", "pages": []}
        for target in ("socket.socket", "socket.create_connection", "urllib.request.urlopen"):
            mock = patch(target, side_effect=AssertionError("retrieval must stay offline"))
            mock.start()
            self.addCleanup(mock.stop)

    def record(self, rid, summary, **fields):
        self.state["records"][rid] = {"id": rid, "revision": 1, "kind": "Question",
                                      "status": "confirmed", "summary": summary,
                                      "subject_refs": [], "observation_refs": [], **fields}

    def observation(self, oid, **content):
        raw = {"observation_id": oid, "run_id": "R1", **content}
        data = (encode(raw) + "\n").encode()
        path = "evidence/" + oid + ".jsonl"
        (self.root / path).write_bytes(data)
        aid = "A-" + oid
        self.state["artifacts"][aid] = {"id": aid, "path": path, "sealed": True,
                                       "kind": "evidence", "sha256": digest(data), "bytes": len(data)}
        self.state["observations"][oid] = {"id": oid, "revision": 1, "artifact_id": aid,
                                           "line": 1, "content_hash": digest(data), "subject_refs": []}

    def save(self):
        (self.root / "state.json").write_text(encode(self.state))
        (self.root / "wiki/manifest.json").write_text(encode(self.manifest))

    def query(self, query="", anchors=(), **options):
        self.save()
        return retrieve(self.root, "R1", query, anchors, **options)

    @staticmethod
    def ids(result):
        return {row["id"] for row in result["records"]}

    @staticmethod
    def spec(name, **constraints):
        return {"type": name, "constraints": constraints}

    def graph(self):
        self.observation("O1", response={"body": "fictional task reference"})
        self.observation("O2", response={"body": "fictional download preconditions"})
        self.record("PRODUCER", "早期发现的任务产物", kind="Capability", observation_refs=["O1"],
                    capability={"provides": [self.spec("task-reference", tenant="lab-a")], "needs": []})
        self.record("CONSUMER", "download the final report", kind="Capability", observation_refs=["O2"],
                    capability={"provides": [], "needs": [self.spec("task-reference", tenant="lab-a")]})

    def test_default_retrieval_has_no_eighty_candidate_or_32000_character_cutoff(self):
        for number in range(105):
            self.record(f"R{number:03}", "retained " + ("detail " * 75))
        result = self.query("retained")
        self.assertEqual(len(self.ids(result)), 105)
        self.assertIsNone(result["budget"]["limit_chars"])
        self.assertGreater(result["budget"]["used_chars"], 32000)
        self.assertEqual(result["budget"]["omitted_units"], 0)
        self.assertEqual(result["budget"]["used_chars"], len(encode(result)))
        self.assertEqual(result["cross_candidates"], [])

    def test_unlimited_and_sufficient_budget_return_identical_complete_packages(self):
        from store import publish

        self.graph()
        self.record("CORRECTION", "review the old production claim", contradicts=["PRODUCER"])
        self.save()
        publish(self.root, "R1", {"pages": [
            {"id": "PROVIDER-PAGE", "kind": "capability", "title": "provider details", "record_refs": ["PRODUCER"]},
            {"id": "CONSUMER-PAGE", "kind": "capability", "title": "download consumer", "record_refs": ["CONSUMER"]},
        ]})
        for candidate_limit in (None, 1):
            with self.subTest(max_candidates=candidate_limit):
                fast = retrieve(self.root, "R1", "download", ["CONSUMER"], max_candidates=candidate_limit)
                limited = retrieve(self.root, "R1", "download", ["CONSUMER"],
                                   max_candidates=candidate_limit, budget_chars=1_000_000)
                self.assertEqual(fast["budget"]["used_chars"], len(encode(fast)))
                self.assertEqual(limited["budget"]["used_chars"], len(encode(limited)))
                self.assertEqual(fast["budget"]["omitted_units"], limited["budget"]["omitted_units"])
                self.assertEqual({key: value for key, value in fast.items() if key != "budget"},
                                 {key: value for key, value in limited.items() if key != "budget"})

    def test_full_session_discovery_runs_before_the_candidate_cutoff(self):
        self.graph()
        result = self.query("download", anchors=["CONSUMER"], max_candidates=1)
        self.assertEqual(self.ids(result), {"CONSUMER"})
        candidates = result["chain_discovery"]["candidates"]
        self.assertTrue(any(row["producer_ref"] == "PRODUCER" and row["consumer_ref"] == "CONSUMER"
                            for row in candidates))
        self.assertTrue(all(row["evidence"] is False for row in candidates))
        self.assertTrue(any(row.get("id") == "PRODUCER" and row["reason"] == "candidate_limit"
                            for row in result["omissions"]))
        expanded = self.query("download", anchors=["CONSUMER"])
        self.assertIn("PRODUCER", self.ids(expanded))
        why = next(row for row in expanded["retrieval_reasons"] if row["id"] == "PRODUCER")
        self.assertIn("capability_relation", {row["kind"] for row in why["reasons"]})

    def test_unclassified_material_does_not_evict_exact_anchor_or_correction(self):
        self.record("TARGET", "first claim", corrected_by=["CORRECTION"])
        self.record("CORRECTION", "the earlier claim was disproved")
        for number in range(150):
            self.record(f"U{number}", "unrelated", classification="unclassified")
        result = self.query(anchors=["TARGET"], budget_chars=6000, max_candidates=1)
        self.assertEqual(self.ids(result), {"TARGET", "CORRECTION"})
        self.assertLessEqual(len(encode(result)), 6000)
        self.assertEqual(result["budget"]["used_chars"], len(encode(result)))
        self.assertGreaterEqual(result["budget"]["omitted_units"], 150)
        self.assertEqual(result["status"], "review_required")

    def test_chain_package_includes_each_step_edge_and_final_evidence(self):
        self.graph()
        self.observation("FINAL", response={"synthetic_flag": "local-demo"})
        source = b"independent raw edge transcript\n"
        (self.root / "evidence/edge.txt").write_bytes(source)
        self.state["artifacts"]["SRC-EDGE"] = {"id": "SRC-EDGE", "path": "evidence/edge.txt",
            "sealed": True, "kind": "evidence", "sha256": digest(source), "bytes": len(source)}
        self.observation("EDGE", response={"connected": True}, source_artifact={
            "artifact_id": "SRC-EDGE", "path": "evidence/edge.txt", "sha256": digest(source)})
        self.state["observations"]["EDGE"]["source_artifact_id"] = "SRC-EDGE"
        self.record("CHAIN", "demonstration", kind="Chain", status="verified", steps=["PRODUCER", "CONSUMER"],
                    observation_refs=["FINAL"], links=[{"producer_ref": "PRODUCER", "consumer_ref": "CONSUMER",
                    "provide_index": 0, "need_index": 0, "assessment": "verified", "evidence_refs": ["EDGE"]}])
        self.save()
        package, issues = Corpus(self.root, "R1").package(record_ids=["CHAIN"])
        self.assertIsNotNone(package)
        self.assertFalse(issues)
        self.assertEqual({row["id"] for row in package["records"]}, {"CHAIN", "PRODUCER", "CONSUMER"})
        self.assertEqual({row["id"] for row in package["observations"]}, {"O1", "O2", "EDGE", "FINAL"})
        self.assertIn("SRC-EDGE", {row["id"] for row in package["artifacts"]})

    def test_tampered_observation_is_not_available_as_raw_evidence(self):
        self.graph()
        self.save()
        (self.root / "evidence/O1.jsonl").write_text("tampered\n")
        result = retrieve(self.root, "R1", "", ["PRODUCER"])
        observed = next(row for row in result["observations"] if row["id"] == "O1")
        self.assertEqual(observed["status"], "unavailable")
        self.assertIsNone(observed["raw"])
        self.assertNotEqual(result["status"], "ready")
        self.assertTrue(all(row["compatibility"] != "compatible" for row in result["chain_discovery"]["candidates"]))

    def test_imported_source_tampering_invalidates_observation_and_discovery(self):
        self.graph()
        raw = b"original source evidence\n"
        path = self.root / "evidence/imported.txt"
        path.write_bytes(raw)
        self.state["artifacts"]["IMPORTED"] = {"id": "IMPORTED", "path": "evidence/imported.txt",
            "sealed": True, "kind": "evidence", "sha256": digest(raw), "bytes": len(raw)}
        self.state["observations"]["O1"]["source_artifact_id"] = "IMPORTED"
        self.save()
        path.write_text("changed source\n")
        result = retrieve(self.root, "R1", "download", ["CONSUMER"])
        observed = next(row for row in result["observations"] if row["id"] == "O1")
        self.assertEqual(observed["status"], "unavailable")
        self.assertIsNone(observed["raw"])
        self.assertTrue(all(row["compatibility"] != "compatible" for row in result["chain_discovery"]["candidates"]))

    def test_observation_pair_comparison_is_explicitly_enabled(self):
        self.state["entities"]["ENDPOINT"] = {"id": "ENDPOINT", "kind": "endpoint", "revision": 1}
        for oid, actor in (("LEFT", "actor-a"), ("RIGHT", "actor-b")):
            self.observation(oid, actor_ref=actor, request={"url": "/demo", "method": "GET"}, response={"ok": True})
            self.state["observations"][oid]["subject_refs"] = ["ENDPOINT"]
            self.record("REC-" + oid, "comparison", observation_refs=[oid])
        result = self.query("comparison", cross_limit=2)
        self.assertEqual(len(result["cross_candidates"]), 1)
        self.assertEqual(result["cross_candidates"][0]["relation"], "same_request_input")
        self.assertIn("actor_ref", result["cross_candidates"][0]["changed_axes"])

    def test_changed_snapshot_clears_graph_and_all_usable_evidence(self):
        self.graph()
        self.save()
        with patch.object(Corpus, "stable", return_value=False):
            result = retrieve(self.root, "R1", "download", ["CONSUMER"])
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["records"])
        self.assertFalse(result["chain_discovery"]["candidates"])
        self.assertTrue(any(row["code"] == "snapshot_changed" for row in result["gaps"]))

    def test_explicit_budget_never_slices_an_observation_body(self):
        self.observation("BIG", response={"body": "payload " * 2000})
        self.record("BIGREC", "large source", observation_refs=["BIG"])
        result = self.query(anchors=["BIGREC"], budget_chars=2048)
        self.assertEqual(result["observations"], [])
        self.assertNotIn("BIGREC", self.ids(result))
        self.assertLessEqual(len(encode(result)), 2048)
        self.assertGreater(result["budget"]["omitted_units"], 0)
        self.assertTrue(any(row["code"] == "budget_exhausted" for row in result["gaps"]))

    def test_exact_alias_boundaries_and_chinese_lexical_reason(self):
        self.record("ADMIN", "special user", aliases=["admin"])
        self.record("ZH", "任务查询报告业务拒绝")
        self.save()
        corpus = Corpus(self.root, "R1")
        ranked, _, exact, why = rank(corpus, "administrator", [], with_exact=True, with_reasons=True)
        self.assertNotIn(("record", "ADMIN"), exact)
        ranked, _, exact, why = rank(corpus, "如何解释业务拒绝响应", [], with_exact=True, with_reasons=True)
        self.assertEqual(ranked[0], ("record", "ZH"))
        self.assertEqual(why[("record", "ZH")][0]["kind"], "lexical")
        result = self.query("", anchors=["ADMIN"])
        entry = next(row for row in result["retrieval_reasons"] if row["id"] == "ADMIN")
        self.assertEqual(entry["reasons"][0]["kind"], "exact_anchor")

    def test_foreign_run_is_rejected(self):
        self.save()
        with self.assertRaises(RetrievalError):
            retrieve(self.root, "OTHER", "query")


if __name__ == "__main__":
    unittest.main()
