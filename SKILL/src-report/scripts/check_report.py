#!/usr/bin/env python3
"""Validate a draft's structure and traceability; never prove a vulnerability.

Uses only Python 3.10+ standard library. check_report() is pure; the CLI also
checks registered material files. No material is executed or printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import sys
import tempfile
from typing import Any

from assessment import assess, validate_shapes


class StructureError(ValueError):
    """Input cannot safely be interpreted using the version 1.0 contract."""


VERIFICATIONS = {"observed", "inferred", "unverified", "conflicted"}
FIELD_STATUSES = {"supported", "inferred", "missing", "manual", "not_applicable"}
CLAIM_COLLECTIONS = ("identities", "prerequisites", "steps", "observed_results", "supported_impact")
ATTACHMENT_KINDS = {"attachment", "attachments", "image_upload", "file", "files", "upload"}


def _need(value: Any, typ: type, path: str) -> Any:
    if not isinstance(value, typ) or (typ is int and isinstance(value, bool)):
        raise StructureError(f"{path}: expected {typ.__name__}")
    return value


def _strs(value: Any, path: str) -> list[str]:
    _need(value, list, path)
    for i, item in enumerate(value):
        _need(item, str, f"{path}[{i}]")
    return value


def _versioned(value: Any, path: str) -> None:
    _need(value, dict, path)
    if value.get("schema_version") != "1.0":
        raise StructureError(f"{path}.schema_version: expected 1.0")


def _field_shape(value: Any, path: str) -> None:
    _need(value, dict, path)
    if value.get("status") not in FIELD_STATUSES:
        raise StructureError(f"{path}.status: invalid field status")
    if "value" not in value:
        raise StructureError(f"{path}.value: missing")
    raw = value["value"]
    if raw is not None and not isinstance(raw, (str, bool, list)):
        raise StructureError(f"{path}.value: expected string, boolean, array or null")
    if isinstance(raw, list):
        for i, member in enumerate(raw):
            if not isinstance(member, (str, dict)):
                raise StructureError(f"{path}.value[{i}]: expected string or attachment object")
            if isinstance(member, dict):
                _need(member.get("path"), str, f"{path}.value[{i}].path")
                _need(member.get("evidence_id"), str, f"{path}.value[{i}].evidence_id")
                if "purpose" in member:
                    _need(member["purpose"], str, f"{path}.value[{i}].purpose")
    _strs(value.get("evidence_refs"), f"{path}.evidence_refs")


def _condition_value(value: Any, path: str) -> None:
    if isinstance(value, list):
        if not _strs(value, path):
            raise StructureError(f"{path}: category path must not be empty")
    elif not isinstance(value, (str, bool)):
        raise StructureError(f"{path}: expected string, boolean or complete category path")


def _condition_shape(condition: Any, path: str) -> None:
    _need(condition, dict, path)
    if "all" in condition or "any" in condition:
        operator = "all" if "all" in condition else "any"
        if set(condition) != {operator}:
            raise StructureError(f"{path}: compound conditions cannot mix operators or field comparisons")
        children = _need(condition[operator], list, f"{path}.{operator}")
        if not children:
            raise StructureError(f"{path}.{operator}: must not be empty")
        for i, child in enumerate(children):
            _condition_shape(child, f"{path}.{operator}[{i}]")
        return
    if ("equals" in condition) == ("in" in condition):
        raise StructureError(f"{path}: expected exactly one of equals or in")
    operator = "equals" if "equals" in condition else "in"
    if set(condition) != {"field", operator}:
        raise StructureError(f"{path}: expected field and one comparison operator")
    _need(condition["field"], str, f"{path}.field")
    if operator == "equals":
        _condition_value(condition[operator], f"{path}.equals")
    else:
        options = _need(condition[operator], list, f"{path}.in")
        if not options:
            raise StructureError(f"{path}.in: must not be empty")
        for i, option in enumerate(options):
            _condition_value(option, f"{path}.in[{i}]")


def condition_matches(condition: dict, value: Any) -> bool:
    """Compare complete values; an equals array is one path, not alternatives."""
    return value == condition["equals"] if "equals" in condition else value in condition["in"]


def _size_limit_shape(value: Any, path: str) -> None:
    _need(value, dict, path)
    if _need(value.get("bytes"), int, f"{path}.bytes") < 0:
        raise StructureError(f"{path}.bytes: negative")
    if "inclusive" in value:
        _need(value["inclusive"], bool, f"{path}.inclusive")
    for key in ("label", "basis", "scope"):
        if key in value:
            _need(value[key], str, f"{path}.{key}")
    if value.get("scope", "per_file") not in {"per_file", "unknown"}:
        raise StructureError(f"{path}.scope: expected per_file or unknown")


def _validate_manifest(manifest: Any) -> None:
    _versioned(manifest, "manifest")
    _need(manifest.get("materials_root"), str, "manifest.materials_root")
    root = manifest["materials_root"]
    if not (Path(root).is_absolute() or PureWindowsPath(root).is_absolute()):
        raise StructureError("manifest.materials_root: expected absolute path")
    _need(manifest.get("warnings"), list, "manifest.warnings")
    _need(manifest.get("materials"), list, "manifest.materials")
    for i, item in enumerate(manifest["materials"]):
        base = f"manifest.materials[{i}]"
        _need(item, dict, base)
        for key in ("evidence_id", "sha256", "kind", "mime_type"):
            _need(item.get(key), str, f"{base}.{key}")
        if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise StructureError(f"{base}.sha256: expected lowercase SHA-256 hex")
        if item["evidence_id"] not in {"E-" + item["sha256"][:16], "E-" + item["sha256"]}:
            raise StructureError(f"{base}.evidence_id: does not match content hash")
        _need(item.get("size_bytes"), int, f"{base}.size_bytes")
        if item["size_bytes"] < 0:
            raise StructureError(f"{base}.size_bytes: must be non-negative")
        if not _strs(item.get("paths"), f"{base}.paths"):
            raise StructureError(f"{base}.paths: must not be empty")


def _validate_inputs(manifest: Any, case: Any, fields: Any, profile: Any) -> None:
    _validate_manifest(manifest)
    for value, label in ((case, "case"), (fields, "fields")):
        _versioned(value, label)
        for key in ("case_id", "src", "profile_version"):
            _need(value.get(key), str, f"{label}.{key}")
        version_key = "version" if label == "case" else "case_version"
        version = _need(value.get(version_key), int, f"{label}.{version_key}")
        if version < 1:
            raise StructureError(f"{label}.{version_key}: must be positive")
    _need(case.get("target"), dict, "case.target")
    for collection in CLAIM_COLLECTIONS:
        _need(case.get(collection), list, f"case.{collection}")
        for i, claim in enumerate(case[collection]):
            path = f"case.{collection}[{i}]"
            _need(claim, dict, path)
            for key in ("id", "text"):
                _need(claim.get(key), str, f"{path}.{key}")
            if claim.get("verification") not in VERIFICATIONS:
                raise StructureError(f"{path}.verification: invalid verification")
            _strs(claim.get("evidence_refs"), f"{path}.evidence_refs")
    _need(case.get("evidence"), list, "case.evidence")
    for i, evidence in enumerate(case["evidence"]):
        _need(evidence, dict, f"case.evidence[{i}]")
        for key in ("evidence_id", "locator", "note"):
            _need(evidence.get(key), str, f"case.evidence[{i}].{key}")
    _need(case.get("uncertainties"), list, "case.uncertainties")
    for i, uncertainty in enumerate(case["uncertainties"]):
        path = f"case.uncertainties[{i}]"
        _need(uncertainty, dict, path)
        for key in ("id", "description"):
            _need(uncertainty.get(key), str, f"{path}.{key}")
        _strs(uncertainty.get("affects", []), f"{path}.affects")
        _strs(uncertainty.get("evidence_refs"), f"{path}.evidence_refs")
    reviews = [(case, "semantic_review", "case"), (fields, "redaction_review", "fields")]
    if "content_review" in fields:
        reviews.append((fields, "content_review", "fields"))
    for document, key, label in reviews:
        review = _need(document.get(key), dict, f"{label}.{key}")
        status = _need(review.get("status"), str, f"{label}.{key}.status")
        if status not in {"pending", "completed"}:
            raise StructureError(f"{label}.{key}.status: expected pending or completed")
        _strs(review.get("notes"), f"{label}.{key}.notes")
    _strs(case["semantic_review"].get("reviewed_evidence_refs"), "case.semantic_review.reviewed_evidence_refs")
    validate_shapes(case, _need, _strs)
    _need(fields.get("fields"), dict, "fields.fields")
    for key, value in fields["fields"].items():
        _field_shape(value, f"fields.fields.{key}")
    _need(fields.get("groups"), dict, "fields.groups")
    for group_id, rows in fields["groups"].items():
        _need(rows, list, f"fields.groups.{group_id}")
        for i, row in enumerate(rows):
            _need(row, dict, f"fields.groups.{group_id}[{i}]")
            for key, value in row.items():
                _field_shape(value, f"fields.groups.{group_id}[{i}].{key}")
    _need(profile, dict, "profile")
    for key in ("id", "version"):
        _need(profile.get(key), str, f"profile.{key}")
    _need(profile.get("groups", {}), dict, "profile.groups")
    for group_id, group in profile.get("groups", {}).items():
        _need(group, dict, f"profile.groups.{group_id}")
        minimum = _need(group.get("min_items", 0), int, f"profile.groups.{group_id}.min_items")
        if minimum < 0:
            raise StructureError(f"profile.groups.{group_id}.min_items: negative")
    _need(profile.get("fields"), list, "profile.fields")
    seen = set()
    for i, field in enumerate(profile["fields"]):
        path = f"profile.fields[{i}]"
        _need(field, dict, path)
        for key in ("id", "label", "kind"):
            _need(field.get(key), str, f"{path}.{key}")
        if field["id"] in seen:
            raise StructureError(f"{path}.id: duplicate profile field")
        seen.add(field["id"])
        if field.get("required") is not None and not isinstance(field["required"], bool):
            raise StructureError(f"{path}.required: expected boolean or null")
        if "group" in field and field["group"] not in profile.get("groups", {}):
            raise StructureError(f"{path}.group: unknown group")
        for key in ("max_length", "max_items"):
            if key in field and (_need(field[key], int, f"{path}.{key}") < 0):
                raise StructureError(f"{path}.{key}: negative")
        if "length_basis" in field:
            if "max_length" not in field or field["length_basis"] not in ("dom_maxlength", "editor_counter"):
                raise StructureError(f"{path}.length_basis: expected dom_maxlength or editor_counter with max_length")
        for key in ("options", "extensions"):
            if key in field:
                _strs(field[key], f"{path}.{key}")
        for key in ("option_paths", "incomplete_paths"):
            if key in field:
                _need(field[key], list, f"{path}.{key}")
                for j, option in enumerate(field[key]):
                    _strs(option, f"{path}.{key}[{j}]")
        if "when" in field:
            _condition_shape(field["when"], f"{path}.when")
        if "options_by_parent" in field:
            options = _need(field["options_by_parent"], dict, f"{path}.options_by_parent")
            _need(field.get("parent_field"), str, f"{path}.parent_field")
            for parent, children in options.items():
                _strs(children, f"{path}.options_by_parent.{parent}")
        if "size_limit" in field:
            _size_limit_shape(field["size_limit"], f"{path}.size_limit")
        if "size_limits_by_extension" in field:
            limits = _need(field["size_limits_by_extension"], dict, f"{path}.size_limits_by_extension")
            if not limits:
                raise StructureError(f"{path}.size_limits_by_extension: must not be empty")
            for extension, limit in limits.items():
                if not isinstance(extension, str) or not re.fullmatch(r"\.[a-z0-9]+", extension):
                    raise StructureError(f"{path}.size_limits_by_extension: expected lowercase suffix keys such as .pdf")
                _size_limit_shape(limit, f"{path}.size_limits_by_extension.{extension}")


def _issue(code: str, level: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "level": level, "path": path, "message": message}


def _empty(value: Any) -> bool:
    return value is None or value == [] or (isinstance(value, str) and not value.strip())


def condition_state(condition: dict | None, row: dict, top_fields: dict | None = None) -> bool | None:
    """Keep absent or unconfirmed parent values unknown in checks and rendering."""
    if not condition:
        return True
    if "all" in condition or "any" in condition:
        operator = "all" if "all" in condition else "any"
        states = [condition_state(child, row, top_fields) for child in condition[operator]]
        decisive = operator == "any"
        if any(state is decisive for state in states):
            return decisive
        return None if None in states else not decisive
    record = row.get(condition["field"], (top_fields or {}).get(condition["field"]))
    if not record or _empty(record["value"]) or record["status"] in {"missing", "manual", "not_applicable"}:
        return None
    return condition_matches(condition, record["value"])


def _relative_key(value: str) -> str | None:
    """Portable conservative path policy, including Windows paths on POSIX."""
    if not value or "\x00" in value:
        return None
    normalized = value.replace("\\", "/")
    windows = PureWindowsPath(value)
    parts = normalized.split("/")
    if windows.drive or windows.root or normalized.startswith("/"):
        return None
    if any(part in {"", ".", ".."} or ":" in part for part in parts):
        return None
    return "/".join(parts)


def _status(issues: list[dict[str, str]]) -> str:
    if any(issue["level"] == "error" for issue in issues):
        return "needs_revision"
    return "draft" if issues else "checked"


def check_report(manifest: dict, case: dict, fields: dict, profile: dict) -> dict:
    """Return deterministic issues; raise StructureError for malformed shapes.

    A 'checked' result means these mechanical checks passed, never that an
    exploit worked, claims are true, or a platform will accept the submission.
    """
    _validate_inputs(manifest, case, fields, profile)
    issues: list[dict[str, str]] = []

    def add(code: str, level: str, path: str, message: str) -> None:
        issues.append(_issue(code, level, path, message))

    materials: dict[str, dict] = {}
    paths: dict[str, str] = {}
    for i, material in enumerate(manifest["materials"]):
        base = f"manifest.materials[{i}]"
        evidence_id = material["evidence_id"]
        if evidence_id in materials:
            add("duplicate_evidence_id", "error", base, "材料清单中的证据编号重复。")
        materials[evidence_id] = material
        for j, raw in enumerate(material["paths"]):
            key = _relative_key(raw)
            if key is None:
                add("unsafe_material_path", "error", f"{base}.paths[{j}]", "材料路径必须是根目录内的普通相对路径。")
            elif key in paths:
                add("duplicate_material_path", "error", f"{base}.paths[{j}]", "同一材料路径重复登记。")
            else:
                paths[key] = evidence_id
    for i, _ in enumerate(manifest["warnings"]):
        add("manifest_warning", "warning", f"manifest.warnings[{i}]", "材料登记器报告了警告，请核对材料清单。")

    def refs_check(refs: list[str], path: str) -> None:
        seen: set[str] = set()
        for i, ref in enumerate(refs):
            if ref in seen:
                add("duplicate_evidence_ref", "error", f"{path}[{i}]", "同一证据引用重复出现。")
            seen.add(ref)
            if ref not in materials:
                add("unknown_evidence_ref", "error", f"{path}[{i}]", "证据引用未在材料清单登记。")

    if fields["case_id"] != case["case_id"]:
        add("case_id_mismatch", "error", "fields.case_id", "字段数据与案例编号不一致。")
    if fields["case_version"] != case["version"]:
        add("case_version_mismatch", "error", "fields.case_version", "字段数据与案例版本不一致。")
    for label, document in (("case", case), ("fields", fields)):
        if document["src"] != profile["id"]:
            add("src_mismatch", "error", f"{label}.src", "目标 SRC 与所加载配置不一致。")
        if document["profile_version"] != profile["version"]:
            add("profile_version_mismatch", "error", f"{label}.profile_version", "平台配置版本不一致。")

    located: set[str] = set()
    locations: set[tuple[str, str]] = set()
    for i, evidence in enumerate(case["evidence"]):
        base = f"case.evidence[{i}]"
        refs_check([evidence["evidence_id"]], f"{base}.evidence_id")
        location = (evidence["evidence_id"], evidence["locator"])
        if location in locations:
            add("duplicate_evidence_locator", "error", base, "同一证据及定位重复出现。")
        locations.add(location)
        if evidence["locator"].strip():
            located.add(evidence["evidence_id"])
        else:
            add("missing_evidence_locator", "error", f"{base}.locator", "证据缺少行号、图片区域或其他可复核定位。")
        if not evidence["note"].strip():
            add("missing_evidence_observation", "warning", f"{base}.note", "应说明此定位实际观察到的内容。")

    claims = {claim["id"] for name in CLAIM_COLLECTIONS for claim in case[name]}
    uncertainty_ids: set[str] = set()
    covered: set[str] = set()
    global_uncertainty = False
    for i, uncertainty in enumerate(case["uncertainties"]):
        base = f"case.uncertainties[{i}]"
        if uncertainty["id"] in uncertainty_ids:
            add("duplicate_uncertainty_id", "error", f"{base}.id", "未决问题编号重复。")
        uncertainty_ids.add(uncertainty["id"])
        refs_check(uncertainty["evidence_refs"], f"{base}.evidence_refs")
        affected = uncertainty.get("affects", [])
        if not affected:
            global_uncertainty = True
        covered.update(affected)
        for j, claim_id in enumerate(affected):
            if claim_id not in claims:
                add("unknown_affected_claim", "error", f"{base}.affects[{j}]", "未决问题指向不存在的事实项。")
        add("unresolved_uncertainty", "warning", base, "此未决问题仍需随草稿交付；脚本不会自行消除它。")
    seen_claims: set[str] = set()
    for collection in CLAIM_COLLECTIONS:
        for i, claim in enumerate(case[collection]):
            base = f"case.{collection}[{i}]"
            claim_id = claim["id"]
            if not claim_id.strip() or claim_id in seen_claims:
                add("invalid_claim_id", "error", f"{base}.id", "事实项编号为空或重复。")
            seen_claims.add(claim_id)
            if not claim["text"].strip():
                add("empty_claim", "error", f"{base}.text", "事实项内容为空。")
            refs_check(claim["evidence_refs"], f"{base}.evidence_refs")
            verification = claim["verification"]
            if verification == "observed":
                if not claim["evidence_refs"]:
                    add("observed_missing_evidence", "error", base, "已观察事实必须引用证据，不能仅凭描述确认。")
                for j, ref in enumerate(claim["evidence_refs"]):
                    if ref not in located:
                        add("observed_missing_locator", "error", f"{base}.evidence_refs[{j}]", "已观察事实的证据必须在案例中给出定位。")
            elif verification == "inferred":
                add("inferred_claim", "warning", base, "此项仍为推测，不可在报告中改写为已观察事实。")
                if not claim["evidence_refs"]:
                    add("inference_missing_basis", "warning", base, "推测缺少证据依据。")
            else:
                add("claim_" + verification, "warning", base, "未验证或冲突内容必须保留相应标记。")
                if claim_id not in covered and not global_uncertainty:
                    add("uncertainty_missing", "warning", base, "应为未验证或冲突内容记录具体未决问题。")
    refs_check(case["semantic_review"]["reviewed_evidence_refs"], "case.semantic_review.reviewed_evidence_refs")
    if case["semantic_review"]["status"] == "pending":
        add("semantic_review_pending", "warning", "case.semantic_review", "宿主尚未完成原件语义复核；脚本无法证明漏洞成立。")
    else:
        reviewed = set(case["semantic_review"]["reviewed_evidence_refs"])
        used = {ref for name in CLAIM_COLLECTIONS for claim in case[name] for ref in claim["evidence_refs"]}
        if not used.issubset(reviewed):
            add("semantic_review_incomplete", "warning", "case.semantic_review", "语义复核的证据范围未覆盖全部事实引用。")
    if fields["redaction_review"]["status"] == "pending":
        add("redaction_review_pending", "warning", "fields.redaction_review", "分享内容尚需人工脱敏复核；脚本不提供自动脱敏保证。")
    content_review = fields.get("content_review")
    if content_review is None or content_review["status"] == "pending":
        add("content_review_pending", "warning", "fields.content_review", "尚未声明完成 PoC 取舍与全稿内容复核；请核对必要字段、证据边界及重复内容。")
    elif not any(note.strip() for note in content_review["notes"]):
        add("content_review_notes_missing", "warning", "fields.content_review.notes", "内容复核缺少记录；请说明 PoC 保留或省略的依据与全稿检查结果。")

    triage, cvss31 = assess(case, materials, located, add)
    if triage["passed"] and any(item["level"] == "error" and item["path"].startswith("manifest.materials[") for item in issues):
        triage["passed"], cvss31 = False, None
        add("triage_materials_invalid", "warning", "case.triage", "材料登记存在重复编号、重复路径或不安全路径，暂不接受筛选通过声明及数值评分。")
    lead_record = triage["explicit"] and not triage["passed"]
    definitions = {item["id"]: item for item in profile["fields"]}
    top = {key: item for key, item in definitions.items() if not item.get("group")}
    group_defs = {group_id: {key: item for key, item in definitions.items() if item.get("group") == group_id}
                  for group_id in profile.get("groups", {})}

    def find_record(field_id: str, row: dict) -> dict | None:
        return row[field_id] if field_id in row else fields["fields"].get(field_id)

    def validate_field(definition: dict, record: dict | None, row: dict, path: str) -> None:
        if record:
            refs_check(record["evidence_refs"], f"{path}.evidence_refs")
        value = record["value"] if record else None
        # A lead has no submission form yet, but populated values remain checked.
        if lead_record and _empty(value):
            return
        active = condition_state(definition.get("when"), row, fields["fields"])
        status = record["status"] if record else "missing"
        manual = bool(definition.get("manual") or definition.get("read_only"))
        if active is None:
            add("condition_unknown", "warning", path, "条件来源缺失或待人工确认，不能判定此字段无需填写。")
        elif not active:
            if not _empty(value):
                add("inactive_field_value", "warning", path, "条件未激活，此字段却有值；应核对是否来自其他请求组。")
            if not lead_record:
                return
        if manual:
            if not _empty(value):
                add("manual_value_present", "error", path, "人工操作或只读字段应保留空值，不能自动同意协议、填写验证码或生成验证结果。")
            if active is True or record:
                add("manual_action", "manual", path, "此项由用户在提交页面操作或读取，留空不会被当作缺失证据。")
            return
        if status == "manual":
            add("manual_fill", "manual", path, "此项留待人工补填；不表示平台已接受或无需填写。")
            if not _empty(value):
                add("manual_status_has_value", "warning", path, "人工补填状态已有值，应核对是否包含不宜分享的内容。")
        elif not lead_record and active is True and definition.get("required") is True and (not record or _empty(value) or status in {"missing", "not_applicable"}):
            add("required_field_missing", "error", path, "平台页面标记的必填字段尚未得到有效内容。")
        if record and status == "missing" and not _empty(value):
            add("missing_status_has_value", "warning", path, "标记缺失的字段仍有值，应保持状态与内容一致。")
        if record and status == "not_applicable" and active is True and not definition.get("required"):
            if not _empty(value):
                add("not_applicable_has_value", "warning", path, "不适用字段不应保留待提交内容。")
        if _empty(value):
            if record and status in {"supported", "inferred"}:
                add("empty_supported_field", "warning", path, "已支持或推测字段实际为空。")
            return
        kind = definition.get("kind")
        valid_kind = True
        if kind in {"text", "multiline", "richtext", "select", "password"}:
            valid_kind = isinstance(value, str)
        elif kind in {"boolean", "checkbox"}:
            valid_kind = isinstance(value, bool)
        elif kind in {"cascade", "cascader"}:
            valid_kind = isinstance(value, list) and all(isinstance(part, str) for part in value)
        elif kind in ATTACHMENT_KINDS:
            valid_kind = isinstance(value, list) and all(isinstance(item, dict) for item in value)
        if not valid_kind:
            add("field_value_type", "error", path, "字段内容的数据类型与平台控件类型不一致。")
            return
        if status == "supported" and not record["evidence_refs"]:
            add("field_missing_evidence", "warning", path, "字段标记有依据却没有证据引用；页面默认值不等于事实依据。")
        if status == "inferred":
            add("inferred_field", "warning", path, "该字段来自推测，提交前需人工确认。")
        if definition.get("kind") == "password" or "password" in definition["id"].lower():
            add("sensitive_password", "warning", path, "密码建议使用空值及人工补填状态，精确内容保留在受控原件。")
        if "max_length" in definition and isinstance(value, str):
            units = len(value.encode("utf-16-le", errors="surrogatepass")) // 2
            if units > definition["max_length"]:
                if definition.get("length_basis") == "editor_counter":
                    add("max_length_exceeded", "warning", path, "文本按 UTF-16 预检超过页面计数器提示值；编辑器可能采用不同计数方式，须在页面核对，不可静默截断。")
                else:
                    add("max_length_exceeded", "error", path, "文本超过 DOM maxlength 的 UTF-16 计数限制；必须人工编辑，不可静默截断。")
        if "options" in definition and value not in definition["options"]:
            add("invalid_option", "error", path, "所选值不在已采集的独立选项中。")
        if "option_paths" in definition:
            if not isinstance(value, list) or not all(isinstance(part, str) for part in value):
                add("invalid_option_path", "error", path, "多级选项必须使用完整路径数组。")
            elif value not in definition["option_paths"]:
                incomplete = definition.get("incomplete_paths", [])
                if value in incomplete:
                    add("incomplete_option_path", "error", path, "所选路径只是已知需继续展开的分类前缀，尚未选择最终分类。")
                elif any(value[:len(prefix)] == prefix for prefix in incomplete):
                    add("option_path_unverified", "warning", path, "此分类的后续选项采集不完整，须在页面核验。")
                else:
                    add("invalid_option_path", "error", path, "多级选项路径不在已采集范围，且不属于已知未完整展开的分支。")
        if "options_by_parent" in definition:
            parent = find_record(definition["parent_field"], row)
            parent_value = parent["value"] if parent else None
            if not isinstance(parent_value, str) or parent_value not in definition["options_by_parent"]:
                add("parent_option_unknown", "warning", path, "无法由当前父选项验证二级选项。")
            elif value not in definition["options_by_parent"][parent_value]:
                add("invalid_child_option", "error", path, "二级选项不属于所选一级分类。")
        if definition.get("kind") in ATTACHMENT_KINDS or (isinstance(value, list) and any(isinstance(item, dict) for item in value)):
            if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
                add("invalid_attachments", "error", path, "附件必须是包含相对路径及证据编号的对象数组。")
                return
            if "max_items" in definition and len(value) > definition["max_items"]:
                add("attachment_count_exceeded", "error", path, "附件数量超过页面已知限制。")
            seen_attachments = set()
            unknown_size_scope = False
            for i, attachment in enumerate(value):
                attachment_path = f"{path}.value[{i}]"
                key = _relative_key(attachment["path"])
                ref = attachment["evidence_id"]
                refs_check([ref], f"{attachment_path}.evidence_id")
                if key is None:
                    add("unsafe_attachment_path", "error", attachment_path, "附件路径越界、绝对路径或包含不安全路径段。")
                    continue
                if (key, ref) in seen_attachments:
                    add("duplicate_attachment", "error", attachment_path, "同一附件重复列出。")
                seen_attachments.add((key, ref))
                if paths.get(key) != ref:
                    add("attachment_not_registered", "error", attachment_path, "附件路径与材料清单的证据登记不一致。")
                if ref not in record["evidence_refs"]:
                    add("attachment_ref_missing", "warning", attachment_path, "附件证据编号未出现在此字段的证据引用列表。")
                extensions = definition.get("extensions")
                if extensions and Path(key).suffix.lower() not in {item.lower() for item in extensions}:
                    add("attachment_extension", "error", attachment_path, "附件扩展名不属于页面允许格式。")
                limit = definition.get("size_limits_by_extension", {}).get(Path(key).suffix.lower(), definition.get("size_limit"))
                unknown_size_scope |= bool(limit and limit.get("scope") == "unknown")
                if limit and ref in materials:
                    size = materials[ref]["size_bytes"]
                    exceeds = size > limit["bytes"] if limit.get("inclusive", True) else size >= limit["bytes"]
                    if exceeds:
                        # M/MB conversion and unknown scope are not measured server rules.
                        level = "warning" if limit.get("basis") == "conservative_decimal" or limit.get("scope") == "unknown" else "error"
                        add("attachment_size_limit", level, attachment_path, "附件达到或超过配置中的字节阈值；保守换算或未知作用范围需在页面核验。")
            if unknown_size_scope:
                add("attachment_size_scope_unknown", "warning", path, "页面未说明大小限制是单文件还是总量，不能据此保证附件被接受。")

    for field_id in fields["fields"]:
        if field_id not in top:
            add("unknown_field", "error", f"fields.fields.{field_id}", "字段不属于此平台顶层字段，或应放在重复组中。")
    for field_id, definition in top.items():
        validate_field(definition, fields["fields"].get(field_id), fields["fields"], f"fields.fields.{field_id}")
    for group_id in fields["groups"]:
        if group_id not in group_defs:
            add("unknown_group", "error", f"fields.groups.{group_id}", "此平台没有该重复字段组。")
    for group_id, group in profile.get("groups", {}).items():
        rows = fields["groups"].get(group_id, [])
        if not lead_record and len(rows) < group.get("min_items", 0):
            add("group_min_items", "error", f"fields.groups.{group_id}", "重复字段组少于要求的最小组数。")
        for i, row in enumerate(rows):
            base = f"fields.groups.{group_id}[{i}]"
            for field_id in row:
                if field_id not in group_defs[group_id]:
                    add("unknown_group_field", "error", f"{base}.{field_id}", "此字段不属于当前重复组。")
            for field_id, definition in group_defs[group_id].items():
                validate_field(definition, row.get(field_id), row, f"{base}.{field_id}")
    return {"schema_version": "1.0", "case_id": case["case_id"], "case_version": case["version"],
            "src": case["src"], "profile_version": case["profile_version"], "status": _status(issues),
            "semantic_verified": False, "triage": triage, "cvss31": cvss31, "issues": issues}


def _is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def apply_material_verification(review: dict, file_issues: list[dict]) -> None:
    """Withdraw evidence-gated results when registered originals fail validation."""
    review["issues"].extend(file_issues)
    if any(item["level"] == "error" for item in file_issues):
        if review["triage"]["passed"]:
            review["issues"].append(_issue("triage_materials_unverified", "warning", "case.triage",
                                         "原件完整性核验未通过，撤销本次筛选通过及评分结果；需重新登记并复核材料。"))
        review["triage"]["passed"] = False
        review["cvss31"] = None
    review["status"] = _status(review["issues"])


def verify_material_files(manifest: dict) -> list[dict[str, str]]:
    """Check every registered original without executing it or following links."""
    _validate_manifest(manifest)
    issues = []
    root = Path(manifest["materials_root"])
    try:
        if not root.is_absolute():
            raise OSError("non-native root")
        for part in reversed((root, *root.parents)):
            if _is_link(part):
                raise OSError("linked root")
        if not root.is_dir():
            raise OSError("not directory")
    except OSError:
        return [_issue("materials_root_unavailable", "error", "manifest.materials_root", "材料根目录不可用，或路径含符号链接/重解析点。")]
    resolved_root = root.resolve()
    for i, material in enumerate(manifest["materials"]):
        for j, relative in enumerate(material["paths"]):
            path = f"manifest.materials[{i}].paths[{j}]"
            key = _relative_key(relative)
            if key is None:
                issues.append(_issue("unsafe_material_path", "error", path, "材料路径必须位于根目录内。"))
                continue
            candidate = root
            try:
                for segment in key.split("/"):
                    candidate = candidate / segment
                    if _is_link(candidate):
                        raise OSError("linked material")
                candidate.resolve().relative_to(resolved_root)
                if not candidate.is_file():
                    raise OSError("not a file")
                flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(candidate, flags)
                with os.fdopen(fd, "rb") as source:
                    before = os.fstat(source.fileno())
                    if not stat.S_ISREG(before.st_mode):
                        raise OSError("not a regular file")
                    digest = hashlib.sha256()
                    size = 0
                    while block := source.read(1024 * 1024):
                        size += len(block)
                        digest.update(block)
                    after = os.fstat(source.fileno())
                if before.st_mtime_ns != after.st_mtime_ns or before.st_size != after.st_size:
                    issues.append(_issue("material_changed_during_read", "error", path, "原件在核验过程中变化，不能使用本次核验结果。"))
                if size != material["size_bytes"] or digest.hexdigest() != material["sha256"]:
                    issues.append(_issue("material_hash_mismatch", "error", path, "原件内容或大小与材料登记不一致，需要重新登记并复核。"))
            except (OSError, ValueError):
                issues.append(_issue("material_file_unavailable", "error", path, "原件不存在、不可读、越界或含符号链接/重解析点。"))
    return issues


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as source:
        return json.load(source)


def _safe_output_path(output: Path, root: Path, inputs: list[Path]) -> Path:
    destination = Path(os.path.abspath(output))
    # Check every existing ancestor before resolve/mkdir/replace can follow it.
    for component in reversed((destination, *destination.parents)):
        try:
            if _is_link(component):
                raise ValueError("output path contains a link or reparse point")
        except FileNotFoundError:
            continue
    canonical = destination.resolve(strict=False)
    root_absolute = Path(os.path.abspath(root))
    # Reject the lexical subtree even if the root itself is currently missing.
    for candidate_root in {root_absolute, root_absolute.resolve(strict=False)}:
        try:
            canonical.relative_to(candidate_root)
        except ValueError:
            continue
        raise ValueError("review output must be outside original materials")
    for source in inputs:
        if canonical == source.resolve(strict=False):
            raise ValueError("review output cannot replace an input document")
        if canonical.exists() and source.exists() and os.path.samefile(canonical, source):
            raise ValueError("review output cannot alias an input document")
    if canonical.exists() and not canonical.is_file():
        raise ValueError("review output must be a regular file")
    return canonical


def write_review(review: dict, manifest: dict, output: str | Path, inputs: list[Path]) -> Path:
    """Atomically write a review outside originals, without replacing inputs."""
    root = Path(manifest["materials_root"])
    destination = _safe_output_path(Path(output), root, inputs)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = _safe_output_path(destination, root, inputs)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", prefix=".review-", suffix=".tmp",
                                         dir=destination.parent, delete=False) as stream:
            temporary = stream.name
            json.dump(review, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        _safe_output_path(destination, root, inputs)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("manifest", "case", "fields", "profile", "output"):
        parser.add_argument("--" + key, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = _load(args.manifest)
        review = check_report(manifest, _load(args.case), _load(args.fields), _load(args.profile))
        apply_material_verification(review, verify_material_files(manifest))
        inputs = [Path(getattr(args, name)) for name in ("manifest", "case", "fields", "profile")]
        write_review(review, manifest, args.output, inputs)
    except (ValueError, OSError, UnicodeError) as exc:
        # Input text / paths may contain credentials, so do not echo exceptions.
        print(f"check_report: input/output failure ({type(exc).__name__}); check JSON structure and local paths.", file=sys.stderr)
        return 2
    print(f"check_report: status={review['status']}; issues={len(review['issues'])}; semantic_verified=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
