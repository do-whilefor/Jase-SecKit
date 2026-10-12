"""Business-level evidence gates and safe lead rendering, using synthetic data."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_check_report import SCRIPT, checker, synthetic_documents
from render_report import render_report


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.case, self.fields, self.profile, self.data, self.ref = synthetic_documents()

    def check(self):
        return checker.check_report(self.manifest, self.case, self.fields, self.profile)

    def render(self, verify_files=False):
        return render_report(self.manifest, self.case, self.fields, self.profile, verify_files=verify_files)

    def codes(self, review):
        return {issue["code"] for issue in review["issues"]}

    def test_legacy_cases_keep_platform_draft_and_get_two_specific_reminders(self):
        del self.case["triage"], self.case["cvss31"]
        before = copy.deepcopy((self.manifest, self.case, self.fields, self.profile))
        review = self.check()
        self.assertEqual({"triage_pending", "cvss_pending"}, self.codes(review))
        self.assertEqual({"status": "pending", "passed": False, "explicit": False}, review["triage"])
        self.assertIsNone(review["cvss31"])
        report = self.render()["report.md"]
        self.assertIn("Synthetic draft", report)
        self.assertIn("## 平台字段", report)
        self.assertIn("未筛选的旧版草稿", report)
        self.assertEqual(before, (self.manifest, self.case, self.fields, self.profile))

    def test_pending_and_lead_have_no_score_or_required_platform_fields(self):
        for status in ("pending", "lead"):
            with self.subTest(status=status):
                self.case["triage"].update(status=status, basis={key: [] for key in ("boundary", "reproducibility", "impact")})
                self.case["cvss31"] = {"vector": None, "rationale": {}, "reason": "Need a recorded response and control case."}
                self.fields["fields"] = {}
                self.profile["groups"] = {"packets": {"label": "Requests", "min_items": 2}}
                review = self.check()
                self.assertFalse(review["triage"]["passed"])
                self.assertIsNone(review["cvss31"])
                self.assertFalse({"required_field_missing", "group_min_items"} & self.codes(review))
                self.assertEqual(status != "lead", "cvss_pending" in self.codes(review))
                report = self.render()["report.md"]
                self.assertTrue(report.startswith("# 漏洞线索记录\n"))
                self.assertIn("## 待补证", report)
                self.assertNotIn("## 平台字段", report)

    def test_lead_still_checks_supplied_field_values(self):
        self.case["triage"]["status"] = "lead"
        self.fields["fields"]["title"]["value"] = True
        self.assertIn("field_value_type", self.codes(self.check()))
        self.fields["fields"]["title"]["value"] = None
        self.fields["fields"]["alien"] = {"value": "unknown", "status": "supported", "evidence_refs": [self.ref]}
        self.assertIn("unknown_field", self.codes(self.check()))
        self.profile["fields"].append({"id": "conditional", "label": "Conditional", "kind": "select", "options": ["yes"],
                                       "when": {"field": "title", "equals": "Active title"}})
        self.fields["fields"]["title"]["value"] = "Inactive title"
        self.fields["fields"]["conditional"] = {"value": "illegal", "status": "supported", "evidence_refs": [self.ref]}
        self.assertTrue({"inactive_field_value", "invalid_option"} <= self.codes(self.check()))

    def test_missing_any_of_three_basis_categories_cannot_pass(self):
        original = copy.deepcopy(self.case["triage"]["basis"])
        for category in original:
            for value in (None, []):
                with self.subTest(category=category, value=value):
                    self.case["triage"]["basis"] = copy.deepcopy(original)
                    if value is None:
                        del self.case["triage"]["basis"][category]
                    else:
                        self.case["triage"]["basis"][category] = value
                    review = self.check()
                    self.assertFalse(review["triage"]["passed"])
                    self.assertIsNone(review["cvss31"])
                    self.assertIn("triage_not_supported", self.codes(review))

    def test_all_five_claim_collections_can_provide_basis(self):
        claim = self.case["observed_results"].pop()
        for collection in checker.CLAIM_COLLECTIONS:
            with self.subTest(collection=collection):
                self.case[collection] = [claim]
                self.assertTrue(self.check()["triage"]["passed"])
                self.case[collection] = []

    def test_unknown_ambiguous_and_nonobserved_claims_cannot_pass(self):
        original = copy.deepcopy(self.case)
        for mutation in ("unknown", "duplicate", "inferred", "unverified", "conflicted", "empty"):
            with self.subTest(mutation=mutation):
                self.case = copy.deepcopy(original)
                if mutation == "unknown":
                    self.case["triage"]["basis"]["boundary"] = ["MISSING"]
                elif mutation == "duplicate":
                    self.case["steps"] = copy.deepcopy(self.case["observed_results"])
                elif mutation == "empty":
                    self.case["observed_results"][0]["text"] = " "
                else:
                    self.case["observed_results"][0]["verification"] = mutation
                review = self.check()
                self.assertFalse(review["triage"]["passed"])
                self.assertIsNone(review["cvss31"])

    def test_missing_unknown_unlocated_and_unreviewed_evidence_cannot_pass(self):
        original = copy.deepcopy(self.case)
        for mutation in ("missing", "unknown", "duplicate", "locator", "pending_review", "incomplete_review"):
            with self.subTest(mutation=mutation):
                self.case = copy.deepcopy(original)
                if mutation in {"missing", "unknown", "duplicate"}:
                    self.case["observed_results"][0]["evidence_refs"] = {"missing": [], "unknown": ["E-unknown"], "duplicate": [self.ref, self.ref]}[mutation]
                elif mutation == "locator":
                    self.case["evidence"][0]["locator"] = " "
                elif mutation == "pending_review":
                    self.case["semantic_review"]["status"] = "pending"
                else:
                    self.case["semantic_review"]["reviewed_evidence_refs"] = []
                review = self.check()
                self.assertFalse(review["triage"]["passed"])
                self.assertIsNone(review["cvss31"])

    def test_rule_labels_do_not_automatically_filter_cors_with_supported_impact(self):
        self.case["triage"]["matched_rules"] = ["F1", "F8"]
        self.case["observed_results"][0]["text"] = "CORS test recorded an unauthorized origin reading another test account's private response."
        review = self.check()
        self.assertTrue(review["triage"]["passed"])
        self.assertEqual(9.8, review["cvss31"]["base_score"])

    def test_invalid_declarations_are_issues_but_wrong_shapes_raise(self):
        original = copy.deepcopy(self.case)
        for key, value in (("reason", " "), ("matched_rules", ["F9"]), ("matched_rules", ["F1", "F1"]), ("status", "confirmed")):
            with self.subTest(key=key, value=value):
                self.case = copy.deepcopy(original)
                self.case["triage"][key] = value
                self.assertFalse(self.check()["triage"]["passed"])
        for field, value in (("triage", []), ("cvss31", []), ("triage", {"basis": []}),
                             ("triage", {"basis": {"boundary": "RESULT-1"}}),
                             ("cvss31", {"vector": 8}), ("cvss31", {"rationale": []}),
                             ("cvss31", {"rationale": {"AV": []}}),
                             ("cvss31", {"rationale": {"AV": {"claim_refs": "RESULT-1"}}})):
            with self.subTest(field=field, value=value):
                self.case = copy.deepcopy(original)
                self.case[field] = value
                with self.assertRaises(checker.StructureError):
                    self.check()

    def test_cvss_requires_all_metric_reasons_and_evidence(self):
        original = copy.deepcopy(self.case["cvss31"])
        for metric in original["rationale"]:
            for mutation in ("absent", "reason", "refs", "unknown"):
                with self.subTest(metric=metric, mutation=mutation):
                    self.case["cvss31"] = copy.deepcopy(original)
                    if mutation == "absent":
                        del self.case["cvss31"]["rationale"][metric]
                    elif mutation == "reason":
                        self.case["cvss31"]["rationale"][metric]["reason"] = " "
                    else:
                        self.case["cvss31"]["rationale"][metric]["claim_refs"] = [] if mutation == "refs" else ["MISSING"]
                    review = self.check()
                    self.assertTrue(review["triage"]["passed"])
                    self.assertIsNone(review["cvss31"])

    def test_metric_evidence_must_be_observed_located_and_reviewed_independently(self):
        metric_claim = {"id": "CVSS-EXTRA", "text": "Synthetic metric-specific claim", "verification": "observed", "evidence_refs": [self.ref]}
        self.case["steps"] = [metric_claim]
        self.case["cvss31"]["rationale"]["AV"]["claim_refs"] = [metric_claim["id"]]
        for mutation in ("unverified", "missing", "unregistered"):
            with self.subTest(mutation=mutation):
                metric_claim.update(verification="observed", evidence_refs=[self.ref])
                if mutation == "unverified":
                    metric_claim["verification"] = "unverified"
                else:
                    metric_claim["evidence_refs"] = [] if mutation == "missing" else ["E-other"]
                review = self.check()
                self.assertTrue(review["triage"]["passed"])
                self.assertIsNone(review["cvss31"])

    def test_invalid_vectors_are_business_errors_without_a_score(self):
        for vector in ("", "CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                       "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H", "CVSS:3.1/AV:N/AV:N"):
            with self.subTest(vector=vector):
                self.case["cvss31"]["vector"] = vector
                review = self.check()
                self.assertIsNone(review["cvss31"])
                issue = next(issue for issue in review["issues"] if issue["code"] == "cvss_vector_invalid")
                self.assertEqual("error", issue["level"])

    def test_null_missing_and_incomplete_scores_never_fall_back_to_zero(self):
        for cvss in (None, {"vector": None, "rationale": {}, "reason": "Missing impact evidence."},
                     {"vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", "rationale": {}, "reason": "Need metric basis."}):
            with self.subTest(cvss=cvss):
                self.case.pop("cvss31", None)
                if cvss is not None:
                    self.case["cvss31"] = cvss
                output = self.render()
                self.assertIsNone(json.loads(output["review_issues.json"])["cvss31"])
                self.assertIn("待评估（暂不输出数值）", output["report.md"])
                self.assertNotIn("Base：0", output["report.md"])

    def test_scoring_is_calculated_without_changing_platform_severity_or_inputs(self):
        self.case["cvss31"]["base_score"] = 1.0
        self.profile["fields"].append({"id": "severity", "label": "SRC 等级", "kind": "select", "options": ["中危"], "required": True})
        self.fields["fields"]["severity"] = {"value": "中危", "status": "supported", "evidence_refs": [self.ref]}
        before = copy.deepcopy((self.manifest, self.case, self.fields, self.profile))
        output = self.render()
        review = json.loads(output["review_issues.json"])
        score = review["cvss31"]
        self.assertEqual(9.8, score["base_score"])
        self.assertEqual("CRITICAL", score["severity"])
        self.assertEqual("3.1", score["version"])
        self.assertEqual("Base", score["metric_group"])
        report = output["report.md"]
        self.assertIn(self.case["cvss31"]["vector"], report)
        self.assertIn("CVSS 3.1 Base：9.8（CRITICAL）", report)
        self.assertIn("不等于 SRC 平台等级", report)
        self.assertIn("未经动态漏洞真实性认证", report)
        self.assertIn("SRC 等级\n\n中危", report)
        for metric in self.case["cvss31"]["rationale"]:
            self.assertIn("| " + metric + " |", report)
        self.assertIn("RESULT-1 → " + self.ref, report)
        self.assertIn("line 1", report)
        self.assertEqual(before, (self.manifest, self.case, self.fields, self.profile))

    def test_lead_hides_confirmatory_platform_title_and_impact_but_preserves_source(self):
        self.case["triage"]["basis"]["impact"] = []
        self.fields["fields"]["title"]["value"] = "DEFINITE-EXPLOIT-SENTINEL"
        self.profile["fields"].append({"id": "impact", "label": "漏洞危害", "kind": "richtext", "required": True})
        self.fields["fields"]["impact"] = {"value": "CONFIRMED-DATA-THEFT-SENTINEL", "status": "supported", "evidence_refs": [self.ref]}
        self.fields["content_review"]["notes"] = ["INTERNAL-SELECTION-SENTINEL"]
        before = copy.deepcopy((self.manifest, self.case, self.fields, self.profile))
        output = self.render()
        report = output["report.md"]
        self.assertTrue(report.startswith("# 漏洞线索记录\n"))
        self.assertIn("## 材料观察", report)
        self.assertIn("Observed response marker", report)
        self.assertIn("## 证据定位", report)
        self.assertIn("## 待补证", report)
        self.assertNotIn("## 平台字段", report)
        self.assertNotIn("DEFINITE-EXPLOIT-SENTINEL", report)
        self.assertNotIn("CONFIRMED-DATA-THEFT-SENTINEL", report)
        self.assertTrue(all("INTERNAL-SELECTION-SENTINEL" not in text for text in output.values()))
        self.assertNotIn(self.data.decode().strip(), report)
        self.assertEqual(before, (self.manifest, self.case, self.fields, self.profile))

    def test_file_failure_withdraws_prior_triage_and_score_in_renderer_and_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "materials"
            materials.mkdir()
            self.manifest["materials_root"] = str(materials)
            original = materials / "request.txt"
            original.write_bytes(self.data)
            valid = json.loads(self.render(verify_files=True)["review_issues.json"])
            self.assertTrue(valid["triage"]["passed"])
            self.assertEqual(9.8, valid["cvss31"]["base_score"])
            for changed in (True, False):
                with self.subTest(changed=changed):
                    if changed:
                        original.write_bytes(b"Different original content")
                    else:
                        original.unlink()
                    output = self.render(verify_files=True)
                    review = json.loads(output["review_issues.json"])
                    self.assertFalse(review["triage"]["passed"])
                    self.assertIsNone(review["cvss31"])
                    self.assertIn("triage_materials_unverified", self.codes(review))
                    self.assertTrue(output["report.md"].startswith("# 漏洞线索记录\n"))
                    self.assertNotIn("9.8", output["report.md"])
            command = [sys.executable, str(SCRIPT)]
            for name, doc in (("manifest", self.manifest), ("case", self.case), ("fields", self.fields), ("profile", self.profile)):
                path = root / (name + ".json")
                path.write_text(json.dumps(doc), encoding="utf-8")
                command.extend(["--" + name, str(path)])
            command.extend(["--output", str(root / "review.json")])
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            review = json.loads((root / "review.json").read_text(encoding="utf-8"))
            self.assertFalse(review["triage"]["passed"])
            self.assertIsNone(review["cvss31"])

    def test_invalid_material_registration_withdraws_triage_and_score(self):
        original = copy.deepcopy(self.manifest)
        for mutation in ("duplicate_id", "duplicate_path", "unsafe_path"):
            with self.subTest(mutation=mutation):
                self.manifest = copy.deepcopy(original)
                material = self.manifest["materials"][0]
                if mutation == "duplicate_id":
                    self.manifest["materials"].append(copy.deepcopy(material))
                elif mutation == "duplicate_path":
                    material["paths"].append(material["paths"][0])
                else:
                    material["paths"] = ["../request.txt"]
                review = self.check()
                self.assertFalse(review["triage"]["passed"])
                self.assertIsNone(review["cvss31"])
                self.assertIn("triage_materials_invalid", self.codes(review))
                report = self.render()["report.md"]
                self.assertTrue(report.startswith("# 漏洞线索记录\n"))
                self.assertNotIn("9.8", report)


if __name__ == "__main__":
    unittest.main()
