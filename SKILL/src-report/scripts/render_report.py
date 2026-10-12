#!/usr/bin/env python3
"""Render locally reviewed SRC fields; never execute or copy evidence files."""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from check_report import apply_material_verification, check_report, condition_state, verify_material_files
from assessment import BASE_METRICS, CLAIM_COLLECTIONS


STATUS = {
    "supported": "有材料支持（仍需语义复核）", "inferred": "合理推测",
    "missing": "待补充", "manual": "人工完成", "not_applicable": "不适用",
    "observed": "材料中已观察", "unverified": "未验证", "conflicted": "存在冲突",
}


def code(text):
    text = str(text).replace("\r", " ").replace("\n", " ")
    fence = "`" * (max([len(x) for x in re.findall(r"`+", text)] or [0]) + 1)
    return f"{fence} {text} {fence}"


def fenced(text):
    fence = "`" * max(3, max([len(x) for x in re.findall(r"`+", str(text))] or [0]) + 1)
    return f"{fence}text\n{text}\n{fence}"


def heading(text):
    return html.escape(str(text).replace("\r", " ").replace("\n", " "), quote=False)


def table_text(text):
    return str(text).replace("|", "&#124;").replace("\r", " ").replace("\n", "<br>")


def nest_markdown(text, parent_level):
    """Nest editor headings under the field without touching fenced code."""
    rows, headings, fence = str(text).splitlines(), [], None
    for index, line in enumerate(rows):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            run, tail = marker.groups()
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not tail.strip():
                fence = None
            continue
        match = re.match(r"^(#{1,6})\s+(.*)$", line) if fence is None else None
        if match:
            headings.append((index, len(match[1]), match[2]))
    if headings:
        first_level = min(level for _, level, _ in headings)
        for index, level, title in headings:
            rows[index] = "#" * min(6, parent_level + 1 + level - first_level) + " " + title
    return "\n".join(rows)


def field_block(definition, entry, level=3):
    entry = entry or {"value": None, "status": "manual" if definition.get("manual") else "missing"}
    value, status = entry.get("value"), entry.get("status", "missing")
    lines = [f"{'#' * level} {heading(definition['label'])}", ""]
    if definition.get("manual") or definition.get("read_only"):
        # Do not expose filled passwords, CAPTCHAs, FLAG values, or agreement state.
        lines += ["【人工完成或由平台显示；此处不填写实际凭证，也不代为勾选协议】", ""]
    elif value is None or value == "" or value == []:
        placeholder = {"manual": "人工补填", "not_applicable": "不适用"}.get(status, "待补充")
        lines += [f"【{placeholder}】", ""]
    elif definition.get("kind") == "attachments":
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            lines.append("【附件字段类型无效，见检查问题】")
        else:
            for item in value:
                lines.append(f"- 证据 {code(item.get('evidence_id', '未登记'))}；文件 {code(item.get('path', '未指定'))}。")
        lines.append("")
    elif isinstance(value, list):
        lines += [" → ".join(map(str, value)), ""]
    elif isinstance(value, bool):
        lines += ["是" if value else "否", ""]
    elif definition.get("kind") == "multiline":
        lines += [fenced(value), ""]
    elif definition.get("kind") == "richtext":
        lines += [nest_markdown(value, level), ""]
    else:
        lines += [html.escape(str(value), quote=False), ""]
    if status != "supported" and value not in (None, "", []) and not (definition.get("manual") or definition.get("read_only")):
        lines[2:2] = [f"状态：{STATUS.get(status, status)}", ""]
    refs = entry.get("evidence_refs", [])
    if refs:
        lines += ["证据：" + "、".join(code(ref) for ref in refs), ""]
    if entry.get("notes"):
        lines += ["备注：" + html.escape(str(entry["notes"]), quote=False), ""]
    return lines


def render_report(manifest, case, fields, profile, verify_files=True):
    """Return three output texts. Structural failures raise ValueError."""
    review = check_report(manifest, case, fields, profile)
    if verify_files:
        apply_material_verification(review, verify_material_files(manifest))
    levels = {item["level"] for item in review["issues"]}
    review["status"] = "needs_revision" if "error" in levels else "draft" if levels else "checked"
    review["semantic_verified"] = False
    lead_record = review["triage"]["explicit"] and not review["triage"]["passed"]
    title = "漏洞线索记录" if lead_record else fields.get("fields", {}).get("title", {}).get("value") or "漏洞报告草稿"
    lines = [f"# {heading(title)}", "", f"平台：{profile['id']} · 案件：{case['case_id']} · 版本：{case['version']}", "",
             f"配置版本：{profile['version']} · 程序检查状态：{review['status']}", "",
             "本报告由已有材料整理；生成完成和程序检查通过均不代表漏洞真实性或可提交性已获确认。", ""]
    if lead_record:
        lines += ["当前材料按线索保留，需补证后重新评估；线索状态不表示已排除漏洞。", ""]
    definitions = profile["fields"]
    locations = {"case": "报告事实", "fields": "平台字段", "manifest": "材料清单",
                 "case.semantic_review": "原件复核", "fields.redaction_review": "脱敏复核",
                 "fields.content_review": "内容复核", "case.triage": "漏洞筛选", "case.cvss31": "CVSS 评估"}
    claims = {claim["id"]: claim for collection in CLAIM_COLLECTIONS for claim in case[collection]}

    def claim_links(refs):
        return "；".join(ref + " → " + "、".join(claims.get(ref, {}).get("evidence_refs", [])) for ref in refs)

    lines += ["## 漏洞评估", ""]
    triage = case.get("triage")
    if triage is None:
        lines += ["筛选状态：未筛选的旧版草稿。", ""]
    else:
        label = "证据支持声明通过" if review["triage"]["passed"] else "待筛选" if triage.get("status") == "pending" else "仅线索（待补证）"
        lines += ["筛选状态：" + label + "。", "",
                  "规则编号：" + ("、".join(code(rule) for rule in triage.get("matched_rules", [])) or "未命中") + "。", "",
                  "筛选理由：" + html.escape(triage.get("reason", "") or "待补充。", quote=False), ""]
        for category, label in (("boundary", "安全边界"), ("reproducibility", "可复现性"), ("impact", "实际影响")):
            refs = triage.get("basis", {}).get(category, [])
            if refs:
                lines += [label + "依据：" + html.escape(claim_links(refs), quote=False), ""]
    score = review["cvss31"]
    if score is not None:
        lines += [f"CVSS 3.1 Base：{score['base_score']:.1f}（{score['severity']}）", "",
                  code(score["vector"]), "",
                  "评分说明：" + html.escape(case["cvss31"]["reason"], quote=False), "",
                  "CVSS 是技术严重性参考，不等于 SRC 平台等级；此结果仅核对依据声明及数学计算，未经动态漏洞真实性认证。", "",
                  "| 指标 | 取值 | 依据 | 事实 → 证据定位索引 |", "| --- | --- | --- | --- |"]
        for metric in BASE_METRICS:
            entry = case["cvss31"]["rationale"][metric]
            cells = (metric, score["metrics"][metric], entry["reason"], claim_links(entry["claim_refs"]))
            lines.append("| " + " | ".join(table_text(html.escape(str(cell), quote=False)) for cell in cells) + " |")
        lines += ["", "证据编号对应下方“证据定位”中的原件定位。", ""]
    else:
        lines += ["CVSS 3.1 Base：待评估（暂不输出数值）。", ""]
        if case.get("cvss31", {}).get("reason"):
            lines += ["评分说明：" + html.escape(case["cvss31"]["reason"], quote=False), ""]
    if lead_record:
        lines += ["## 材料观察", ""]
        observed = [claim for collection in CLAIM_COLLECTIONS for claim in case[collection] if claim["verification"] == "observed"]
        for claim in observed:
            lines += [f"- {code(claim['id'])} [{STATUS['observed']}] {html.escape(claim['text'], quote=False)}",
                      "  证据：" + "、".join(code(ref) for ref in claim["evidence_refs"])]
        lines += [""] if observed else ["尚无可确认的材料观察，需补充执行结果与对照证据。", ""]
    else:
        lines += ["## 平台字段", ""]

    def append_fields(group, row, index=None):
        for definition in definitions:
            if definition.get("group") != group:
                continue
            base = f"fields.groups.{group}[{index}]" if group else "fields.fields"
            label = f"{profile['groups'][group]['label']} / 第 {index + 1} 组 / " if group else ""
            locations[f"{base}.{definition['id']}"] = label + definition["label"]
            if lead_record:
                continue
            if condition_state(definition.get("when"), row, fields.get("fields", {})) is False:
                # An unexpected populated inactive field is still covered by checker issues.
                continue
            lines.extend(field_block(definition, row.get(definition["id"]), 4 if group else 3))

    append_fields(None, fields.get("fields", {}))
    for group, config in profile.get("groups", {}).items():
        locations[f"fields.groups.{group}"] = config["label"]
        rows = fields.get("groups", {}).get(group, [])
        if not rows and config.get("min_items", 0) == 0:
            continue
        if not lead_record:
            lines.extend([f"### {heading(config['label'])}", ""])
        if not rows and not lead_record:
            lines.extend(["【待补充：此组尚无材料】", ""])
        for index, row in enumerate(rows, 1):
            if not lead_record:
                lines.extend([f"第 {index} 组", ""])
            locations[f"fields.groups.{group}[{index - 1}]"] = f"{config['label']} / 第 {index} 组"
            append_fields(group, row, index - 1)

    pending, uncertain_claims = [], []
    linked_ids = {claim_id for item in case.get("uncertainties", []) for claim_id in item.get("affects", [])}
    for key, label in [("identities", "测试身份"), ("prerequisites", "前提"), ("steps", "步骤"),
                       ("observed_results", "实际结果"), ("supported_impact", "影响及其边界")]:
        for index, claim in enumerate(case.get(key, [])):
            locations[f"case.{key}[{index}]"] = f"{label} {claim['id']}"
            if claim["verification"] == "observed":
                continue
            uncertain_claims.append(claim)
            if claim["id"] in linked_ids:
                continue
            pending.append(f"- {code(claim['id'])} [{STATUS[claim['verification']]}] {html.escape(claim['text'], quote=False)}")
            if claim.get("evidence_refs"):
                pending.append("  证据：" + "、".join(code(x) for x in claim["evidence_refs"]))
    if case.get("evidence"):
        lines.extend(["## 证据定位", "", "| 证据 | 定位 | 观察备注 |", "| --- | --- | --- |"])
    for index, evidence in enumerate(case.get("evidence", [])):
        locations[f"case.evidence[{index}]"] = f"证据 {evidence['evidence_id']}"
        lines.append("| " + " | ".join(table_text(evidence.get(k, "")) for k in ("evidence_id", "locator", "note")) + " |")
    for index, item in enumerate(case.get("uncertainties", [])):
        locations[f"case.uncertainties[{index}]"] = f"待确认项 {item['id']}"
        pending.append(f"- {code(item['id'])} {html.escape(item['description'], quote=False)}")
        linked = [claim for claim in uncertain_claims if claim["id"] in item.get("affects", [])]
        if linked:
            pending.append("  关联论断：" + "、".join(f"{code(claim['id'])} [{STATUS[claim['verification']]}]" for claim in linked))
        refs = dict.fromkeys([*item.get("evidence_refs", []), *(ref for claim in linked for ref in claim["evidence_refs"])])
        if refs:
            pending.append("  证据：" + "、".join(code(ref) for ref in refs))
    for index, material in enumerate(manifest["materials"]):
        locations[f"manifest.materials[{index}]"] = f"材料 {material['evidence_id']}"
    # These reminders are already represented by field placeholders and claim statuses.
    shown = {"inferred_claim", "claim_unverified", "claim_conflicted", "unresolved_uncertainty",
             "inferred_field", "manual_action", "manual_fill"}
    prefixes = sorted(locations, key=len, reverse=True)
    for item in review["issues"]:
        if item["code"] in shown:
            continue
        path = item["path"]
        label = next((locations[prefix] for prefix in prefixes if path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[")), "材料检查")
        pending.append(f"- {heading(label)}：{html.escape(item['message'], quote=False)}")
    if pending:
        lines.extend(["", "## 待补证" if lead_record else "## 待确认与人工事项", "", *pending])
    if profile.get("source_urls") and not lead_record:
        lines.extend(["", "## 表单规则来源", ""])
        lines.extend(f"- {url}" for url in profile["source_urls"])

    attachment_lines = ["# 本地材料与附件清单", "",
                        "此清单可能包含原始文件名，仅供受控查阅。列出文件不等于已上传或已经脱敏。", "",
                        "## 已登记材料", ""]
    for material in manifest["materials"]:
        attachment_lines.extend([f"### {material['evidence_id']}", "",
                                 f"大小：{material['size_bytes']} 字节 · 类型：{material['kind']}", "",
                                 f"SHA256：{code(material['sha256'])}", ""])
        attachment_lines.extend(f"- {code(path)}" for path in material["paths"])
        attachment_lines.append("")
    attachment_lines.extend(["## 字段中引用的附件", ""])
    for definition in definitions:
        if definition["kind"] != "attachments":
            continue
        rows = fields.get("groups", {}).get(definition["group"], []) if definition.get("group") else [fields.get("fields", {})]
        for index, row in enumerate(rows, 1):
            attachments = row.get(definition["id"], {}).get("value") or []
            if not isinstance(attachments, list):
                continue
            for item in attachments:
                if not isinstance(item, dict):
                    continue
                attachment_lines.append(f"- {definition['label']} / 第{index}组：{code(item.get('path', ''))}；{code(item.get('evidence_id', ''))}")
    return {"report.md": "\n".join(lines).rstrip() + "\n",
            "attachments.md": "\n".join(attachment_lines).rstrip() + "\n",
            "review_issues.json": json.dumps(review, ensure_ascii=False, indent=2) + "\n"}


def write_outputs(contents, output_dir, materials_root, input_paths, overwrite=False):
    output_dir = Path(output_dir).resolve()
    root = Path(materials_root).resolve()
    if output_dir.is_relative_to(root):
        raise ValueError("输出目录不得位于原始材料目录内")
    inputs = {Path(path).resolve() for path in input_paths}
    if any(Path(name).name != name or "/" in name or "\\" in name for name in contents):
        raise ValueError("导出文件名不得包含路径段")
    targets = [output_dir / name for name in contents]
    for target in targets:
        if target.is_symlink() or target.resolve() in inputs:
            raise ValueError("输出不得覆盖输入文件或符号链接")
        if target.exists() and not overwrite:
            raise ValueError(f"已有导出文件 {target.name}；使用新目录或显式 --overwrite")
        if target.exists() and not target.is_file():
            raise ValueError("输出目标不是普通文件")
    output_dir.mkdir(parents=True, exist_ok=True)
    for target in targets:
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=output_dir, delete=False) as stream:
                temp_name = stream.name
                stream.write(contents[target.name])
            os.replace(temp_name, target)
        finally:
            if temp_name and Path(temp_name).exists():
                Path(temp_name).unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "case", "fields", "profile"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    inputs = [args.manifest, args.case, args.fields, args.profile]
    try:
        data = [json.loads(path.read_text(encoding="utf-8-sig")) for path in inputs]
        contents = render_report(*data)
        write_outputs(contents, args.output_dir, data[0]["materials_root"], inputs, args.overwrite)
        review = json.loads(contents["review_issues.json"])
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Cannot render report: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"status": review["status"], "issue_count": len(review["issues"]),
                      "outputs": list(contents)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
