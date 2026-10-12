"""Regression checks against the captured source, without online target access."""

import json
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "references" / "src"
sys.path.insert(0, str(ROOT / "scripts"))
from check_report import check_report
from index_materials import index_materials
from render_report import render_report, write_outputs
from test_check_report import assessment_declarations


def load_profile(platform):
    return json.loads((PROFILE_DIR / f"{platform}.json").read_text(encoding="utf-8"))


def table_rows(section, heading):
    part = section.split(heading, 1)[1].split("\n### ", 1)[0]
    rows = [line for line in part.splitlines() if line.startswith("|")]
    return [[cell.strip() for cell in line.strip("|").split("|")] for line in rows[2:]]


class ProfileContractTests(unittest.TestCase):
    def test_independent_profiles_and_condition_references(self):
        profiles = sorted(PROFILE_DIR.glob("*.json"))
        self.assertTrue(profiles, "No SRC profiles found")
        for profile_path in profiles:
            platform = profile_path.stem
            with self.subTest(platform=platform):
                profile = load_profile(platform)
                self.assertEqual(profile["id"], platform)
                date.fromisoformat(profile["verified_at"])
                self.assertIsInstance(profile["version"], str)
                self.assertTrue(profile["version"].strip())
                self.assertTrue(profile["source_urls"])
                self.assertTrue((PROFILE_DIR / f"{platform}.md").is_file())
                fields = {field["id"]: field for field in profile["fields"]}
                self.assertEqual(len(fields), len(profile["fields"]))
                for field in fields.values():
                    self.assertIn(field["kind"], ("text", "multiline", "richtext", "select", "cascade", "boolean", "attachments"))
                    self.assertIn(field["required"], (True, False, None))
                    self.assertTrue(field["label"])
                    self.assertTrue(field["map_from"])
                    if "group" in field:
                        self.assertIn(field["group"], profile["groups"])
                    if "when" in field:
                        pending = [field["when"]]
                        while pending:
                            condition = pending.pop()
                            if "all" in condition or "any" in condition:
                                pending.extend(condition.get("all", condition.get("any", [])))
                                continue
                            parent = fields[condition["field"]]
                            self.assertIn(parent.get("group"), (None, field.get("group")))
                            allowed = parent.get("options", parent.get("option_paths", []))
                            values = [condition["equals"]] if "equals" in condition else condition["in"]
                            for value in values:
                                self.assertIn(value, allowed)
                    if "parent_field" in field:
                        parent = fields[field["parent_field"]]
                        self.assertLessEqual(set(field["options_by_parent"]), set(parent["options"]))
                self.assertIsInstance(profile["body_sections"], list)
                for section in profile["body_sections"]:
                    self.assertTrue(section["id"])
                    self.assertTrue(section["label"])
                    self.assertTrue(section["map_from"])

    def test_new_platform_flows_from_materials_to_markdown(self):
        platform = "synthetic-src"
        schema = json.loads((ROOT / "references" / "report-schema.json").read_text(encoding="utf-8"))
        for document in ("case", "fields"):
            src = schema["$defs"][document]["properties"]["src"]
            self.assertEqual(src["type"], "string")
            self.assertEqual(src["minLength"], 1)
            self.assertNotIn("enum", src)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "materials"
            materials.mkdir()
            original = "Synthetic evidence: response contains EXAMPLE.\n"
            (materials / "response.txt").write_text(original, encoding="utf-8")
            manifest = index_materials(materials)
            ref = manifest["materials"][0]["evidence_id"]
            profile = {"id": platform, "version": "1.0", "groups": {}, "source_urls": [], "fields": [
                {"id": "title", "label": "漏洞标题", "kind": "text", "required": True},
                {"id": "proof", "label": "平台证明字段", "kind": "richtext", "required": True},
            ]}
            case = {"schema_version": "1.0", "case_id": "synthetic", "version": 1,
                    "src": platform, "profile_version": profile["version"], "target": {},
                    "identities": [], "prerequisites": [], "steps": [], "supported_impact": [],
                    "observed_results": [{"id": "R1", "text": "记录包含 EXAMPLE 标记",
                                          "verification": "observed", "evidence_refs": [ref]}],
                    "evidence": [{"evidence_id": ref, "locator": "response.txt:1", "note": "合成响应标记"}],
                    "uncertainties": [],
                    "semantic_review": {"status": "completed", "notes": [], "reviewed_evidence_refs": [ref]}}
            case.update(assessment_declarations("R1"))
            fields = {"schema_version": "1.0", "case_id": case["case_id"], "case_version": case["version"],
                      "src": platform, "profile_version": profile["version"], "groups": {}, "fields": {
                          "title": {"value": "合成第四平台报告", "status": "supported", "evidence_refs": [ref]},
                          "proof": {"value": "### 已观察内容\n记录包含 EXAMPLE 标记。", "status": "supported", "evidence_refs": [ref]},
                      }, "redaction_review": {"status": "completed", "notes": []},
                      "content_review": {"status": "completed", "notes": [
                          "response.txt:1 只有合成响应标记，无 PoC 可精简；已核对正文与定位，未加入无依据的影响。"]}}
            contents = render_report(manifest, case, fields, profile)
            review = json.loads(contents["review_issues.json"])
            self.assertEqual(review["status"], "checked")
            self.assertFalse(review["semantic_verified"])
            output = root / "output"
            write_outputs(contents, output, materials, [])
            report = (output / "report.md").read_text(encoding="utf-8")
            self.assertIn("平台：synthetic-src", report)
            self.assertIn("### 平台证明字段", report)
            self.assertIn("#### 已观察内容", report)
            self.assertIn(ref, report)
            self.assertEqual((materials / "response.txt").read_text(encoding="utf-8"), original)
            for document, data in (("case", case), ("fields", fields)):
                with self.subTest(mismatched_document=document):
                    data["src"] = "another-src"
                    review = check_report(manifest, case, fields, profile)
                    self.assertEqual(review["status"], "needs_revision")
                    self.assertTrue(any(issue["code"] == "src_mismatch" and issue["path"] == f"{document}.src"
                                        for issue in review["issues"]))
                    data["src"] = platform

    def test_site_fields_stay_separate(self):
        jd, mt, ks = (load_profile(p) for p in ("jd", "meituan", "kuaishou"))
        self.assertEqual(len(jd["fields"]), 24)
        self.assertEqual(len(mt["fields"]), 12)
        self.assertEqual(len(ks["fields"]), 9)
        self.assertEqual({field["id"] for field in mt["fields"]}, {
            "title", "type_primary", "type_secondary", "url", "test_ip", "test_account",
            "severity", "details", "attachments", "captcha", "contact", "agreement",
        })
        self.assertEqual({field["id"] for field in ks["fields"]}, {
            "title", "vulnerability_type", "application", "url", "request_packet",
            "details", "remediation", "attachments", "agreement",
        })
        self.assertNotIn("remediation", {field["id"] for field in jd["fields"]})
        self.assertNotIn("attachments", {field["id"] for field in jd["fields"]})

    def test_jd_groups_and_sensitive_manual_fields(self):
        profile = load_profile("jd")
        self.assertEqual({key: group["min_items"] for key, group in profile["groups"].items()},
                         {"test_ips": 1, "test_accounts": 1, "request_packets": 1, "flag": 0})
        fields = {field["id"]: field for field in profile["fields"]}
        self.assertEqual({f["id"] for f in fields.values() if f.get("group") == "request_packets"}, {
            "request_packet", "harm_type", "impact_description", "core_network", "network_screenshots", "account_credentials",
        })
        for field_id in ("test_password", "account_credentials", "captcha", "agreement"):
            self.assertIs(fields[field_id]["manual"], True)
        for field_id in ("flag_level", "flag_credential", "silver_activation"):
            self.assertIs(fields[field_id]["read_only"], True)
        self.assertIsNone(fields["network_screenshots"]["required"])

    def test_attachment_uncertainty_preserved(self):
        jd = {f["id"]: f for f in load_profile("jd")["fields"]}["network_screenshots"]
        self.assertEqual(jd["max_items"], 3)
        self.assertEqual(jd["size_limit"]["scope"], "per_file")
        self.assertTrue(jd["size_limit"]["inclusive"])
        for platform, extensions, inclusive in (
            ("meituan", [".doc", ".docx", ".zip"], True),
            ("kuaishou", [".pdf", ".zip", ".rar"], False),
        ):
            field = {f["id"]: f for f in load_profile(platform)["fields"]}["attachments"]
            self.assertEqual(field["extensions"], extensions)
            self.assertNotIn("max_items", field)
            self.assertEqual(field["size_limit"]["scope"], "unknown")
            self.assertEqual(field["size_limit"]["basis"], "conservative_decimal")
            self.assertEqual(field["size_limit"]["bytes"], 10_000_000)
            self.assertEqual(field["size_limit"]["inclusive"], inclusive)


@unittest.skipUnless((ROOT / "SRC提交字段汇总.md").is_file(), "Repository capture is not included in installed skill")
class CapturedEnumerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / "SRC提交字段汇总.md").read_text(encoding="utf-8")
        cls.jd = source.split("## 京东 SRC", 1)[1].split("## 美团 SRC", 1)[0]
        cls.mt = source.split("## 美团 SRC", 1)[1].split("## 快手 SRC", 1)[0]
        cls.ks = source.split("## 快手 SRC", 1)[1]

    def test_jd_classifications_and_departments_match_capture(self):
        fields = {f["id"]: f for f in load_profile("jd")["fields"]}
        departments = self.jd.split("公司部门选项：", 1)[1].split("。", 1)[0].split("、")
        self.assertEqual(fields["department"]["options"], departments)
        complete, incomplete = [], []
        for primary, secondary in table_rows(self.jd, "### 漏洞类型下拉选项"):
            for label in secondary.split("；"):
                path = [primary, label.replace("（需三级）", "")]
                (incomplete if "（需三级）" in label else complete).append(path)
        self.assertEqual(fields["vulnerability_type"]["option_paths"], complete)
        self.assertEqual(fields["vulnerability_type"]["incomplete_paths"], incomplete)
        self.assertEqual(len(complete), 68)
        self.assertEqual(len(incomplete), 12)
        self.assertFalse(set(map(tuple, complete)) & set(map(tuple, incomplete)))

    def test_meituan_parent_child_options_match_capture(self):
        fields = {f["id"]: f for f in load_profile("meituan")["fields"]}
        expected = {primary: values.split("；") for primary, values in table_rows(self.mt, "### 漏洞类型下拉选项")}
        self.assertEqual(fields["type_primary"]["options"], list(expected))
        self.assertEqual(fields["type_secondary"]["options_by_parent"], expected)
        self.assertEqual(sum(map(len, expected.values())), 103)

    def test_kuaishou_paths_and_applications_match_capture(self):
        fields = {f["id"]: f for f in load_profile("kuaishou")["fields"]}
        expected = []
        for primary, secondary, tertiary in table_rows(self.ks, "### “漏洞类型”下拉选项"):
            for second in secondary.split("；"):
                if tertiary == "无三级":
                    expected.append([primary, second])
                else:
                    expected.extend([[primary, second, leaf] for leaf in tertiary.split("；")])
        applications = [value for _, values in table_rows(self.ks, "### “所属应用”下拉选项") for value in values.split("；")]
        self.assertEqual(fields["vulnerability_type"]["option_paths"], expected)
        self.assertEqual(fields["application"]["options"], applications)
        self.assertEqual(len(applications), 87)
        self.assertEqual(len(expected), 31)


if __name__ == "__main__":
    unittest.main()
