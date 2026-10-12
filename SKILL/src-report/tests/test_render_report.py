import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from index_materials import index_materials
from render_report import STATUS, render_report, write_outputs


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.materials = self.root / "materials"
        self.materials.mkdir()
        (self.materials / "note.txt").write_text("Synthetic note: no response was recorded.\n", encoding="utf-8")
        self.manifest = index_materials(self.materials)
        self.ref = self.manifest["materials"][0]["evidence_id"]
        self.profile = {"id": "meituan", "version": "2026-10-03.1", "groups": {}, "fields": [
            {"id": "title", "label": "漏洞名称", "kind": "text", "required": True},
            {"id": "request_packet", "label": "请求包", "kind": "multiline", "required": True},
            {"id": "agreement", "label": "用户协议", "kind": "boolean", "manual": True, "required": None},
        ], "source_urls": []}
        self.case = {"schema_version": "1.0", "case_id": "synthetic", "version": 1, "src": "meituan", "profile_version": self.profile["version"],
                     "target": {}, "identities": [], "prerequisites": [], "steps": [], "observed_results": [],
                     "supported_impact": [{"id": "I1", "text": "请求效果尚未验证", "verification": "unverified", "evidence_refs": [self.ref]}],
                     "evidence": [{"evidence_id": self.ref, "locator": "note.txt:1", "note": "缺少响应"}],
                     "uncertainties": [{"id": "U1", "description": "需要执行结果材料", "affects": ["I1"], "evidence_refs": [self.ref]}],
                     "semantic_review": {"status": "pending", "notes": [], "reviewed_evidence_refs": []}}
        self.fields = {"schema_version": "1.0", "case_id": "synthetic", "case_version": 1, "src": "meituan", "profile_version": self.profile["version"],
                       "fields": {"title": {"value": "合成材料草稿", "status": "supported", "evidence_refs": [self.ref]},
                                  "request_packet": {"value": "GET /example HTTP/1.1\n```\nEND", "status": "inferred", "evidence_refs": [self.ref]},
                                  "agreement": {"value": None, "status": "manual", "evidence_refs": []}},
                       "groups": {}, "redaction_review": {"status": "pending", "notes": []},
                       "content_review": {"status": "pending", "notes": []}}

    def test_draft_keeps_uncertainty_and_does_not_copy_evidence(self):
        result = render_report(self.manifest, self.case, self.fields, self.profile)
        self.assertEqual(set(result), {"report.md", "attachments.md", "review_issues.json"})
        report = result["report.md"]
        self.assertIn(STATUS["unverified"], report)
        self.assertIn("需要执行结果材料", report)
        self.assertIn("````text\nGET", report)
        self.assertNotIn("Synthetic note:", report)
        review = json.loads(result["review_issues.json"])
        self.assertFalse(review["semantic_verified"])
        self.assertNotEqual(review["status"], "checked")

    def test_content_review_warnings_use_friendly_label_and_keep_draft(self):
        self.case["supported_impact"] = []
        self.case["uncertainties"] = []
        self.case["semantic_review"]["status"] = "completed"
        self.fields["redaction_review"]["status"] = "completed"
        self.fields["fields"]["request_packet"]["status"] = "supported"
        self.profile["fields"] = self.profile["fields"][:2]
        self.fields["fields"].pop("agreement")
        for declaration, code in ((None, "content_review_pending"),
                                  ({"status": "pending", "notes": []}, "content_review_pending"),
                                  ({"status": "completed", "notes": ["  "]}, "content_review_notes_missing")):
            with self.subTest(declaration=declaration):
                self.fields.pop("content_review", None)
                if declaration is not None:
                    self.fields["content_review"] = declaration
                result = render_report(self.manifest, self.case, self.fields, self.profile)
                report, review = result["report.md"], json.loads(result["review_issues.json"])
                self.assertEqual("draft", review["status"])
                issue = next(item for item in review["issues"] if item["code"] == code)
                self.assertIn("内容复核：" + issue["message"], report)
                self.assertNotIn(issue["path"], report)
                self.assertFalse(review["semantic_verified"])

    def test_content_review_notes_remain_internal_for_pending_and_completed(self):
        for status in ("pending", "completed"):
            with self.subTest(status=status):
                self.fields["content_review"] = {"status": status, "notes": ["INTERNAL-SELECTION-SENTINEL"]}
                before = copy.deepcopy((self.manifest, self.case, self.fields, self.profile))
                result = render_report(self.manifest, self.case, self.fields, self.profile)
                self.assertTrue(all("INTERNAL-SELECTION-SENTINEL" not in text for text in result.values()))
                self.assertEqual(before, (self.manifest, self.case, self.fields, self.profile))

    def test_illegal_manual_value_is_not_rendered(self):
        self.fields["fields"]["agreement"]["value"] = "SECRET_SENTINEL"
        result = render_report(self.manifest, self.case, self.fields, self.profile)
        self.assertNotIn("SECRET_SENTINEL", result["report.md"])

    def test_original_mutation_is_reported(self):
        (self.materials / "note.txt").write_text("Different bytes", encoding="utf-8")
        result = render_report(self.manifest, self.case, self.fields, self.profile)
        self.assertEqual(json.loads(result["review_issues.json"])["status"], "needs_revision")

    def test_body_headings_and_plaintext_placeholders_remain_readable(self):
        self.profile["fields"].append({"id": "details", "label": "详情", "kind": "richtext", "required": True})
        self.fields["fields"]["details"] = {"value": "### 原有小节\n```python\n# retain code comment\n```", "status": "supported", "evidence_refs": [self.ref]}
        self.fields["fields"]["title"]["value"] = "对象 <ORDER-X>"
        report = render_report(self.manifest, self.case, self.fields, self.profile)["report.md"]
        self.assertIn("### 详情\n", report)
        self.assertIn("#### 原有小节\n", report)
        self.assertIn("```python\n# retain code comment\n```", report)
        self.assertIn("对象 &lt;ORDER-X&gt;", report)

    def test_invalid_attachment_value_yields_reviewable_draft(self):
        self.profile["fields"].append({"id": "attachments", "label": "附件", "kind": "attachments", "required": None})
        self.fields["fields"]["attachments"] = {"value": "not-an-array", "status": "supported", "evidence_refs": [self.ref]}
        result = render_report(self.manifest, self.case, self.fields, self.profile)
        self.assertEqual(json.loads(result["review_issues.json"])["status"], "needs_revision")
        self.assertIn("附件字段类型无效", result["report.md"])

    def test_observed_facts_are_not_repeated_outside_platform_body(self):
        facts = []
        for index, collection in enumerate(("identities", "prerequisites", "steps", "observed_results", "supported_impact")):
            text = f"已观察内容 {index}"
            facts.append(text)
            self.case[collection] = [{"id": f"C{index}", "text": text, "verification": "observed", "evidence_refs": [self.ref]}]
        self.profile["fields"].append({"id": "details", "label": "详情", "kind": "richtext", "required": True})
        self.fields["fields"]["details"] = {"value": "\n\n".join(facts), "status": "supported", "evidence_refs": [self.ref]}

        report = render_report(self.manifest, self.case, self.fields, self.profile)["report.md"]

        for fact in facts:
            self.assertEqual(report.count(fact), 1)
        self.assertNotIn(STATUS["supported"], report)

    def test_uncertain_claims_keep_status_and_evidence_without_duplicate_reminders(self):
        self.case["supported_impact"] = [
            {"id": f"I{index}", "text": f"异常结论 {status}", "verification": status, "evidence_refs": [self.ref]}
            for index, status in enumerate(("inferred", "unverified", "conflicted"), 1)
        ]
        self.case["uncertainties"][0]["affects"] = []
        result = render_report(self.manifest, self.case, self.fields, self.profile)
        report, review = result["report.md"], json.loads(result["review_issues.json"])

        for claim in self.case["supported_impact"]:
            self.assertEqual(report.count(claim["text"]), 1)
            claim_line = next(line for line in report.splitlines() if claim["text"] in line)
            self.assertIn(STATUS[claim["verification"]], claim_line)
            self.assertIn(self.ref, report.split(claim["text"], 1)[1].splitlines()[1])
        uncertainty = self.case["uncertainties"][0]
        self.assertEqual(report.count(uncertainty["description"]), 1)
        self.assertIn(self.ref, report.split(uncertainty["description"], 1)[1].splitlines()[1])
        for issue in review["issues"]:
            self.assertNotIn(issue["path"], report)
            if issue["code"] in {"inferred_claim", "claim_unverified", "claim_conflicted", "unresolved_uncertainty"}:
                self.assertNotIn(issue["message"], report)

    def test_explicit_gap_links_combine_claim_statuses_and_all_evidence(self):
        for name in ("identity", "conflict", "inference"):
            (self.materials / f"{name}.txt").write_text(f"Synthetic {name} evidence", encoding="utf-8")
        self.manifest = index_materials(self.materials)
        refs = {material["paths"][0]: material["evidence_id"] for material in self.manifest["materials"]}
        linked = [
            {"id": "I2", "text": "账号归属缺少证明", "verification": "unverified", "evidence_refs": [refs["identity.txt"]]},
            {"id": "P2", "text": "两个身份记录互相矛盾", "verification": "conflicted", "evidence_refs": [refs["conflict.txt"]]},
            {"id": "S2", "text": "推测请求来自同一身份", "verification": "inferred", "evidence_refs": [refs["inference.txt"]]},
        ]
        self.case["identities"], self.case["prerequisites"], self.case["steps"] = [[claim] for claim in linked]
        fallback = self.case["supported_impact"][0]
        fallback["evidence_refs"] = [refs["identity.txt"]]
        gap = self.case["uncertainties"][0]
        gap["description"] = "补充两账号身份对应关系"
        gap["affects"] = [claim["id"] for claim in linked]
        original_case = copy.deepcopy(self.case)

        report = render_report(self.manifest, self.case, self.fields, self.profile)["report.md"]

        self.assertEqual(report.count(gap["description"]), 1)
        gap_block = report.split(gap["description"], 1)[1].split("\n- ", 1)[0]
        for claim in linked:
            self.assertNotIn(claim["text"], report)
            self.assertIn(claim["id"], gap_block)
            self.assertIn(STATUS[claim["verification"]], gap_block)
            for ref in claim["evidence_refs"]:
                self.assertEqual(gap_block.count(ref), 1)
        for ref in gap["evidence_refs"]:
            self.assertEqual(gap_block.count(ref), 1)
        self.assertEqual(report.count(fallback["text"]), 1)
        self.assertEqual(self.case, original_case)

    def test_group_conditions_and_diagnostics_use_each_rows_values_and_labels(self):
        self.profile["groups"] = {"packets": {"label": "请求记录", "min_items": 1}}
        self.profile["fields"].extend([
            {"id": "mode", "label": "条件选择", "kind": "select", "group": "packets", "options": ["是", "否"]},
            {"id": "proof", "label": "验证截图", "kind": "text", "group": "packets", "required": True,
             "when": {"field": "mode", "equals": "是"}},
        ])
        self.fields["groups"] = {"packets": [
            {"mode": {"value": "是", "status": "supported", "evidence_refs": [self.ref]},
             "proof": {"value": "第一组证据", "status": "supported", "evidence_refs": [self.ref]}},
            {"mode": {"value": "否", "status": "supported", "evidence_refs": [self.ref]},
             "proof": {"value": "不适用的旧证据", "status": "supported", "evidence_refs": [self.ref]}},
            {"mode": {"value": "是", "status": "manual", "evidence_refs": []},
             "proof": {"value": "条件仍待确认的证据", "status": "supported", "evidence_refs": [self.ref]}},
        ]}
        result = render_report(self.manifest, self.case, self.fields, self.profile)
        report, review = result["report.md"], json.loads(result["review_issues.json"])

        self.assertIn("第一组证据", report)
        self.assertNotIn("不适用的旧证据", report)
        self.assertIn("条件仍待确认的证据", report)
        for issue_code, row_number in (("inactive_field_value", 2), ("condition_unknown", 3)):
            issue = next(item for item in review["issues"] if item["code"] == issue_code)
            line = next(line for line in report.splitlines() if issue["message"] in line)
            self.assertIn("请求记录", line)
            self.assertIn("验证截图", line)
            self.assertRegex(line, rf"\b{row_number}\b")
            self.assertNotIn(issue["path"], report)

    def test_new_platform_multiline_field_preserves_verbatim_lines(self):
        self.profile["id"] = self.case["src"] = self.fields["src"] = "future-src"
        self.profile["fields"].append({"id": "reproduction_notes", "label": "补充操作", "kind": "multiline"})
        content = "第一行\n<KEEP-LITERAL>\n```\n最后一行"
        self.fields["fields"]["reproduction_notes"] = {"value": content, "status": "supported", "evidence_refs": [self.ref]}

        report = render_report(self.manifest, self.case, self.fields, self.profile)["report.md"]

        self.assertRegex(report, r"(?m)^(`{4,})text\n" + re.escape(content) + r"\n\1$")

    def test_condition_alternatives_render_each_matching_branch_and_keep_unknown(self):
        self.profile["fields"] += [
            {"id": "category", "label": "Category", "kind": "select"},
            {"id": "mobile", "label": "Mobile details", "kind": "text", "required": True,
             "when": {"field": "category", "in": ["Android", "iOS"]}}]
        self.fields["fields"]["mobile"] = {"value": "MOBILE-SENTINEL", "status": "supported", "evidence_refs": [self.ref]}
        for value, status, visible in (("Android", "supported", True), ("iOS", "supported", True),
                                       ("Web", "supported", False), ("Web", "manual", True),
                                       (" \t\n", "supported", True), (None, "missing", True)):
            with self.subTest(value=value, status=status):
                self.fields["fields"]["category"] = {"value": value, "status": status, "evidence_refs": [self.ref]}
                output = render_report(self.manifest, self.case, self.fields, self.profile)
                self.assertEqual(visible, "MOBILE-SENTINEL" in output["report.md"])
                codes = {issue["code"] for issue in json.loads(output["review_issues.json"])["issues"]}
                self.assertEqual(status in {"manual", "missing"} or value == " \t\n", "condition_unknown" in codes)

    def test_nested_conditions_use_each_row_and_ignore_stale_unrelated_business_values(self):
        self.profile["groups"] = {"requests": {"label": "Requests", "min_items": 1}}
        self.profile["fields"] += [
            {"id": "family", "label": "Family", "kind": "select"},
            {"id": "business", "label": "Business", "kind": "select", "group": "requests"},
            {"id": "domain", "label": "Domain", "kind": "text", "required": True, "group": "requests",
             "when": {"any": [{"field": "family", "equals": "web"}, {"all": [
                 {"field": "family", "equals": "intel"}, {"field": "business", "equals": "web"}]}]}}]
        self.fields["groups"]["requests"] = [
            {"business": {"value": value, "status": status, "evidence_refs": [self.ref]},
             "domain": {"value": f"DOMAIN-SENTINEL-{index}", "status": "supported", "evidence_refs": [self.ref]}}
            for index, (value, status) in enumerate((("web", "supported"), ("app", "supported"), ("web", "manual")))]
        for family, visible, unknown in (("intel", {0, 2}, True), ("mobile", set(), False), ("web", {0, 1, 2}, False)):
            with self.subTest(family=family):
                self.fields["fields"]["family"] = {"value": family, "status": "supported", "evidence_refs": [self.ref]}
                output = render_report(self.manifest, self.case, self.fields, self.profile)
                for index in range(3):
                    self.assertEqual(index in visible, f"DOMAIN-SENTINEL-{index}" in output["report.md"])
                codes = {issue["code"] for issue in json.loads(output["review_issues.json"])["issues"]}
                self.assertEqual(unknown, "condition_unknown" in codes)

    def test_http_fields_are_not_cleaned_or_deduplicated_in_text_and_repeated_groups(self):
        request = ("POST /example?id=1&id=2 HTTP/1.1\n"
                   "Host: example.invalid\n"
                   "Cookie: session=SYNTHETIC; role=reader\n"
                   "Origin: https://example.invalid\n"
                   "X-Signature: SYNTHETIC-SIGNATURE\n"
                   "Content-Type: application/x-www-form-urlencoded\n"
                   "Content-Length: 13\n\n"
                   "item=1&item=2")
        note = "完整脱敏请求；原件 request.http:1-9，未验证可重放。"
        for kind in ("multiline", "richtext"):
            for grouped in (False, True):
                with self.subTest(kind=kind, grouped=grouped):
                    fields, profile = copy.deepcopy((self.fields, self.profile))
                    entry = fields["fields"].pop("request_packet")
                    entry.update(value=request if kind == "multiline" else "### 请求\n```http\n" + request + "\n```",
                                 status="supported", notes=note)
                    definition = profile["fields"][1]
                    definition["kind"] = kind
                    if grouped:
                        profile["groups"] = {"packets": {"label": "请求记录", "min_items": 1}}
                        definition["group"] = "packets"
                        fields["groups"] = {"packets": [{"request_packet": copy.deepcopy(entry)} for _ in range(2)]}
                    else:
                        fields["fields"]["request_packet"] = entry
                    before = copy.deepcopy((self.manifest, self.case, fields, profile))
                    report = render_report(self.manifest, self.case, fields, profile)["report.md"]
                    self.assertEqual(2 if grouped else 1, report.count(request))
                    self.assertEqual(2 if grouped else 1, report.count(note))
                    blocks = re.findall(r"(?ms)^```(?:text|http)\n(.*?)\n```$", report)
                    self.assertIn(request, blocks)
                    self.assertTrue(all(note not in block for block in blocks))
                    self.assertEqual(before, (self.manifest, self.case, fields, profile))

    def test_legacy_draft_omits_empty_evidence_section_and_keeps_manual_fields(self):
        self.case["supported_impact"] = []
        self.case["uncertainties"] = []
        self.case["evidence"] = []
        self.case["semantic_review"]["status"] = "completed"
        self.fields["redaction_review"]["status"] = "completed"
        self.fields["content_review"] = {"status": "completed", "notes": ["PoC selection and whole-report consistency reviewed."]}
        self.fields["fields"]["request_packet"]["status"] = "supported"
        report = render_report(self.manifest, self.case, self.fields, self.profile)["report.md"]

        self.assertNotIn("## 证据定位", report)
        self.assertIn("## 漏洞评估", report)
        self.assertIn("## 平台字段", report)
        self.assertIn("未筛选的旧版草稿", report)
        manual = self.profile["fields"][2]
        self.assertIn(manual["label"], report)
        self.assertNotIn("fields.fields.agreement", report)

    def test_output_write_is_guarded(self):
        contents = {"report.md": "draft"}
        with self.assertRaises(ValueError):
            write_outputs(contents, self.materials, self.materials, [])
        output = self.root / "out"
        write_outputs(contents, output, self.materials, [])
        with self.assertRaises(ValueError):
            write_outputs(contents, output, self.materials, [])
        with self.assertRaises(ValueError):
            write_outputs(contents, output, self.materials, [output / "report.md"], overwrite=True)
        write_outputs({"report.md": "new draft"}, output, self.materials, [], overwrite=True)
        self.assertEqual((output / "report.md").read_text(encoding="utf-8"), "new draft")


if __name__ == "__main__":
    unittest.main()
