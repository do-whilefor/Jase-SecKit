"""Local evidence comparisons, including misleading HTTP/timing signals."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from compare_observations import compare
from rag import Corpus, RetrievalError
from store import publish


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "run"
        (self.root / "wiki").mkdir(parents=True)
        self.run_id = "RUN-COMPARE"
        state = {"run_id": self.run_id, "revision": 1, "session_id": "comparison-test",
                 "records": {}, "entities": {}, "observations": {}, "artifacts": {}}
        (self.root / "state.json").write_text(json.dumps(state), encoding="utf-8")
        (self.root / "wiki/manifest.json").write_text(
            json.dumps({"run_id": self.run_id, "pages": []}), encoding="utf-8")

    def observation(self, oid, body, **metadata):
        return {"id": oid, "summary": "Fictional local response", "content": {
            "actor_ref": "E-A", "environment": "lab-v1", "session_generation": "1",
            "request": {"method": "POST", "url": "https://training.invalid/operation",
                        "body": {"object_id": "OBJ-1"}},
            "response": {"status": 200, "body": body}, **metadata}}

    def corpus(self, *observations):
        publish(self.root, self.run_id, {"observations": list(observations)})
        return Corpus(self.root, self.run_id)

    def test_same_http_code_exposes_actual_business_difference_without_verdict(self):
        corpus = self.corpus(self.observation("O-A", {"status": "denied"}),
                             self.observation("O-B", {"status": "accepted"}))
        result = compare(corpus, "O-A", "O-B", ["response.body.status"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["assessment"], "comparison_only")
        self.assertTrue(result["response"]["status"]["equal"])
        self.assertEqual(result["selected_fields"][0]["right"]["value"], "accepted")
        self.assertEqual(result["response"]["body"]["changed_paths"], ["/response/body/status"])
        self.assertIn("business_outcome_not_established", {g["code"] for g in result["gaps"]})
        self.assertEqual(result["observation_refs"], ["O-A", "O-B"])
        self.assertEqual(result["sources"]["left"]["provenance"]["path"], "evidence/O-A.jsonl")

    def test_status_transition_does_not_certify_a_fix(self):
        after = self.observation("O-B", {"status": "rejected"})
        after["content"]["response"]["status"] = 403
        result = compare(self.corpus(self.observation("O-A", {"status": "accepted"}), after), "O-A", "O-B")
        self.assertFalse(result["response"]["status"]["equal"])
        self.assertEqual(result["assessment"], "comparison_only")
        self.assertIn("controls_not_established", {g["code"] for g in result["gaps"]})

    def test_timing_noise_with_equal_body_is_visible_without_differential_verdict(self):
        first = self.observation("O-A", "same error", time_total=0.10)
        second = self.observation("O-B", "same error", time_total=0.11)
        result = compare(self.corpus(first, second), "O-A", "O-B")
        self.assertTrue(result["response"]["body"]["equal"])
        self.assertEqual(result["response"]["body"]["changed_paths"], [])
        self.assertEqual(result["other_changed_paths"], ["/time_total"])
        self.assertTrue(any("内容相同" in note for note in result["notes"]))
        self.assertEqual(result["assessment"], "comparison_only")

    def test_identity_conditions_and_request_changes_are_kept_separate(self):
        first = self.observation("O-A", {"ok": False}, tenant_ref="E-T1", target_version="1")
        second = self.observation("O-B", {"ok": True}, actor_ref="E-B", tenant_ref="E-T2",
                                  environment="lab-v2", target_version="2", session_generation="2")
        second["content"]["request"]["body"]["object_id"] = "OBJ-2"
        result = compare(self.corpus(first, second), "O-A", "O-B")
        self.assertEqual(result["identity"]["changed_paths"], ["/actor_ref", "/tenant_ref"])
        self.assertEqual(result["conditions"]["changed_paths"],
                         ["/environment", "/session_generation", "/target_version"])
        self.assertEqual(result["request"]["changed_paths"], ["/request/body/object_id"])
        self.assertFalse(result["request"]["equal"])

    def test_missing_identity_is_not_inferred_from_request_or_subjects(self):
        first, second = self.observation("O-A", {}), self.observation("O-B", {})
        for obs in (first, second):
            del obs["content"]["actor_ref"]
            del obs["content"]["environment"]
        result = compare(self.corpus(first, second), "O-A", "O-B")
        self.assertNotIn("actor_ref", result["identity"]["left"])
        self.assertEqual([g["fields"] for g in result["gaps"] if g["code"] == "missing_context"],
                         [["actor_ref", "environment"], ["actor_ref", "environment"]])

    def test_missing_null_boolean_and_number_remain_distinguishable(self):
        result = compare(self.corpus(self.observation("O-A", {"flag": True}),
                                     self.observation("O-B", {"flag": 1, "detail": None})),
                         "O-A", "O-B", ["response.body.flag", "response.body.detail", "response.body.unknown"])
        flag, detail, absent = result["selected_fields"]
        self.assertFalse(flag["equal"])
        self.assertEqual(detail["left"], {"present": False})
        self.assertEqual(detail["right"], {"present": True, "value": None})
        self.assertFalse(detail["equal"])
        self.assertIsNone(absent["equal"])

    def test_large_body_is_not_copied_or_semantically_truncated(self):
        body = "长响应" * 20000
        result = compare(self.corpus(self.observation("O-A", body), self.observation("O-B", body + "x")),
                         "O-A", "O-B", ["response.body"])
        summary = result["response"]["body"]["left"]
        self.assertEqual(summary["byte_length"], len(body.encode("utf-8")))
        self.assertEqual(summary["sha256"], hashlib.sha256(body.encode("utf-8")).hexdigest())
        self.assertNotIn(body, json.dumps(result, ensure_ascii=False))
        self.assertNotIn("value", result["selected_fields"][0]["left"])
        self.assertEqual(result["response"]["body"]["changed_paths"], ["/response/body"])

    def test_objects_are_canonicalized_and_array_paths_are_precise(self):
        a = {"rows": [{"a/b~c": 1}], "status": "same"}
        b = {"status": "same", "rows": [{"a/b~c": 2}]}
        result = compare(self.corpus(self.observation("O-A", a), self.observation("O-B", b)),
                         "O-A", "O-B", ["response.body.rows.0.a/b~c", "response.body.rows"])
        self.assertEqual(result["response"]["body"]["changed_paths"], ["/response/body/rows/0/a~1b~0c"])
        self.assertEqual(result["selected_fields"][0]["right"]["value"], 2)
        self.assertTrue(result["selected_fields"][1]["right"]["value_omitted"])
        self.assertEqual(result["response"]["body"]["right"]["encoding"], "canonical-json")

    def test_missing_http_data_is_reported_without_invented_response(self):
        first = {"id": "O-A", "summary": "Local source note", "content": {"line": 12}}
        result = compare(self.corpus(first, self.observation("O-B", None)), "O-A", "O-B")
        self.assertEqual(result["response"]["body"]["left"], {"present": False})
        self.assertEqual(result["response"]["body"]["right"]["type"], "null")
        gap = next(g for g in result["gaps"] if g["code"] == "missing_http_observation")
        self.assertEqual(gap["fields"], ["request", "response.status", "response.body"])

    def test_original_source_tampering_disables_content_comparison(self):
        source = self.root / "capture.txt"
        source.write_text("original capture", encoding="utf-8")
        first = self.observation("O-A", {"ok": True})
        first["source_path"] = str(source)
        self.corpus(first, self.observation("O-B", {"ok": False}))
        (self.root / "evidence/O-A.source").write_text("edited capture", encoding="utf-8")
        result = compare(Corpus(self.root, self.run_id), "O-A", "O-B")
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("response", result)
        self.assertEqual(result["sources"]["left"]["source_artifact_id"], "SRC-O-A")
        self.assertTrue(result["sources"]["left"]["issues"])

    def test_only_requested_observations_are_read_and_no_files_change(self):
        corpus = self.corpus(*(self.observation(oid, oid) for oid in ("O-A", "O-B", "O-UNUSED")))
        files = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with patch.object(corpus, "observation", wraps=corpus.observation) as reader:
            compare(corpus, "O-A", "O-B")
        self.assertEqual([call.args for call in reader.call_args_list], [("O-A",), ("O-B",)])
        self.assertNotIn("ART-O-UNUSED", corpus.art_cache)
        self.assertEqual(files, {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_invalid_ids_fields_and_http_schema_raise_retrieval_error(self):
        broken = self.observation("O-B", {})
        broken["content"]["response"] = "not a response object"
        corpus = self.corpus(self.observation("O-A", {}), broken)
        for left, right, fields in (("O-A", "O-MISSING", ()),
                                    ("O-A", "O-A", "response.body"),
                                    ("O-A", "O-A", ["response..body"]),
                                    ("O-A", "O-A", [None]),
                                    ("O-A", "O-B", ())):
            with self.subTest(left=left, right=right, fields=fields), self.assertRaises(RetrievalError):
                compare(corpus, left, right, fields)


if __name__ == "__main__":
    unittest.main()
