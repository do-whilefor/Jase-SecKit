"""Exercise captured profiles with temporary, synthetic evidence only."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_report import check_report, condition_state
from index_materials import index_materials
from render_report import render_report, write_outputs
from test_check_report import synthetic_documents


PLATFORMS = tuple(path.stem for path in sorted((ROOT / "references" / "src").glob("*.json")))


def condition_leaves(condition):
    if "field" in condition:
        yield condition
    else:
        for child in condition.get("all", condition.get("any", [])):
            yield from condition_leaves(child)


class PlatformIntegrationTests(unittest.TestCase):
    def documents(self, platform):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        materials = root / "materials"
        materials.mkdir()
        manifest, case, fields, _, data, ref = synthetic_documents(str(materials))
        (materials / "request.txt").write_bytes(data)
        profile = json.loads((ROOT / "references" / "src" / f"{platform}.json").read_text(encoding="utf-8"))
        for document in (case, fields):
            document.update(src=platform, profile_version=profile["version"])
        fields["fields"] = {}
        fields["groups"] = {group: [{} for _ in range(max(1, config.get("min_items", 0)))]
                            for group, config in profile.get("groups", {}).items()}

        def record(value, status="supported"):
            return {"value": value, "status": status, "evidence_refs": [ref] if status == "supported" else []}

        for definition in profile["fields"]:
            rows = fields["groups"][definition["group"]] if definition.get("group") else [fields["fields"]]
            for row in rows:
                if definition.get("manual") or definition.get("read_only"):
                    row[definition["id"]] = record(None, "manual")
                    continue
                kind = definition["kind"]
                if "options" in definition:
                    value = definition["options"][0]
                elif definition.get("option_paths"):
                    value = definition["option_paths"][0]
                elif "options_by_parent" in definition:
                    parent = row.get(definition["parent_field"], fields["fields"].get(definition["parent_field"]))
                    children = definition["options_by_parent"].get(parent["value"], [])
                    value = children[0] if children else "Synthetic uncollected child"
                elif kind == "cascade":
                    value = definition.get("incomplete_paths", [["Synthetic"]])[0] + ["Synthetic leaf"]
                elif kind == "boolean":
                    value = False
                elif kind == "attachments":
                    extension = definition.get("extensions", [".txt"])[0]
                    path = f"synthetic-{definition['id']}{extension}"
                    (materials / path).write_text(f"Synthetic attachment for {definition['id']}\n", encoding="utf-8")
                    manifest = index_materials(materials)
                    attachment_ref = next(item["evidence_id"] for item in manifest["materials"] if path in item["paths"])
                    row[definition["id"]] = {"value": [{"path": path, "evidence_id": attachment_ref}],
                                             "status": "supported", "evidence_refs": [attachment_ref]}
                    continue
                else:
                    value = f"Synthetic {definition['id']}"
                row[definition["id"]] = record(value)

        # Respect the actual selected branch, including row-local conditions.
        for definition in profile["fields"]:
            condition = definition.get("when")
            if not condition:
                continue
            rows = fields["groups"][definition["group"]] if definition.get("group") else [fields["fields"]]
            for row in rows:
                if condition_state(condition, row, fields["fields"]) is False:
                    row[definition["id"]] = record(None, "not_applicable")
        return manifest, case, fields, profile

    @staticmethod
    def row(fields, definition):
        return fields["groups"][definition["group"]][0] if definition.get("group") else fields["fields"]

    @staticmethod
    def field_issues(review, field_id):
        return [issue for issue in review["issues"] if issue["path"].endswith("." + field_id)]

    def activate(self, fields, definition):
        def activate_condition(condition):
            if "all" in condition:
                for child in condition["all"]:
                    activate_condition(child)
                return
            if "any" in condition:
                activate_condition(condition["any"][0])
                return
            row = self.row(fields, definition)
            parent = row.get(condition["field"], fields["fields"].get(condition["field"]))
            value = condition["equals"] if "equals" in condition else condition["in"][0]
            parent.update(value=copy.deepcopy(value), status="supported")
        if definition.get("when"):
            activate_condition(definition["when"])

    def test_all_profiles_render_registered_materials_without_errors(self):
        self.assertTrue(PLATFORMS, "No SRC profiles found")
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                documents = self.documents(platform)
                before = copy.deepcopy(documents)
                manifest, case, fields, profile = documents
                output = render_report(*documents)
                review = json.loads(output["review_issues.json"])
                self.assertFalse([issue for issue in review["issues"] if issue["level"] == "error"])
                self.assertFalse(review["semantic_verified"])
                self.assertIn(f"平台：{platform}", output["report.md"])
                self.assertIn("Synthetic title", output["report.md"])
                for definition in profile["fields"]:
                    if self.row(fields, definition)[definition["id"]]["status"] != "not_applicable":
                        self.assertIn(definition["label"], output["report.md"])
                destination = Path(manifest["materials_root"]).parent / "output"
                write_outputs(output, destination, Path(manifest["materials_root"]), [])
                self.assertEqual(set(output), {path.name for path in destination.iterdir()})
                self.assertEqual(before, documents)

    def test_required_fields_and_manual_controls_keep_distinct_behavior(self):
        for platform in PLATFORMS:
            documents = self.documents(platform)
            manifest, case, original_fields, profile = documents
            for definition in profile["fields"]:
                if not definition.get("required") or definition.get("manual") or definition.get("read_only"):
                    continue
                with self.subTest(platform=platform, field=definition["id"]):
                    fields = copy.deepcopy(original_fields)
                    self.activate(fields, definition)
                    self.row(fields, definition)[definition["id"]].update(value=None, status="missing")
                    issues = self.field_issues(check_report(manifest, case, fields, profile), definition["id"])
                    self.assertIn("required_field_missing", {issue["code"] for issue in issues})
            for definition in profile["fields"]:
                if not (definition.get("manual") or definition.get("read_only")):
                    continue
                with self.subTest(platform=platform, manual=definition["id"]):
                    fields = copy.deepcopy(original_fields)
                    self.activate(fields, definition)
                    self.row(fields, definition)[definition["id"]].update(value="PRIVATE-SENTINEL", status="supported")
                    output = render_report(manifest, case, fields, profile)
                    issues = self.field_issues(json.loads(output["review_issues.json"]), definition["id"])
                    self.assertIn("manual_value_present", {issue["code"] for issue in issues})
                    self.assertNotIn("PRIVATE-SENTINEL", output["report.md"])

    def test_captured_enumerations_reject_values_outside_the_recorded_choices(self):
        for platform in PLATFORMS:
            manifest, case, original_fields, profile = self.documents(platform)
            for definition in profile["fields"]:
                if definition.get("manual") or definition.get("read_only"):
                    continue
                for key, code, value in (("options", "invalid_option", "OUTSIDE-CAPTURE"),
                                         ("option_paths", "invalid_option_path", ["OUTSIDE-CAPTURE"]),
                                         ("options_by_parent", "invalid_child_option", "OUTSIDE-CAPTURE")):
                    if key not in definition:
                        continue
                    with self.subTest(platform=platform, field=definition["id"], constraint=key):
                        fields = copy.deepcopy(original_fields)
                        self.activate(fields, definition)
                        self.row(fields, definition)[definition["id"]].update(value=value, status="supported")
                        issues = self.field_issues(check_report(manifest, case, fields, profile), definition["id"])
                        self.assertIn(code, {issue["code"] for issue in issues})

    def test_conditional_fields_are_required_only_in_the_selected_branch(self):
        for platform in PLATFORMS:
            manifest, case, original_fields, profile = self.documents(platform)
            for definition in profile["fields"]:
                if not definition.get("when") or not definition.get("required") or definition.get("manual"):
                    continue
                with self.subTest(platform=platform, field=definition["id"]):
                    fields = copy.deepcopy(original_fields)
                    row = self.row(fields, definition)
                    row[definition["id"]].update(value=None, status="missing")
                    parents = [row.get(leaf["field"], fields["fields"].get(leaf["field"]))
                               for leaf in condition_leaves(definition["when"])]
                    for parent in parents:
                        parent.update(value="UNSELECTED-BRANCH", status="supported")
                    issues = self.field_issues(check_report(manifest, case, fields, profile), definition["id"])
                    self.assertNotIn("required_field_missing", {issue["code"] for issue in issues})
                    self.activate(fields, definition)
                    for parent in parents:
                        parent["status"] = "manual"
                    issues = self.field_issues(check_report(manifest, case, fields, profile), definition["id"])
                    self.assertIn("condition_unknown", {issue["code"] for issue in issues})

    def test_attachment_thresholds_keep_uncertainty_and_enforce_known_counts(self):
        for platform in PLATFORMS:
            original_manifest, case, original_fields, profile = self.documents(platform)
            for definition in profile["fields"]:
                if definition["kind"] != "attachments":
                    continue
                fields = copy.deepcopy(original_fields)
                self.activate(fields, definition)
                entry = self.row(fields, definition)[definition["id"]]
                # Inactive attachment branches were cleared by the fixture.
                path = f"synthetic-{definition['id']}{definition.get('extensions', ['.txt'])[0]}"
                material = next(item for item in original_manifest["materials"] if path in item["paths"])
                entry.update(value=[{"path": path, "evidence_id": material["evidence_id"]}],
                             evidence_refs=[material["evidence_id"]], status="supported")
                if definition.get("extensions"):
                    with self.subTest(platform=platform, attachment=definition["id"], constraint="extension"):
                        manifest, invalid_fields = copy.deepcopy((original_manifest, fields))
                        invalid_path = path + ".unsupported"
                        next(item for item in manifest["materials"] if path in item["paths"])["paths"] = [invalid_path]
                        self.row(invalid_fields, definition)[definition["id"]]["value"][0]["path"] = invalid_path
                        issues = check_report(manifest, case, invalid_fields, profile)["issues"]
                        self.assertTrue(any(issue["code"] == "attachment_extension"
                                            and f".{definition['id']}." in issue["path"] for issue in issues))
                if "size_limit" in definition:
                    limit = definition["size_limit"]
                    for size in (limit["bytes"] - 1, limit["bytes"], limit["bytes"] + 1):
                        with self.subTest(platform=platform, attachment=definition["id"], size=size):
                            manifest = copy.deepcopy(original_manifest)
                            next(item for item in manifest["materials"] if path in item["paths"])["size_bytes"] = size
                            issues = check_report(manifest, case, fields, profile)["issues"]
                            size_issues = [issue for issue in issues if issue["code"] == "attachment_size_limit"
                                           and f".{definition['id']}." in issue["path"]]
                            exceeds = size > limit["bytes"] if limit.get("inclusive", True) else size >= limit["bytes"]
                            self.assertEqual(exceeds, bool(size_issues))
                            if exceeds:
                                expected = "warning" if limit.get("basis") == "conservative_decimal" or limit.get("scope") == "unknown" else "error"
                                self.assertEqual(expected, size_issues[0]["level"])
                if "max_items" in definition:
                    with self.subTest(platform=platform, attachment=definition["id"], constraint="count"):
                        entry["value"] *= definition["max_items"] + 1
                        issues = self.field_issues(check_report(original_manifest, case, fields, profile), definition["id"])
                        self.assertIn("attachment_count_exceeded", {issue["code"] for issue in issues})

    def test_tencent_pdf_and_zip_use_their_respective_captured_limits(self):
        original_manifest, case, original_fields, profile = self.documents("tencent")
        attachment = original_fields["fields"]["attachments"]["value"][0]
        for extension, size, exceeds in ((".PDF", 9_999_999, False), (".pdf", 10_000_000, True),
                                          (".zip", 10_000_000, False), (".ZIP", 99_999_999, False),
                                          (".zip", 100_000_000, True)):
            with self.subTest(extension=extension, bytes=size):
                manifest, fields = copy.deepcopy((original_manifest, original_fields))
                path = "synthetic-attachment" + extension
                material = next(item for item in manifest["materials"] if item["evidence_id"] == attachment["evidence_id"])
                material.update(paths=[path], size_bytes=size)
                fields["fields"]["attachments"]["value"][0]["path"] = path
                issues = check_report(manifest, case, fields, profile)["issues"]
                size_issues = [issue for issue in issues if issue["code"] == "attachment_size_limit"]
                self.assertEqual(exceeds, bool(size_issues))
                if exceeds:
                    self.assertEqual("warning", size_issues[0]["level"])

    def test_360_mobile_privacy_hardware_and_sample_branches_require_distinct_fields(self):
        manifest, case, original_fields, profile = self.documents("360")
        mobile = {"mobile_model", "system_version", "app_package", "app_version", "app_download", "app_source"}
        hardware = {"device_name", "device_version", "software_name", "software_version"}
        expected = {
            "web漏洞": {"severity", "url"}, "android漏洞": {"severity"} | mobile,
            "iOS漏洞": {"severity"} | mobile, "智能硬件": {"severity"} | hardware,
            "PC客户端漏洞": {"severity"}, "威胁情报": {"severity"}, "大语言模型": {"severity"},
            "android隐私漏洞": {"severity"}, "iOS隐私漏洞": {"severity"}, "样本收集": {"sample_attachment"},
        }
        for category, required in expected.items():
            with self.subTest(category=category):
                fields = copy.deepcopy(original_fields)
                fields["fields"]["type_primary"]["value"] = category
                for definition in profile["fields"]:
                    if "when" in definition:
                        fields["fields"][definition["id"]].update(value=None, status="missing")
                    if definition["id"] == "type_secondary":
                        fields["fields"]["type_secondary"]["value"] = definition["options_by_parent"][category][0]
                issues = check_report(manifest, case, fields, profile)["issues"]
                missing = {issue["path"].split(".")[-1] for issue in issues if issue["code"] == "required_field_missing"}
                self.assertEqual(required, missing)

    def test_tencent_web_and_client_branches_preserve_independent_required_fields(self):
        manifest, case, original_fields, profile = self.documents("tencent")
        packet_ids = {"request_packet", "response_packet"}
        app_ids = {"app_name", "app_version", "app_description"}
        expected = {
            "Web漏洞": packet_ids, "PC客户端漏洞": app_ids, "移动客户端漏洞": app_ids,
            "安全情报": set(), "服务器漏洞": set(), "号码安全": set(), "通用软件": set(),
            "疑似BUG": set(), "其他": set(),
        }
        definitions = {definition["id"]: definition for definition in profile["fields"]}
        for category, required in expected.items():
            with self.subTest(category=category):
                fields = copy.deepcopy(original_fields)
                fields["fields"]["type_primary"]["value"] = category
                fields["fields"]["type_secondary"]["value"] = definitions["type_secondary"]["options_by_parent"][category][0]
                for field_id in packet_ids | app_ids:
                    fields["fields"][field_id].update(value=None, status="missing")
                output = render_report(manifest, case, fields, profile)
                issues = json.loads(output["review_issues.json"])["issues"]
                missing = {issue["path"].split(".")[-1] for issue in issues if issue["code"] == "required_field_missing"}
                self.assertEqual(required, missing)
                for field_id in packet_ids | app_ids:
                    self.assertEqual(field_id in required, f"### {definitions[field_id]['label']}\n" in output["report.md"])

        request = "POST /synthetic?a=1&a=2 HTTP/1.1\nHost: example.invalid\nContent-Length: 13\n\na=1&a=2&a=3&b"
        response = "HTTP/1.1 200 OK\nContent-Type: text/plain\nX-Test: SAME\nX-Test: SAME\n\n<SYNTHETIC>"
        original_fields["fields"]["request_packet"]["value"] = request
        original_fields["fields"]["response_packet"]["value"] = response
        report = render_report(manifest, case, original_fields, profile)["report.md"]
        for packet in (request, response):
            self.assertIn("```text\n" + packet + "\n```", report)
            self.assertEqual(1, report.count(packet))

    def test_sensitive_controls_remain_manual_and_private(self):
        controls = {"xiaomi": {"test_password", "captcha", "agreement"}, "ant": {"nickname", "phone", "agreement"},
                    "baidu": {"captcha", "agreement"}}
        for platform, manual_ids in controls.items():
            with self.subTest(platform=platform):
                manifest, case, fields, profile = self.documents(platform)
                for field_id in manual_ids:
                    fields["fields"][field_id].update(value="PRIVATE-CONTROL-SENTINEL", status="supported")
                output = render_report(manifest, case, fields, profile)
                issues = json.loads(output["review_issues.json"])["issues"]
                self.assertEqual(manual_ids, {issue["path"].split(".")[-1] for issue in issues if issue["code"] == "manual_value_present"})
                self.assertNotIn("PRIVATE-CONTROL-SENTINEL", output["report.md"])

    def test_xiaomi_and_oppo_attachment_formats_obey_the_captured_strict_20m_limit(self):
        extensions = {"xiaomi": (".docx", ".pdf", ".zip", ".mp4"),
                      "oppo": (".doc", ".docx", ".7z", ".zip", ".gz", ".bz2", ".xlsx", ".xls")}
        for platform, allowed in extensions.items():
            original_manifest, case, original_fields, profile = self.documents(platform)
            ref = original_fields["fields"]["attachments"]["value"][0]["evidence_id"]
            for extension in (*allowed, ".unsupported"):
                for size in (19_999_999, 20_000_000):
                    with self.subTest(platform=platform, extension=extension, size=size):
                        manifest, fields = copy.deepcopy((original_manifest, original_fields))
                        path = "synthetic-attachment" + extension.upper()
                        next(item for item in manifest["materials"] if item["evidence_id"] == ref).update(paths=[path], size_bytes=size)
                        fields["fields"]["attachments"]["value"][0]["path"] = path
                        issues = check_report(manifest, case, fields, profile)["issues"]
                        codes = {issue["code"] for issue in issues}
                        self.assertEqual(extension not in allowed, "attachment_extension" in codes)
                        size_issues = [issue for issue in issues if issue["code"] == "attachment_size_limit"]
                        self.assertEqual(size == 20_000_000, bool(size_issues))
                        if size_issues:
                            self.assertEqual("warning", size_issues[0]["level"])

    def test_ant_attachment_cap_is_inclusive_and_preserves_unknown_scope(self):
        original_manifest, case, fields, profile = self.documents("ant")
        ref = fields["fields"]["attachments"]["value"][0]["evidence_id"]
        for size in (19_999_999, 20_000_000, 20_000_001):
            with self.subTest(size=size):
                manifest = copy.deepcopy(original_manifest)
                next(item for item in manifest["materials"] if item["evidence_id"] == ref)["size_bytes"] = size
                issues = check_report(manifest, case, fields, profile)["issues"]
                size_issues = [issue for issue in issues if issue["code"] == "attachment_size_limit"]
                self.assertEqual(size > 20_000_000, bool(size_issues))
                self.assertIn("attachment_size_scope_unknown", {issue["code"] for issue in issues})
                if size_issues:
                    self.assertEqual("warning", size_issues[0]["level"])

    def test_oppo_combined_conditions_ignore_stale_business_selection_in_other_categories(self):
        manifest, case, original_fields, profile = self.documents("oppo")
        definitions = {field["id"]: field for field in profile["fields"]}
        cases = (("web漏洞", "app", {"domain"}), ("服务器漏洞", "app", {"domain"}),
                 ("安全情报", "web", {"domain"}), ("安全情报", "app", {"business_name"}),
                 ("隐私漏洞", "web", {"domain"}), ("隐私漏洞", "app", {"business_name"}),
                 ("AI大模型漏洞", "web", {"domain"}), ("AI大模型漏洞", "app", {"ai_package_name"}),
                 ("移动应用漏洞", "web", {"business_name"}), ("开发者APP漏洞", "web", {"developer_package_name"}),
                 ("终端安全漏洞", "web", {"terminal_business_type"}), ("IoT安全漏洞", "web", {"product_type", "iot_product_name"}))
        for category, business, required in cases:
            with self.subTest(category=category, business=business):
                fields = copy.deepcopy(original_fields)
                fields["fields"]["type_primary"]["value"] = category
                fields["fields"]["type_secondary"]["value"] = definitions["type_secondary"]["options_by_parent"][category][0]
                for definition in profile["fields"]:
                    if "when" in definition:
                        fields["fields"][definition["id"]].update(value=None, status="missing")
                fields["fields"]["business_type"].update(value=business, status="supported")
                issues = check_report(manifest, case, fields, profile)["issues"]
                missing = {issue["path"].split(".")[-1] for issue in issues if issue["code"] == "required_field_missing"}
                self.assertEqual(required, missing)
                fields["fields"]["domain"].update(value="DOMAIN-BRANCH-SENTINEL", status="supported")
                report = render_report(manifest, case, fields, profile)["report.md"]
                self.assertEqual("domain" in required, "DOMAIN-BRANCH-SENTINEL" in report)

        for category, unknown in (("安全情报", True), ("移动应用漏洞", False), ("web漏洞", False)):
            with self.subTest(category=category, business="manual"):
                fields = copy.deepcopy(original_fields)
                fields["fields"]["type_primary"]["value"] = category
                fields["fields"]["business_type"].update(value="web", status="manual")
                issues = self.field_issues(check_report(manifest, case, fields, profile), "domain")
                self.assertEqual(unknown, "condition_unknown" in {issue["code"] for issue in issues})

    def test_xiaomi_uncollected_child_mappings_warn_without_rejecting_every_child(self):
        manifest, case, fields, profile = self.documents("xiaomi")
        fields["fields"]["type_secondary"]["value"] = "Synthetic uncollected child"
        for category in ("服务指纹", "test_sunnan3_create", "垂直越权测试类型"):
            with self.subTest(category=category):
                fields["fields"]["type_primary"]["value"] = category
                issues = self.field_issues(check_report(manifest, case, fields, profile), "type_secondary")
                self.assertEqual([("parent_option_unknown", "warning")], [(issue["code"], issue["level"]) for issue in issues])
        fields["fields"]["type_primary"]["value"] = "WEB漏洞"
        issues = self.field_issues(check_report(manifest, case, fields, profile), "type_secondary")
        self.assertEqual([("invalid_child_option", "error")], [(issue["code"], issue["level"]) for issue in issues])

    def test_xiaomi_mobile_fields_replace_url_and_account_fields(self):
        manifest, case, original_fields, profile = self.documents("xiaomi")
        definitions = {field["id"]: field for field in profile["fields"]}
        for category in ("WEB漏洞", "移动应用漏洞", "移动终端安全漏洞"):
            with self.subTest(category=category):
                fields = copy.deepcopy(original_fields)
                fields["fields"]["type_primary"]["value"] = category
                fields["fields"]["type_secondary"]["value"] = definitions["type_secondary"]["options_by_parent"][category][0]
                for definition in profile["fields"]:
                    if "when" in definition:
                        fields["fields"][definition["id"]].update(value=None, status="missing")
                output = render_report(manifest, case, fields, profile)
                issues = json.loads(output["review_issues.json"])["issues"]
                missing = {issue["path"].split(".")[-1] for issue in issues if issue["code"] == "required_field_missing"}
                mobile = category != "WEB漏洞"
                self.assertEqual({"package_name", "component_name"} if mobile else {"url"}, missing)
                for field_id in ("url", "test_account", "test_password"):
                    self.assertEqual(not mobile, f"### {definitions[field_id]['label']}\n" in output["report.md"])

    def test_xiaomi_mobile_text_limits_use_utf16_without_truncating_the_report(self):
        manifest, case, original_fields, profile = self.documents("xiaomi")
        definitions = {field["id"]: field for field in profile["fields"]}
        for field_id, limit in (("package_name", 200), ("component_name", 300)):
            for extra in ("", "a"):
                with self.subTest(field=field_id, extra=extra):
                    fields = copy.deepcopy(original_fields)
                    self.activate(fields, definitions[field_id])
                    content = "😀" * (limit // 2) + extra
                    fields["fields"][field_id].update(value=content, status="supported",
                                                     evidence_refs=fields["fields"]["title"]["evidence_refs"])
                    output = render_report(manifest, case, fields, profile)
                    issues = self.field_issues(json.loads(output["review_issues.json"]), field_id)
                    self.assertEqual(bool(extra), "max_length_exceeded" in {issue["code"] for issue in issues})
                    self.assertIn(content, output["report.md"])

    def test_baidu_document_and_package_attachments_keep_distinct_inclusive_caps(self):
        original_manifest, case, original_fields, profile = self.documents("baidu")
        ref = original_fields["fields"]["attachments"]["value"][0]["evidence_id"]
        limits = {".docx": 8_000_000, ".doc": 8_000_000,
                  **{extension: 500_000_000 for extension in (".apk", ".ipa", ".aar", ".zip", ".jar", ".rar", ".7z")}}
        for extension, limit in limits.items():
            for size in (limit, limit + 1):
                with self.subTest(extension=extension, size=size):
                    manifest, fields = copy.deepcopy((original_manifest, original_fields))
                    path = "synthetic-attachment" + extension.upper()
                    next(item for item in manifest["materials"] if item["evidence_id"] == ref).update(paths=[path], size_bytes=size)
                    fields["fields"]["attachments"]["value"][0]["path"] = path
                    issues = check_report(manifest, case, fields, profile)["issues"]
                    self.assertNotIn("attachment_extension", {issue["code"] for issue in issues})
                    self.assertIn("attachment_size_scope_unknown", {issue["code"] for issue in issues})
                    size_issues = [issue for issue in issues if issue["code"] == "attachment_size_limit"]
                    self.assertEqual(size > limit, bool(size_issues))
                    if size_issues:
                        self.assertEqual("warning", size_issues[0]["level"])
        manifest, fields = copy.deepcopy((original_manifest, original_fields))
        next(item for item in manifest["materials"] if item["evidence_id"] == ref)["paths"] = ["synthetic.pdf"]
        fields["fields"]["attachments"]["value"][0]["path"] = "synthetic.pdf"
        self.assertIn("attachment_extension", {issue["code"] for issue in check_report(manifest, case, fields, profile)["issues"]})

    def test_baidu_text_inputs_enforce_dom_limits_but_editor_counter_only_warns(self):
        manifest, case, original_fields, profile = self.documents("baidu")
        for field_id, limit, level in (("title", 50, "error"), ("url", 500, "error"), ("details", 10_000, "warning")):
            for extra in ("", "a"):
                with self.subTest(field=field_id, extra=extra):
                    fields = copy.deepcopy(original_fields)
                    content = "x" * limit + extra
                    fields["fields"][field_id]["value"] = content
                    output = render_report(manifest, case, fields, profile)
                    issues = [issue for issue in self.field_issues(json.loads(output["review_issues.json"]), field_id)
                              if issue["code"] == "max_length_exceeded"]
                    self.assertEqual(bool(extra), bool(issues))
                    if extra:
                        self.assertEqual(level, issues[0]["level"])
                    self.assertIn(content, output["report.md"])


if __name__ == "__main__":
    unittest.main()
