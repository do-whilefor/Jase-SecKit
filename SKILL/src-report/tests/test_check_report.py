"""Meaningful checker regressions using synthetic evidence only."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_report.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("check_report_under_test", SCRIPT)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def assessment_declarations(claim_id="RESULT-1"):
    # Synthetic claim deliberately stands in for all reviewed metric dimensions.
    return {
        "triage": {"status": "supported", "matched_rules": [], "reason": "Synthetic reviewed boundary, reproduction and impact.",
                   "basis": {key: [claim_id] for key in ("boundary", "reproducibility", "impact")}},
        "cvss31": {"vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                   "reason": "Synthetic evidence for a deterministic calculator fixture.",
                   "rationale": {metric: {"reason": "Synthetic reviewed metric basis.", "claim_refs": [claim_id]}
                                 for metric in ("AV", "AC", "PR", "UI", "S", "C", "I", "A")}},
    }


def synthetic_documents(root: str = "C:/synthetic-materials"):
    data = b"synthetic request and response\n"
    digest = hashlib.sha256(data).hexdigest()
    evidence_id = "E-" + digest[:16]
    manifest = {"schema_version": "1.0", "materials_root": root, "warnings": [], "materials": [
        {"evidence_id": evidence_id, "sha256": digest, "size_bytes": len(data),
         "kind": "text", "mime_type": "text/plain", "paths": ["request.txt"]}]}
    case = {"schema_version": "1.0", "case_id": "CASE-TEST", "version": 1,
            "src": "demo", "profile_version": "2026-10-03", "target": {},
            "identities": [], "prerequisites": [], "steps": [],
            "observed_results": [{"id": "RESULT-1", "text": "Observed response marker in supplied record",
                                  "verification": "observed", "evidence_refs": [evidence_id]}],
            "supported_impact": [],
            "evidence": [{"evidence_id": evidence_id, "locator": "line 1", "note": "response marker"}],
            "uncertainties": [],
            "semantic_review": {"status": "completed", "notes": [], "reviewed_evidence_refs": [evidence_id]}}
    case.update(assessment_declarations())
    fields = {"schema_version": "1.0", "case_id": case["case_id"], "case_version": 1,
              "src": "demo", "profile_version": "2026-10-03", "groups": {},
              "fields": {"title": {"value": "Synthetic draft", "status": "supported", "evidence_refs": [evidence_id]}},
              "redaction_review": {"status": "completed", "notes": []},
              "content_review": {"status": "completed", "notes": ["PoC selection and whole-report consistency reviewed."]}}
    profile = {"id": "demo", "version": "2026-10-03", "groups": {},
               "fields": [{"id": "title", "label": "Title", "kind": "text", "required": True}]}
    return manifest, case, fields, profile, data, evidence_id


class CheckReportTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.case, self.fields, self.profile, self.data, self.evidence_id = synthetic_documents()

    def check(self):
        return checker.check_report(self.manifest, self.case, self.fields, self.profile)

    def codes(self, review=None):
        return {issue["code"] for issue in (review or self.check())["issues"]}

    def record(self, value, status="supported", refs=None):
        return {"value": value, "status": status, "evidence_refs": [self.evidence_id] if refs is None else refs}

    def add_field(self, field_id, value, **definition):
        self.profile["fields"].append({"id": field_id, "label": field_id, "kind": "text", **definition})
        self.fields["fields"][field_id] = self.record(value)

    def test_checked_is_mechanical_not_semantic_verification(self):
        before = copy.deepcopy((self.manifest, self.case, self.fields, self.profile))
        review = self.check()
        self.assertEqual("checked", review["status"])
        self.assertFalse(review["semantic_verified"])
        self.assertEqual(before, (self.manifest, self.case, self.fields, self.profile))

    def test_missing_or_pending_content_review_keeps_legacy_draft_and_inputs(self):
        for review in (None, {"status": "pending", "notes": []}):
            with self.subTest(review=review):
                self.fields.pop("content_review", None)
                if review is not None:
                    self.fields["content_review"] = review
                before = copy.deepcopy((self.manifest, self.case, self.fields, self.profile))
                result = self.check()
                self.assertEqual("draft", result["status"])
                self.assertFalse(result["semantic_verified"])
                issue = next(item for item in result["issues"] if item["code"] == "content_review_pending")
                self.assertEqual("warning", issue["level"])
                self.assertEqual("fields.content_review", issue["path"])
                self.assertEqual(before, (self.manifest, self.case, self.fields, self.profile))

    def test_completed_content_review_requires_nonblank_notes_but_does_not_verify_them(self):
        for notes in ([], [""], ["  ", "\t\n"]):
            with self.subTest(notes=notes):
                self.fields["content_review"] = {"status": "completed", "notes": notes}
                result = self.check()
                self.assertEqual("draft", result["status"])
                issue = next(item for item in result["issues"] if item["code"] == "content_review_notes_missing")
                self.assertEqual("warning", issue["level"])
                self.assertEqual("fields.content_review.notes", issue["path"])
                self.assertNotIn("content_review_pending", self.codes(result))
        self.fields["content_review"]["notes"] = [" ", "Declaration only; the checker cannot assess these notes."]
        result = self.check()
        self.assertEqual("checked", result["status"])
        self.assertFalse(result["semantic_verified"])

    def test_invalid_content_review_shapes_raise_structure_error(self):
        malformed = [None, [], "completed", {}, {"status": "completed"}, {"notes": []}]
        malformed += [{"status": status, "notes": []} for status in (None, True, 1, [], {}, "checked", "")]
        malformed += [{"status": "completed", "notes": notes} for notes in (None, "note", {}, [None], [1], [[]])]
        for review in malformed:
            with self.subTest(review=review):
                self.fields["content_review"] = review
                with self.assertRaises(checker.StructureError):
                    self.check()

    def test_full_hash_evidence_ids_from_collision_fallback_are_accepted(self):
        full_id = "E-" + self.manifest["materials"][0]["sha256"]
        self.manifest["materials"][0]["evidence_id"] = full_id
        self.case["observed_results"][0]["evidence_refs"] = [full_id]
        self.case["evidence"][0]["evidence_id"] = full_id
        self.case["semantic_review"]["reviewed_evidence_refs"] = [full_id]
        self.fields["fields"]["title"]["evidence_refs"] = [full_id]
        self.assertEqual("checked", self.check()["status"])

    def test_required_missing_is_draft_error_not_structure_exception(self):
        del self.fields["fields"]["title"]
        review = self.check()
        self.assertEqual("needs_revision", review["status"])
        self.assertIn("required_field_missing", self.codes(review))

    def test_wrong_shapes_raise_structure_error(self):
        self.case["steps"] = "PoC contents must not be echoed"
        with self.assertRaises(checker.StructureError):
            self.check()

    def test_control_types_reject_wrong_union_members(self):
        for kind, value in (("text", True), ("multiline", ["http"]), ("richtext", True),
                            ("boolean", "true"), ("cascade", "Parent/Child"), ("attachments", ["picture.png"])):
            with self.subTest(kind=kind):
                self.profile["fields"][0]["kind"] = kind
                self.fields["fields"]["title"]["value"] = value
                self.assertIn("field_value_type", self.codes())

    def test_missing_and_duplicate_evidence_refs(self):
        self.case["observed_results"][0]["evidence_refs"] = ["E-unknown", "E-unknown"]
        codes = self.codes()
        self.assertTrue({"unknown_evidence_ref", "duplicate_evidence_ref", "observed_missing_locator"} <= codes)

    def test_observed_requires_nonempty_refs_and_locator(self):
        self.case["observed_results"][0]["evidence_refs"] = []
        self.assertIn("observed_missing_evidence", self.codes())
        self.case["observed_results"][0]["evidence_refs"] = [self.evidence_id]
        self.case["evidence"][0]["locator"] = ""
        self.assertIn("observed_missing_locator", self.codes())

    def test_multiple_locations_for_same_evidence_are_allowed(self):
        self.case["evidence"].append({"evidence_id": self.evidence_id, "locator": "line 2", "note": "another part"})
        self.assertEqual("checked", self.check()["status"])

    def test_repeated_identical_location_is_error(self):
        self.case["evidence"].append(copy.deepcopy(self.case["evidence"][0]))
        self.assertIn("duplicate_evidence_locator", self.codes())

    def test_profile_case_and_version_cannot_be_mixed(self):
        self.fields.update(case_id="OTHER", case_version=2, src="other-src", profile_version="old")
        codes = self.codes()
        self.assertTrue({"case_id_mismatch", "case_version_mismatch", "src_mismatch", "profile_version_mismatch"} <= codes)

    def test_utf16_length_counts_emoji_as_two(self):
        self.profile["fields"][0]["max_length"] = 3
        self.fields["fields"]["title"]["value"] = "A😀"
        self.assertNotIn("max_length_exceeded", self.codes())
        self.fields["fields"]["title"]["value"] = "AB😀"
        self.assertIn("max_length_exceeded", self.codes())
        self.assertEqual("AB😀", self.fields["fields"]["title"]["value"])

    def test_editor_counter_overflow_warns_without_weakening_dom_limits(self):
        definition = self.profile["fields"][0]
        definition["max_length"] = 3
        self.fields["fields"]["title"]["value"] = "AB😀"
        for basis, level, status in ((None, "error", "needs_revision"), ("dom_maxlength", "error", "needs_revision"),
                                     ("editor_counter", "warning", "draft")):
            with self.subTest(basis=basis):
                definition.pop("length_basis", None)
                if basis:
                    definition["length_basis"] = basis
                review = self.check()
                issue = next(issue for issue in review["issues"] if issue["code"] == "max_length_exceeded")
                self.assertEqual(level, issue["level"])
                self.assertEqual(status, review["status"])
                self.assertEqual("AB😀", self.fields["fields"]["title"]["value"])
        self.fields["fields"]["title"]["value"] = "A😀"
        self.assertEqual("checked", self.check()["status"])

    def test_length_basis_requires_a_known_basis_and_threshold(self):
        definition = self.profile["fields"][0]
        for basis, threshold in (("unknown", 3), (None, 3), (True, 3), ("editor_counter", None)):
            with self.subTest(basis=basis, threshold=threshold):
                definition["length_basis"] = basis
                definition.pop("max_length", None)
                if threshold is not None:
                    definition["max_length"] = threshold
                with self.assertRaises(checker.StructureError):
                    self.check()

    def test_supported_default_without_evidence_is_warning(self):
        self.fields["fields"]["title"]["evidence_refs"] = []
        review = self.check()
        self.assertEqual("draft", review["status"])
        self.assertIn("field_missing_evidence", self.codes(review))

    def test_poc_not_executed_stays_unverified(self):
        self.case["steps"] = [{"id": "POC-1", "text": "PoC intends to read an object; no run record",
                               "verification": "unverified", "evidence_refs": [self.evidence_id]}]
        self.case["uncertainties"] = [{"id": "U-1", "description": "No PoC execution evidence",
                                       "affects": ["POC-1"], "evidence_refs": [self.evidence_id]}]
        review = self.check()
        self.assertEqual("draft", review["status"])
        self.assertIn("claim_unverified", self.codes(review))
        self.assertEqual("unverified", self.case["steps"][0]["verification"])
        self.assertFalse(review["semantic_verified"])

    def test_conflict_without_uncertainty_requires_explanation(self):
        self.case["observed_results"][0]["verification"] = "conflicted"
        self.assertTrue({"claim_conflicted", "uncertainty_missing"} <= self.codes())

    def test_pending_semantic_and_redaction_reviews_are_not_success(self):
        self.case["semantic_review"]["status"] = "pending"
        self.fields["redaction_review"]["status"] = "pending"
        self.assertTrue({"semantic_review_pending", "redaction_review_pending"} <= self.codes())

    def test_group_conditions_are_evaluated_per_row_yes_no(self):
        self.profile["groups"] = {"requests": {"label": "Requests", "min_items": 1}}
        self.profile["fields"] += [
            {"id": "core", "label": "Core network", "kind": "select", "group": "requests", "required": True, "options": ["yes", "no"]},
            {"id": "proof", "label": "Proof", "kind": "text", "group": "requests", "required": True, "when": {"field": "core", "equals": "yes"}}]
        self.fields["groups"] = {"requests": [{"core": self.record("yes")}, {"core": self.record("no")}]}
        missing = [i["path"] for i in self.check()["issues"] if i["code"] == "required_field_missing"]
        self.assertEqual(["fields.groups.requests[0].proof"], missing)
        self.fields["groups"]["requests"][0]["proof"] = self.record("synthetic proof")
        self.assertNotIn("required_field_missing", self.codes())

    def test_jd_intrusion_core_no_still_keeps_screenshot_active(self):
        self.profile["groups"] = {"requests": {"label": "Requests", "min_items": 1}}
        self.profile["fields"] += [
            {"id": "harm", "label": "Harm", "kind": "select", "group": "requests", "required": True, "options": ["intrusion", "account"]},
            {"id": "core", "label": "Core", "kind": "select", "group": "requests", "when": {"field": "harm", "equals": "intrusion"}, "options": ["yes", "no"]},
            {"id": "screenshot", "label": "Screenshot", "kind": "attachments", "group": "requests", "required": None, "when": {"field": "harm", "equals": "intrusion"}},
            {"id": "credentials", "label": "Credentials", "kind": "text", "group": "requests", "required": True, "when": {"field": "harm", "equals": "account"}}]
        self.fields["groups"] = {"requests": [{"harm": self.record("intrusion"), "core": self.record("no"),
                                                 "screenshot": self.record([{"path": "request.txt", "evidence_id": self.evidence_id}])}]}
        self.assertNotIn("inactive_field_value", self.codes())
        self.fields["groups"]["requests"][0]["harm"] = self.record("account")
        self.assertIn("inactive_field_value", self.codes())
        self.assertIn("required_field_missing", self.codes())

    def test_unknown_condition_never_means_not_required(self):
        self.add_field("conditional", None, required=True, when={"field": "missing_source", "equals": "yes"})
        self.fields["fields"]["conditional"]["status"] = "not_applicable"
        self.assertIn("condition_unknown", self.codes())

    def test_complete_path_condition_does_not_match_just_leaf(self):
        self.add_field("category", "SSRF")
        self.add_field("flag", None, required=True, when={"field": "category", "equals": ["Intrusion", "SSRF"]})
        self.fields["fields"]["flag"]["status"] = "missing"
        self.assertNotIn("required_field_missing", self.codes())
        self.fields["fields"]["category"]["value"] = ["Intrusion", "SSRF"]
        self.assertIn("required_field_missing", self.codes())

    def test_condition_alternatives_match_whole_paths_and_each_rows_values(self):
        self.profile["groups"] = {"requests": {"label": "Requests", "min_items": 1}}
        self.profile["fields"] += [
            {"id": "category", "label": "Category", "kind": "cascade", "group": "requests"},
            {"id": "proof", "label": "Proof", "kind": "text", "group": "requests", "required": True,
             "when": {"field": "category", "in": [["Mobile", "Android"], ["Mobile", "iOS"]]}}]
        self.fields["groups"]["requests"] = [
            {"category": self.record(value, status)} for value, status in (
                (["Mobile", "Android"], "supported"), (["Mobile", "iOS"], "supported"),
                (["Android"], "supported"), (["Web", "iOS"], "supported"), (["Mobile", "iOS"], "manual"))]
        issues = self.check()["issues"]
        missing = [issue["path"] for issue in issues if issue["code"] == "required_field_missing"]
        self.assertEqual(["fields.groups.requests[0].proof", "fields.groups.requests[1].proof"], missing)
        self.assertTrue(any(issue["code"] == "condition_unknown" and issue["path"] == "fields.groups.requests[4].proof"
                            for issue in issues))

    def test_malformed_condition_alternatives_are_structure_errors(self):
        self.add_field("proof", None, when={"field": "title", "in": ["A", "B"]})
        for condition in ({"field": "title"}, {"field": "title", "equals": "A", "in": ["A"]},
                          {"field": "title", "in": []}, {"field": "title", "in": "A"},
                          {"field": "title", "in": [None]}, {"field": "title", "in": [[]]},
                          {"field": "title", "equals": {"unexpected": "A"}}):
            with self.subTest(condition=condition):
                self.profile["fields"][-1]["when"] = condition
                with self.assertRaises(checker.StructureError):
                    self.check()

    def test_compound_conditions_preserve_decisive_and_unknown_parent_states(self):
        self.add_field("left", None)
        self.add_field("right", None)
        self.add_field("proof", None, required=True)
        self.fields["fields"]["proof"]["status"] = "missing"
        cases = ((True, True, True, True), (True, False, False, True), (True, None, None, True),
                 (False, True, False, True), (False, False, False, False), (False, None, False, None),
                 (None, True, None, True), (None, False, False, None), (None, None, None, None))
        for left, right, all_result, any_result in cases:
            for operator, expected in (("all", all_result), ("any", any_result)):
                with self.subTest(left=left, right=right, operator=operator):
                    self.profile["fields"][-1]["when"] = {operator: [{"field": key, "equals": "yes"} for key in ("left", "right")]}
                    for key, value in (("left", left), ("right", right)):
                        self.fields["fields"][key] = self.record(None if value is None else "yes" if value else "no",
                                                                 "missing" if value is None else "supported")
                    codes = {issue["code"] for issue in self.check()["issues"] if issue["path"] == "fields.fields.proof"}
                    self.assertEqual(expected is True, "required_field_missing" in codes)
                    self.assertEqual(expected is None, "condition_unknown" in codes)

    def test_malformed_compound_conditions_are_rejected_before_evaluation(self):
        self.add_field("proof", None)
        leaf = {"field": "title", "equals": "yes"}
        for condition in ({"all": []}, {"any": []}, {"all": leaf}, {"any": ["title"]},
                          {"all": [leaf], "any": [leaf]}, {"all": [leaf], **leaf},
                          {"any": [leaf, {"all": []}]}, {"all": [{"field": "title"}]},
                          {"any": [dict(leaf, unexpected=True)]}):
            with self.subTest(condition=condition):
                self.profile["fields"][-1]["when"] = condition
                with self.assertRaises(checker.StructureError):
                    self.check()

    def test_unknown_group_and_minimum(self):
        self.profile["groups"] = {"requests": {"label": "Requests", "min_items": 1}}
        self.fields["groups"] = {"alien": []}
        self.assertTrue({"unknown_group", "group_min_items"} <= self.codes())

    def test_manual_null_is_allowed_but_automatic_agreement_is_not(self):
        self.add_field("agreement", None, kind="checkbox", required=True, manual=True)
        self.fields["fields"]["agreement"].update(status="manual", evidence_refs=[])
        review = self.check()
        self.assertEqual("draft", review["status"])
        self.assertIn("manual_action", self.codes(review))
        self.assertNotIn("required_field_missing", self.codes(review))
        self.assertNotIn("field_missing_evidence", self.codes(review))
        self.fields["fields"]["agreement"]["value"] = True
        self.assertIn("manual_value_present", self.codes())

    def test_password_manual_null_does_not_require_sharing_password(self):
        self.add_field("test_password", None, kind="password", required=True)
        self.fields["fields"]["test_password"].update(status="manual", evidence_refs=[])
        self.assertNotIn("required_field_missing", self.codes())
        self.assertIn("manual_fill", self.codes())

    def test_incomplete_enum_path_warns_but_invalid_complete_path_errors(self):
        self.add_field("category", ["server", "known"], kind="cascader", option_paths=[["server", "known"]], incomplete_paths=[["business", "complex"]])
        self.assertEqual("checked", self.check()["status"])
        self.fields["fields"]["category"]["value"] = ["business", "complex", "uncollected"]
        self.assertIn("option_path_unverified", self.codes())
        self.fields["fields"]["category"]["value"] = ["server", "invented"]
        self.assertIn("invalid_option_path", self.codes())
        self.fields["fields"]["category"]["value"] = ["business", "complex"]
        self.assertIn("incomplete_option_path", self.codes())

    def test_parent_child_option_consistency(self):
        self.add_field("first", "A", kind="select", options=["A", "B"])
        self.add_field("second", "b", kind="select", parent_field="first", options_by_parent={"A": ["a"], "B": ["b"]})
        self.assertIn("invalid_child_option", self.codes())
        self.fields["fields"]["first"]["value"] = "B"
        self.assertNotIn("invalid_child_option", self.codes())

    def test_attachment_traversal_absolute_and_windows_drive_are_rejected(self):
        self.add_field("attachment", [], kind="attachments")
        for unsafe in ("../request.txt", "sub/../../request.txt", "/request.txt", "C:\\request.txt", "\\\\server\\share\\file", "request.txt:stream"):
            with self.subTest(unsafe=unsafe):
                self.fields["fields"]["attachment"]["value"] = [{"path": unsafe, "evidence_id": self.evidence_id}]
                self.assertIn("unsafe_attachment_path", self.codes())

    def test_attachment_registration_extension_count_and_conservative_size(self):
        attachment = {"path": "request.txt", "evidence_id": self.evidence_id}
        self.add_field("attachment", [attachment, copy.deepcopy(attachment)], kind="attachments", max_items=1, extensions=[".png"],
                       size_limit={"label": "1M", "bytes": 1, "inclusive": True, "basis": "conservative_decimal", "scope": "per_file"})
        review = self.check()
        self.assertTrue({"attachment_extension", "attachment_count_exceeded", "duplicate_attachment", "attachment_size_limit"} <= self.codes(review))
        size_issues = [item for item in review["issues"] if item["code"] == "attachment_size_limit"]
        self.assertTrue(all(item["level"] == "warning" for item in size_issues))
        self.fields["fields"]["attachment"]["value"] = [{"path": "unregistered.txt", "evidence_id": self.evidence_id}]
        self.assertIn("attachment_not_registered", self.codes())

    def test_extension_size_rule_overrides_default_with_fallback_and_unknown_scope(self):
        attachment = {"path": "request.PDF", "evidence_id": self.evidence_id}
        self.manifest["materials"][0].update(paths=[attachment["path"]], size_bytes=20)
        self.add_field("attachment", [attachment], kind="attachments", size_limit={"bytes": 10},
                       size_limits_by_extension={".pdf": {"bytes": 20, "inclusive": True, "scope": "unknown"}})
        self.assertNotIn("attachment_size_limit", self.codes())
        self.assertIn("attachment_size_scope_unknown", self.codes())
        self.manifest["materials"][0]["size_bytes"] = 21
        issue = next(issue for issue in self.check()["issues"] if issue["code"] == "attachment_size_limit")
        self.assertEqual("warning", issue["level"])
        attachment["path"] = "request.txt"
        self.manifest["materials"][0].update(paths=[attachment["path"]], size_bytes=20)
        issue = next(issue for issue in self.check()["issues"] if issue["code"] == "attachment_size_limit")
        self.assertEqual("error", issue["level"])
        self.assertNotIn("attachment_size_scope_unknown", self.codes())

    def test_malformed_extension_size_limits_are_structure_errors(self):
        self.add_field("attachment", [], kind="attachments")
        for limits in ([], {}, {"pdf": {"bytes": 10}}, {".PDF": {"bytes": 10}},
                       {".pdf": {"bytes": -1}}, {".pdf": {"bytes": True}}, {".pdf": {"bytes": "10"}},
                       {".pdf": {"bytes": 10, "inclusive": "false"}}, {".pdf": {"bytes": 10, "scope": "total"}}):
            with self.subTest(limits=limits):
                self.profile["fields"][-1]["size_limits_by_extension"] = limits
                with self.assertRaises(checker.StructureError):
                    self.check()

    def test_mixed_attachment_formats_each_use_their_own_limit_regardless_of_order(self):
        self.manifest["materials"][0].update(paths=["proof.PDF", "proof.ZIP"], size_bytes=20)
        self.add_field("attachments", [], kind="attachments", extensions=[".pdf", ".zip"],
                       size_limits_by_extension={".pdf": {"bytes": 10}, ".zip": {"bytes": 100}})
        for paths in (("proof.PDF", "proof.ZIP"), ("proof.ZIP", "proof.PDF")):
            with self.subTest(paths=paths):
                self.fields["fields"]["attachments"]["value"] = [{"path": path, "evidence_id": self.evidence_id} for path in paths]
                issues = self.check()["issues"]
                self.assertEqual([f"fields.fields.attachments.value[{paths.index('proof.PDF')}]"],
                                 [issue["path"] for issue in issues if issue["code"] == "attachment_size_limit"])
                self.assertNotIn("attachment_extension", {issue["code"] for issue in issues})

    def test_verify_hash_missing_and_changed_originals(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.manifest["materials_root"] = temporary
            material = Path(temporary) / "request.txt"
            material.write_bytes(self.data)
            self.assertEqual([], checker.verify_material_files(self.manifest))
            material.write_bytes(b"changed")
            self.assertEqual("material_hash_mismatch", checker.verify_material_files(self.manifest)[0]["code"])
            material.unlink()
            self.assertEqual("material_file_unavailable", checker.verify_material_files(self.manifest)[0]["code"])

    def test_symlink_material_is_never_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "materials"
            root.mkdir()
            outside = Path(temporary) / "outside.txt"
            outside.write_bytes(self.data)
            link = root / "request.txt"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("OS account cannot create symlinks")
            self.manifest["materials_root"] = str(root)
            self.assertEqual("material_file_unavailable", checker.verify_material_files(self.manifest)[0]["code"])

    def test_cli_draft_errors_exit_zero_structural_errors_exit_two_without_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materials = root / "materials"
            materials.mkdir()
            self.manifest["materials_root"] = str(materials)
            (materials / "request.txt").write_bytes(self.data)
            del self.fields["fields"]["title"]
            paths = {}
            for name, document in (("manifest", self.manifest), ("case", self.case), ("fields", self.fields), ("profile", self.profile)):
                paths[name] = root / (name + ".json")
                paths[name].write_text(json.dumps(document), encoding="utf-8")
            command = [sys.executable, str(SCRIPT)]
            for name, path in paths.items():
                command += ["--" + name, str(path)]
            command += ["--output", str(root / "review.json")]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("needs_revision", json.loads((root / "review.json").read_text(encoding="utf-8"))["status"])
            sentinel = "PRIVATE-CREDENTIAL-MUST-NOT-BE-PRINTED"
            paths["case"].write_text('{"steps":"' + sentinel, encoding="utf-8")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(2, result.returncode)
            self.assertNotIn(sentinel, result.stdout + result.stderr)

    def test_review_writer_preserves_originals_and_all_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materials = root / "materials"
            materials.mkdir()
            self.manifest["materials_root"] = str(materials)
            material = materials / "request.txt"
            material.write_bytes(self.data)
            inputs = [root / (name + ".json") for name in ("manifest", "case", "fields", "profile")]
            for path in inputs:
                path.write_text("input sentinel", encoding="utf-8")
            for output in [material, materials / "new-review.json", *inputs]:
                with self.subTest(output=output.name), self.assertRaises(ValueError):
                    checker.write_review(self.check(), self.manifest, output, inputs)
            self.assertEqual(self.data, material.read_bytes())
            self.assertTrue(all(path.read_text(encoding="utf-8") == "input sentinel" for path in inputs))
            self.assertFalse((materials / "new-review.json").exists())
            output = root / "review.json"
            checker.write_review(self.check(), self.manifest, output, inputs)
            self.assertEqual("checked", json.loads(output.read_text(encoding="utf-8"))["status"])
            checker.write_review(self.check(), self.manifest, output, inputs)
            self.assertEqual("checked", json.loads(output.read_text(encoding="utf-8"))["status"])

    def test_atomic_review_write_failure_keeps_existing_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materials = root / "materials"
            materials.mkdir()
            self.manifest["materials_root"] = str(materials)
            output = root / "review.json"
            output.write_text("previous review", encoding="utf-8")
            with mock.patch.object(checker.os, "replace", side_effect=OSError("simulated failure")):
                with self.assertRaises(OSError):
                    checker.write_review(self.check(), self.manifest, output, [])
            self.assertEqual("previous review", output.read_text(encoding="utf-8"))
            self.assertEqual([], list(root.glob(".review-*.tmp")))

    def test_review_writer_rejects_hardlink_alias_of_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materials = root / "materials"
            materials.mkdir()
            self.manifest["materials_root"] = str(materials)
            source = root / "case.json"
            source.write_text("source", encoding="utf-8")
            alias = root / "review.json"
            try:
                os.link(source, alias)
            except OSError:
                self.skipTest("OS cannot create hardlinks")
            with self.assertRaises(ValueError):
                checker.write_review(self.check(), self.manifest, alias, [source])
            self.assertEqual("source", source.read_text(encoding="utf-8"))

    def test_review_writer_rejects_symlink_output_and_linked_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materials = root / "materials"
            materials.mkdir()
            self.manifest["materials_root"] = str(materials)
            source = root / "source.json"
            source.write_text("source", encoding="utf-8")
            link = root / "review.json"
            directory_link = root / "linked-dir"
            real_directory = root / "actual-dir"
            real_directory.mkdir()
            try:
                link.symlink_to(source)
                directory_link.symlink_to(real_directory, target_is_directory=True)
            except OSError:
                self.skipTest("OS account cannot create symlinks")
            for output in (link, directory_link / "new-review.json"):
                with self.assertRaises(ValueError):
                    checker.write_review(self.check(), self.manifest, output, [])
            self.assertEqual("source", source.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
