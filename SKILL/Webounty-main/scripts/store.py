"""Single-writer publication of a session's observations, records, and Wiki pages.

All input and the proposed Corpus are checked before a recoverable file batch
is installed. Derived-cache failures cannot undo a committed observation.
"""

from __future__ import annotations

import copy
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import posixpath
import re

from discovery import _names
from conditions import known as _known
from page_checks import PageChecks
from publication import install, writer
from rag import CORRECTIONS, Corpus, RetrievalError, dependencies, digest, encode, ref_ids, signature
from evidence_io import FileCopy, scan
from telemetry import count, measure
from wiki_structure import navigation_paths


PAGE_KINDS = {"entity", "flow", "capability", "question", "chain"}
RETRIEVAL_FIELDS = ("summary", "questions", "keywords", "aliases", "retrieval")
PAGE_METADATA = {"id", "title", "kind", "parent_page_id", *RETRIEVAL_FIELDS}


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[\w][\w.-]*", value):
        raise RetrievalError("IDs must contain letters, numbers, underscores, dots, or hyphens")
    return value


def _json_bytes(value):
    return (encode(value) + "\n").encode("utf-8")


def _strings(mapping, name):
    if not isinstance(mapping, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                            for k, v in mapping.items()):
        raise RetrievalError(f"{name} must be an object of string values")


def _rows(batch, name):
    rows = batch.get(name, [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RetrievalError(f"{name} must be an array of objects")
    ids = [_identifier(row["id"]) for row in rows]
    if len(set(ids)) != len(ids):
        raise RetrievalError(f"duplicate {name} IDs in one publication")
    return rows


def _check_refs(refs, mapping, name):
    for rid in ref_ids(refs):
        if rid not in mapping:
            raise RetrievalError(f"{name}: missing reference {rid}")


def _validate_capability(row):
    if "capability" not in row:
        return
    capability = row["capability"]
    if not isinstance(capability, dict):
        raise RetrievalError("capability must be an object")
    for name in ("provides", "needs"):
        specs = capability.get(name, [])
        if not isinstance(specs, list):
            raise RetrievalError(f"capability.{name} must be an array")
        for spec in specs:
            if not isinstance(spec, dict) or not isinstance(spec.get("type"), str) or not spec["type"].strip():
                raise RetrievalError("a capability spec requires a nonempty type")
            aliases = spec.get("aliases", [])
            if not isinstance(aliases, list) or any(not isinstance(value, str) for value in aliases):
                raise RetrievalError("capability aliases must be strings")
            _strings(spec.get("constraints", {}), "capability constraints")


def _record_observations(state, seeds):
    pending, seen, observations = list(seeds), set(), set()
    while pending:
        rid = pending.pop()
        if rid in seen:
            continue
        seen.add(rid)
        row = state["records"][rid]
        observations.update(row.get("observation_refs", []))
        pending.extend(dependencies(row))
    return observations


def _verified_compatibility(provided, needed, link_conditions, chain_conditions):
    if not _names(provided).intersection(_names(needed)):
        raise RetrievalError("a verified link requires matching capability types or aliases")
    groups = [provided.get("constraints", {}), needed.get("constraints", {}), link_conditions, chain_conditions]
    for index, left in enumerate(groups):
        for right in groups[index + 1:]:
            for key in left.keys() & right.keys():
                if _known(left[key]) and _known(right[key]) and left[key] != right[key]:
                    raise RetrievalError(f"verified link has conflicting {key} constraints")
    for key, value in needed.get("constraints", {}).items():
        actual = provided.get("constraints", {}).get(key, "unknown")
        if not _known(value) or not _known(actual):
            raise RetrievalError(f"verified link has an unknown required constraint: {key}")


def _validate_chain(state, row):
    steps = row.get("steps", [])
    _check_refs(steps, state["records"], "chain steps")
    if row.get("status") not in {"candidate", "verified", "refuted", "needs_review"}:
        raise RetrievalError("invalid chain status")
    _strings(row.get("conditions", {}), "chain conditions")
    stale = row.get("status") == "needs_review"
    bindings = []
    for link in row.get("links", []):
        producer, consumer = link["producer_ref"], link["consumer_ref"]
        if producer not in steps or consumer not in steps:
            raise RetrievalError("chain link endpoints must belong to its steps")
        for rid, key, index_key in ((producer, "provides", "provide_index"),
                                    (consumer, "needs", "need_index")):
            index = link[index_key]
            specs = state["records"][rid].get("capability", {}).get(key, [])
            if type(index) is not int or index < 0 or (not stale and index >= len(specs)):
                raise RetrievalError(f"chain {index_key} does not address {rid}'s {key}")
        if link.get("assessment") not in {"candidate", "verified", "refuted"}:
            raise RetrievalError("invalid chain link assessment")
        _strings(link.get("conditions", {}), "chain link conditions")
        evidence = link.get("evidence_refs", [])
        _check_refs(evidence, state["observations"], "chain link evidence")
        if link["assessment"] == "verified" and not stale:
            if not evidence or not all(set(evidence) & _record_observations(state, [rid])
                                       for rid in (producer, consumer)):
                raise RetrievalError("a verified link needs observation evidence for both endpoints")
            if not link.get("conditions"):
                raise RetrievalError("a verified link needs explicit conditions")
            provided = state["records"][producer]["capability"]["provides"][link["provide_index"]]
            needed = state["records"][consumer]["capability"]["needs"][link["need_index"]]
            _verified_compatibility(provided, needed, link["conditions"], row.get("conditions", {}))
        bindings.append((producer, consumer, link["provide_index"], link["need_index"]))
    if row["status"] == "verified":
        if len(steps) < 2 or len(set(steps)) != len(steps):
            raise RetrievalError("a verified chain needs an ordered, noncyclic path")
        positions = {rid: index for index, rid in enumerate(steps)}
        if not bindings or len(set(bindings)) != len(bindings) or any(
                positions[producer] >= positions[consumer] for producer, consumer, _, _ in bindings):
            raise RetrievalError("verified chain links must form a topologically ordered dependency graph")
        if any(link["assessment"] != "verified" for link in row.get("links", [])):
            raise RetrievalError("a verified chain requires every included edge to be verified")
        covered = {(consumer, need_index) for _, consumer, _, need_index in bindings}
        for rid in steps:
            for index, _ in enumerate(state["records"][rid].get("capability", {}).get("needs", [])):
                if (rid, index) not in covered:
                    raise RetrievalError(f"verified chain has an unprovided input: {rid}.needs[{index}]")
        if not row.get("observation_refs"):
            raise RetrievalError("a verified chain requires final observation evidence")


def _validate_state(state):
    groups = ("records", "entities", "observations", "artifacts")
    all_ids = [rid for name in groups for rid in state[name]]
    if len(all_ids) != len(set(all_ids)):
        raise RetrievalError("IDs must be unique across records, entities, observations, and artifacts")
    for row in state["entities"].values():
        _check_refs(row.get("source_refs", []), state["records"], "entity sources")
        for field in ("owner_ref", "tenant_ref", "asset_ref"):
            _check_refs([row[field]] if row.get(field) else [], state["entities"], field)
    for row in state["observations"].values():
        _check_refs(row.get("subject_refs", []), state["entities"], "observation subjects")
    for row in state["records"].values():
        _check_refs(dependencies(row), state["records"], "record dependencies")
        _check_refs(row.get("subject_refs", []), state["entities"], "record subjects")
        _check_refs(row.get("observation_refs", []), state["observations"], "record observations")
        for ref in row.get("artifact_refs", []):
            _check_refs([ref["artifact_id"]], state["artifacts"], "record artifacts")
        _validate_capability(row)
    for row in state["records"].values():
        if row.get("kind") == "Chain":
            _validate_chain(state, row)


def _remember_change(previous, row):
    """History describes revisions; it is not a current supporting dependency."""
    if not row.get("change_reason"):
        return
    record_refs = set()
    for field in ("source_refs", "requires", "supporting_fact_ids"):
        record_refs.update(ref_ids(row.get(field, [])))
    entry = {"revision": row["revision"], "previous_status": previous.get("status", "unknown"),
             "previous_summary": previous.get("summary", ""), "change_reason": row["change_reason"],
             "record_refs": sorted(record_refs), "observation_refs": list(row.get("observation_refs", []))}
    row.setdefault("history", []).append(entry)


def _invalidate_dependents(state, changed, explicit, entities=()):
    from collections import defaultdict, deque

    affected = set(changed) | set(entities)
    for rid in changed:
        row = state["records"][rid]
        for field in (*CORRECTIONS, "contradicts", "contradicting_fact_ids"):
            affected.update(ref_ids(row.get(field, [])))
    dependents, invalidated = defaultdict(set), []
    for rid, row in state["records"].items():
        for ref in dependencies(row) | set(row.get("subject_refs", [])):
            dependents[ref].add(rid)
    pending = deque(sorted(affected))
    while pending:
        rid = pending.popleft()
        row = state["records"].get(rid)
        if row and row.get("kind") in {"Chain", "Capability", "Finding", "Fact", "Question", "Step"} and rid not in explicit:
            previous = dict(row)
            # Keep workflow/historical status on facts and questions. Basis validity
            # is independent of whether the author marked the task open or complete.
            row["basis_status"] = "needs_review"
            if row["kind"] in {"Chain", "Capability", "Finding"}:
                row["status"] = "needs_review"
            row["revision"] += 1
            row["change_reason"] = "Source records, conditions or counterevidence changed; review this judgment."
            _remember_change(previous, row)
            invalidated.append(rid)
        for dependent in sorted(dependents[rid] - affected):
            affected.add(dependent)
            pending.append(dependent)
    return invalidated


def _record_title(row):
    if row.get("title"):
        return row["title"]
    label = {"Goal": "目标", "Fact": "事实", "Step": "问题", "Finding": "发现", "Capability": "能力", "Chain": "候选链"}.get(row["kind"], "记录")
    return f"{label} · {row['id']}"


def _canonical_pages(pages):
    candidates = {}
    for page in pages.values():
        roots = ref_ids(page.get("record_refs", []))
        for rid in roots:
            priority = 0 if page.get("auto_record_ref") == rid else 1 if roots == [rid] else 2
            item = (priority, page["page_id"], page)
            if rid not in candidates or priority < candidates[rid][0]:
                candidates[rid] = item
    return {rid: item[2] for rid, item in candidates.items()}


def _reference(rid, state, canonical, directory="wiki/pages"):
    if rid in canonical:
        path = canonical[rid]["path"]
    elif rid in state["observations"]:
        path = state["artifacts"][state["observations"][rid]["artifact_id"]]["path"]
    elif rid in state["artifacts"]:
        path = state["artifacts"][rid]["path"]
    elif rid in state["records"] or rid in state["entities"]:
        path = "state.json"
    else:
        return f"`{rid}`"
    return f"[{rid}]({posixpath.relpath(path, directory)})"


def _is_reference(value, state):
    return isinstance(value, str) and any(value in state[group] for group in ("records", "observations", "artifacts"))


def _value_lines(value, state, canonical, indent=""):
    """Keep optional authored data, including false/unknown/negative qualifiers."""
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                yield f"{indent}- {key}："
                yield from _value_lines(item, state, canonical, indent + "  ")
            else:
                rendered = _reference(item, state, canonical) if _is_reference(item, state) else encode(item) if not isinstance(item, str) else item
                yield f"{indent}- {key}：{rendered}"
    elif isinstance(value, list):
        for item in value:
            yield from _value_lines(item, state, canonical, indent)
    else:
        rendered = _reference(value, state, canonical) if _is_reference(value, state) else encode(value) if not isinstance(value, str) else value
        yield f"{indent}- {rendered}"


def _status(row):
    value = row.get("status", "unknown")
    if row.get("kind") == "Goal":
        return f"`{value}`"
    if value == "verified":
        return "`verified`（作者记录的验证结论，仍受证据与条件限制）"
    if value in {"refuted", "disproved", "closed_for_conditions"}:
        return f"`{value}`（仅限已记录的命题与条件）"
    if value in {"needs_review", "review_required", "superseded", "corrected"}:
        return f"`{value}`（需复核，旧判断不能直接沿用）"
    return f"`{value}`（未验证为成立的漏洞或链）"


def _record_text(row, state, canonical=None):
    canonical = canonical or {}
    lines = [row.get("summary", ""), "", f"- 记录：`{row['id']}`", f"- 当前状态：{_status(row)}"]
    if row.get("basis_status") == "needs_review":
        lines.append("- 依据状态：待复核；历史作者状态不表示当前依据仍有效。")
    if row.get("conditions"):
        lines.append("- 适用条件：" + encode(row["conditions"]))
    optional = (
        ("hard_constraints", "用户硬约束（原文）"), ("next_action", "下一步"),
        ("active_question_ref", "当前问题引用"),
        ("question", "当前问题"), ("hypothesis", "假设（待判命题）"),
        ("expected", "支持判据（预期，不代表已经发生）"), ("falsifier", "反证判据（预期）"),
        ("test", "检查记录"), ("experiment", "实验记录"),
        ("actual_result", "实际结果记录"), ("result", "结果记录"), ("results", "结果记录"),
        ("observer", "观察器有效性"), ("assessment", "当前判断"),
        ("controls", "对照及有效性（按作者记录）"),
        ("counterevidence", "反证与竞争解释"),
        ("contradicted_by", "关联反证"), ("contradicting_fact_ids", "关联反证事实"),
        ("corrected_by", "关联更正"), ("correction_refs", "更正记录"),
        ("superseded_by", "替代本判断的记录"), ("contradicts", "本记录反驳的判断"),
        ("supporting_fact_ids", "支持事实"),
        ("unresolved_preconditions", "尚未满足的前提"), ("blockers", "阻断与待补证据"),
        ("limitations", "结论边界"), ("reopen_when", "重开条件"),
        ("impact", "影响及其验证状态"), ("retest", "复测记录"), ("retest_result", "复测结果记录"),
        ("change_reason", "本次更正或修订缘由"), ("history", "修订记录（历史判断，不作为当前结论）"),
    )
    for field, title in optional:
        if field not in row or row[field] in (None, "", [], {}):
            continue
        lines.extend(["", f"### {title}", ""])
        if field == "impact" and (not isinstance(row[field], dict) or row[field].get("status") != "verified"):
            lines.append("影响验证状态：未验证；保留作者记录的可能影响与限制。")
            lines.append("")
        lines.extend(_value_lines(row[field], state, canonical))
    if row.get("capability"):
        lines.extend(["", "### 能力与前提", ""])
        for field, title in (("provides", "可提供"), ("needs", "需要")):
            for spec in row["capability"].get(field, []):
                lines.append(f"- {title}: `{spec['type']}` — {spec.get('description', '')}")
                if spec.get("constraints"):
                    lines.append("  约束：" + encode(spec["constraints"]))
    if row.get("steps"):
        lines.extend(["", "### 组成记录与连接", ""])
        lines.append("- 依赖顺序：" + " → ".join(_reference(rid, state, canonical) for rid in row["steps"]))
    for link in row.get("links", []):
        lines.append(f"- 连接：{_reference(link['producer_ref'], state, canonical)} → "
                     f"{_reference(link['consumer_ref'], state, canonical)}；"
                     f"判断：`{link['assessment']}`{'（未验证）' if link['assessment'] == 'candidate' else ''}")
        details = {key: value for key, value in link.items() if key not in {"producer_ref", "consumer_ref", "assessment"}}
        lines.extend(_value_lines(details, state, canonical, "  "))
    if row.get("observation_refs") or row.get("artifact_refs"):
        lines.extend(["", "### 原始证据位置", ""])
    for oid in row.get("observation_refs", []):
        observation = state["observations"][oid]
        path = state["artifacts"][observation["artifact_id"]]["path"]
        lines.append(f"- 观察 [{oid}](../../{path})：{observation.get('summary', '')}")
    for ref in row.get("artifact_refs", []):
        artifact = state["artifacts"][ref["artifact_id"]]
        lines.append(f"- 原始文件 [{ref['artifact_id']}](../../{artifact['path']})")
    return "\n".join(lines).strip() + "\n"


def _index_section(row):
    if row["kind"] == "Goal":
        return "当前目标"
    if row["kind"] == "Chain":
        return "链与阻断"
    if row.get("status") in {"refuted", "disproved", "closed_for_conditions"} or row.get("assessment") == "refutes":
        return "负结果与关闭命题"
    if row["kind"] == "Finding":
        return "发现"
    if row["kind"] in {"Question", "Step"}:
        return "活动问题" if row.get("status") not in {"done", "closed", "passed", "resolved"} else "事实与其他记录"
    if row["kind"] == "Capability" or row.get("capability"):
        return "能力"
    return "事实与其他记录"


def _wiki_index(state, pages, checks):
    canonical = _canonical_pages(pages)
    navigation = navigation_paths(pages)
    sections = {name: [] for name in ("当前目标", "活动问题", "发现", "负结果与关闭命题", "能力", "链与阻断", "事实与其他记录")}
    labels = {"stale_source": "来源修订已变化", "new_candidates": "出现尚未审阅的相关资料",
              "removed_candidates": "已检查资料发生变化", "condition_change": "适用条件变化",
              "page_hash_mismatch": "页面内容与清单不一致", "block_hash_mismatch": "块内容与清单不一致",
              "required_block_review": "依赖的解释块待复核"}
    for rid, row in sorted(state["records"].items()):
        page = canonical.get(rid)
        title = page["title"] if page else _record_title(row)
        path = posixpath.relpath(page["path"], "wiki") if page else "../state.json"
        line = f"- [{title}]({path}) — {_status(row)}"
        if row.get("summary"):
            line += "；" + row["summary"].replace("\n", " ")
        if page:
            if page.get("parent_page_id"):
                line += "；目录：" + " → ".join(navigation[page["page_id"]])
            check = checks[page["page_id"]]
            if check["status"] != "ready":
                reasons = sorted({labels.get(issue["code"], issue["code"]) for issue in check["issues"]})
                line += "；**页面待复核：" + "、".join(reasons) + "**"
                changed = [item["id"] for item in check["new_candidates"] if item["kind"] == "record" and item["id"] != rid]
                if changed:
                    line += "；相关记录：" + "、".join(_reference(ref, state, canonical, "wiki") for ref in changed)
        sections[_index_section(row)].append(line)
    output = ["# webounty · 本会话 Wiki", "", "此页根据当前状态生成，仅作导航。每条记录链接到一个规范页；历史判断、候选与可能影响不因收录而成为已验证结论。", ""]
    for heading, rows in sections.items():
        if heading == "事实与其他记录" and not rows:
            continue
        output.extend([f"## {heading}", "", *(rows or ["暂无已记录条目。"]), ""])
    primary = {page["page_id"] for page in canonical.values()}
    others = [page for pid, page in pages.items() if pid not in primary]
    if others:
        output.extend(["## 业务与补充页面", ""])
        for page in sorted(others, key=lambda item: item["page_id"]):
            note = "；页面待复核" if checks[page["page_id"]]["status"] != "ready" else ""
            if page.get("parent_page_id"):
                note += "；目录：" + " → ".join(navigation[page["page_id"]])
            output.append(f"- [{page['title']}]({posixpath.relpath(page['path'], 'wiki')}){note}")
    return ("\n".join(output) + "\n").encode("utf-8")


def _authored_candidates(state, roots):
    """Only mark explicitly cited forward sources, never all related material, read."""
    pending, seen, result = list(roots), set(), []
    while pending:
        rid = pending.pop()
        if rid in seen:
            continue
        seen.add(rid)
        row = state["records"][rid]
        result.append(signature("record", row))
        pending.extend(dependencies(row))
        for oid in row.get("observation_refs", []):
            if oid not in seen:
                seen.add(oid)
                result.append(signature("observation", state["observations"][oid]))
        for eid in row.get("subject_refs", []):
            if eid not in seen:
                seen.add(eid)
                result.append(signature("entity", state["entities"][eid]))
    return sorted(result, key=encode)


def _page(state, supplied, canonical=None):
    pid = _identifier(supplied["id"])
    kind = supplied.get("kind", "question")
    if kind not in PAGE_KINDS:
        raise RetrievalError("invalid Wiki page kind")
    title = supplied.get("title", pid)
    if not isinstance(title, str):
        raise RetrievalError("Wiki page title must be a string")
    roots = list(dict.fromkeys(ref_ids(supplied.get("record_refs", []))))
    _check_refs(roots, state["records"], "Wiki page records")
    authored = supplied.get("blocks")
    generated = authored is None
    if authored is None:
        authored = [{"id": "B-" + rid, "title": _record_title(state["records"][rid]),
                     "text": _record_text(state["records"][rid], state, canonical), "source_refs": [rid]}
                    for rid in roots]
    blocks, bodies, ids = [], [], set()
    for raw in authored:
        bid = _identifier(raw["id"])
        if bid in ids:
            raise RetrievalError("duplicate Wiki block ID")
        ids.add(bid)
        refs = ref_ids(raw.get("source_refs", roots))
        _check_refs(refs, state["records"], "Wiki block sources")
        roots.extend(rid for rid in refs if rid not in roots)
        if not isinstance(raw["text"], str) or not isinstance(raw["title"], str):
            raise RetrievalError("Wiki block text and title must be strings")
        if re.search(r'<a\s+id=', raw["text"], re.I):
            raise RetrievalError("Wiki block anchors are generated; do not embed additional anchors")
        anchor = "block-" + bid
        body = f'<a id="{anchor}"></a>\n## {raw["title"]}\n\n{raw["text"].rstrip()}\n\n'
        bodies.append(body)
        subjects = sorted({eid for rid in refs for eid in state["records"][rid].get("subject_refs", [])})
        block = {"block_id": bid, "anchor": anchor, "title": raw["title"], "role": "explanation",
                 "content_hash": digest(body.encode()), "subject_refs": subjects,
                 "source_refs": [{"id": rid, "revision": state["records"][rid]["revision"]} for rid in refs],
                 "required_block_refs": copy.deepcopy(raw.get("required_block_refs", []))}
        if generated:
            block["representation"] = "record"
        for optional in ("knowledge", "conditions", "role", *RETRIEVAL_FIELDS):
            if optional in raw:
                block[optional] = copy.deepcopy(raw[optional])
        blocks.append(block)
    subjects = sorted({eid for rid in roots for eid in state["records"][rid].get("subject_refs", [])})
    content = (f"# {title}\n\n" + "".join(bodies)).encode("utf-8")
    page = {"page_id": pid, "kind": kind, "title": title, "path": f"wiki/pages/{pid}.md",
            "run_id": state["run_id"], "basis_state_revision": state["revision"],
            "record_refs": roots, "content_hash": digest(content), "subject_refs": subjects,
            "source_refs": [{"id": rid, "revision": state["records"][rid]["revision"]} for rid in roots],
            "conditions": copy.deepcopy(supplied.get("conditions", {})),
            "discovery_scope": {"subject_refs": subjects, "root_record_refs": roots},
            "checked_candidates": _authored_candidates(state, roots), "blocks": blocks}
    for optional in ("parent_page_id", *RETRIEVAL_FIELDS):
        if optional in supplied:
            page[optional] = copy.deepcopy(supplied[optional])
    if page.get("parent_page_id") is not None:
        _identifier(page["parent_page_id"])
    return page, content


def _page_metadata(current, previous, supplied):
    """Rename or move a page without declaring its old interpretation reviewed."""
    page = copy.deepcopy(previous)
    for field in PAGE_METADATA - {"id"}:
        if field in supplied:
            page[field] = copy.deepcopy(supplied[field])
    if page["kind"] not in PAGE_KINDS:
        raise RetrievalError("invalid Wiki page kind")
    if not isinstance(page["title"], str):
        raise RetrievalError("Wiki page title must be a string")
    if page.get("parent_page_id") is not None:
        _identifier(page["parent_page_id"])
    content = current.read_bytes(previous["path"])
    if page["title"] != previous["title"]:
        _, separator, body = content.partition(b"\n")
        content = f"# {page['title']}".encode("utf-8") + separator + body
        page["content_hash"] = digest(content)
    return page, content


class _ProposedCorpus(Corpus):
    def __init__(self, root, run_id, files, metrics=None):
        self.proposed_files = files
        super().__init__(root, run_id, lazy_pages=True, metrics=metrics)

    def read_bytes(self, relative):
        key = Path(relative).as_posix()
        if key not in self.proposed_files:
            return super().read_bytes(relative)
        path = self.path(relative)
        data = self.proposed_files[key]
        if isinstance(data, FileCopy):
            return data.source.read_bytes()
        self.read_files.setdefault(path, None)
        return data

    def source_path(self, relative):
        proposed = self.proposed_files.get(Path(relative).as_posix())
        return proposed.source if isinstance(proposed, FileCopy) else super().source_path(relative)

    def file_size(self, relative):
        proposed = self.proposed_files.get(Path(relative).as_posix())
        if proposed is not None:
            return proposed.metadata["bytes"] if isinstance(proposed, FileCopy) else len(proposed)
        return super().file_size(relative)

    def inspect_file(self, relative):
        proposed = self.proposed_files.get(Path(relative).as_posix())
        if isinstance(proposed, bytes):
            self.read_files.setdefault(self.path(relative), None)
            return {"sha256": digest(proposed), "bytes": len(proposed)}
        return super().inspect_file(relative)


def _prepare_publication(root, run_id, batch, current):
    supplied = {name: _rows(batch, name) for name in ("entities", "observations", "records", "pages")}
    state, manifest = copy.deepcopy(current.state), copy.deepcopy(current.manifest)
    state["revision"] += 1
    files, immutable = {}, set()
    changed_records, changed_entities = [], []
    for group, changed in (("entities", changed_entities), ("records", changed_records)):
        for raw in supplied[group]:
            rid = raw["id"]
            old = state[group].get(rid, {})
            row = {**copy.deepcopy(old), **copy.deepcopy(raw), "run_id": run_id,
                   "revision": old.get("revision", 0) + 1}
            row.setdefault("summary", "")
            if group == "records":
                row.setdefault("kind", "Fact")
                row.setdefault("status", "unknown")
                row.setdefault("subject_refs", [])
                row.setdefault("observation_refs", [])
                if "artifact_refs" not in raw and "observation_refs" in raw:
                    old_imports = {state["observations"].get(oid, {}).get("source_artifact_id")
                                   for oid in old.get("observation_refs", [])}
                    row["artifact_refs"] = [ref for ref in row.get("artifact_refs", [])
                                            if ref["artifact_id"] not in old_imports]
                if old:
                    row["change_reason"] = raw.get("change_reason", "Updated by an explicit publication.")
                if raw.get("reviewed") is True:
                    if not raw.get("change_reason"):
                        raise RetrievalError("reviewed records require a change_reason")
                    row.pop("basis_status", None)
                elif old.get("basis_status") == "needs_review":
                    row["basis_status"] = "needs_review"
                row.pop("reviewed", None)
                if row["kind"] == "Chain":
                    row["step_refs"] = list(row.get("steps", []))
                if old:
                    _remember_change(old, row)
            state[group][rid] = row
            changed.append(rid)
    for raw in supplied["observations"]:
        oid = raw["id"]
        if oid in state["observations"]:
            raise RetrievalError(f"observation {oid} is immutable; use a new ID")
        if not isinstance(raw["content"], dict):
            raise RetrievalError("observation content must be an object")
        content = {**copy.deepcopy(raw["content"]), "observation_id": oid, "run_id": run_id}
        index = {"id": oid, "revision": 1, "run_id": run_id, "summary": raw.get("summary", ""),
                 "subject_refs": raw.get("subject_refs", []), "artifact_id": "ART-" + oid, "line": 1}
        content["subject_refs"] = index["subject_refs"]
        if "excerpt_selectors" in raw:
            from excerpts import validate_selectors
            validate_selectors(raw["excerpt_selectors"])
            index["excerpt_selectors"] = copy.deepcopy(raw["excerpt_selectors"])
        if raw.get("source_path"):
            source = Path(raw["source_path"])
            if not source.is_absolute() or not source.is_file():
                raise RetrievalError("source_path must name an existing absolute file")
            if (source.resolve() in current.derived_paths or source.resolve() == root / "wiki/index.md"
                    or source.resolve().is_relative_to(root / "cache")):
                raise RetrievalError("derived session documents cannot be imported as original evidence")
            metadata = scan(source)
            aid, path = "SRC-" + oid, f"evidence/{oid}.source"
            if aid in state["artifacts"]:
                raise RetrievalError(f"artifact {aid} already exists")
            state["artifacts"][aid] = {"id": aid, "run_id": run_id, "kind": "source", "sealed": True,
                                       "path": path, **{key: metadata[key] for key in ("bytes", "sha256", "text_encoding")}}
            files[path] = FileCopy(source, metadata)
            immutable.add(path)
            index["source_artifact_id"] = aid
            content["source_artifact"] = {"artifact_id": aid, "path": path, "sha256": metadata["sha256"]}
        data, path = _json_bytes(content), f"evidence/{oid}.jsonl"
        index["content_hash"] = digest(data)
        if index["artifact_id"] in state["artifacts"]:
            raise RetrievalError(f"artifact {index['artifact_id']} already exists")
        state["artifacts"][index["artifact_id"]] = {
            "id": index["artifact_id"], "run_id": run_id, "kind": "observation", "sealed": True,
            "path": path, "bytes": len(data), "sha256": digest(data)}
        state["observations"][oid] = index
        files[path] = data
        immutable.add(path)
    for rid in changed_records:
        row = state["records"][rid]
        refs = row.setdefault("artifact_refs", [])
        known = {ref["artifact_id"] for ref in refs}
        for oid in row.get("observation_refs", []):
            aid = state["observations"].get(oid, {}).get("source_artifact_id")
            if aid and aid not in known:
                refs.append({"artifact_id": aid})
                known.add(aid)
    invalidated = _invalidate_dependents(state, changed_records, set(changed_records), changed_entities)
    changed_records.extend(invalidated)
    _validate_state(state)
    pages = {page["page_id"]: page for page in manifest["pages"]}
    page_inputs = {row["id"]: copy.deepcopy(row) for row in supplied["pages"]}
    explicitly_paged = {rid for page in supplied["pages"] for rid in page.get("record_refs", [])}
    for rid in changed_records:
        if rid in explicitly_paged or rid in invalidated:
            continue
        owned = [page for page in pages.values() if page.get("auto_record_ref") == rid]
        authored = [page for page in pages.values() if page.get("record_refs") == [rid]]
        if not owned and authored:
            # An author's page remains an authoring task. Keep it visibly stale
            # instead of overwriting its interpretation or creating a rival page.
            continue
        row = state["records"][rid]
        pid = owned[0]["page_id"] if owned else "WK-" + rid
        if pid in page_inputs:
            continue
        if pid in pages and not owned:
            raise RetrievalError(f"auto page {pid} conflicts with an authored page")
        kind = "chain" if row["kind"] == "Chain" else "capability" if row.get("capability") else "question"
        metadata = {key: copy.deepcopy(pages[pid][key]) for key in ("parent_page_id", *RETRIEVAL_FIELDS)
                    if pid in pages and key in pages[pid]}
        page_inputs[pid] = {**metadata, "id": pid, "kind": kind, "title": _record_title(row),
                            "record_refs": [rid], "auto_record_ref": rid}
    planning_pages = {**pages, **{pid: {**pages.get(pid, {}), **raw, "page_id": pid, "path": f"wiki/pages/{pid}.md"}
                                 for pid, raw in page_inputs.items()}}
    canonical = _canonical_pages(planning_pages)
    metadata_pages = set()
    for pid, raw in page_inputs.items():
        if pid in pages and set(raw) <= PAGE_METADATA:
            page, data = _page_metadata(current, pages[pid], raw)
            metadata_pages.add(pid)
        else:
            page, data = _page(state, raw, canonical)
        if raw.get("auto_record_ref"):
            page["auto_record_ref"] = raw["auto_record_ref"]
        pages[pid] = page
        files[page["path"]] = data
    try:
        navigation_paths(pages)
    except ValueError as exc:
        raise RetrievalError(str(exc)) from exc
    manifest["pages"] = list(pages.values())
    manifest["run_id"] = run_id
    files["state.json"] = _json_bytes(state)
    files[current.manifest_path] = _json_bytes(manifest)
    for path in immutable:
        if (root / path).exists():
            raise RetrievalError(f"refusing to replace immutable evidence {path}")
    return (supplied, state, pages, page_inputs, metadata_pages, files, immutable,
            changed_records, changed_entities, invalidated)


def publish(root, run_id, batch, metrics=None):
    """Serialize writers and recover any abandoned publication before reading."""
    root = Path(root).resolve(strict=True)
    if not isinstance(batch, dict):
        raise RetrievalError("publication must be an object")
    with writer(root, run_id), ExitStack() as resources:
        return _publish(root, run_id, batch, metrics, resources)


def _publish(root, run_id, batch, metrics, resources):
    with measure(metrics, "publish.load"):
        current = resources.enter_context(Corpus(root, run_id, lazy_pages=True, metrics=metrics))
        if current.load_issues:
            current.close()
            raise RetrievalError("refusing to publish with unreadable authoritative indexes: " + encode(current.load_issues))
        from retrieval_index import snapshot, sync_publication
        current.index_snapshot = snapshot(current)
    with measure(metrics, "publish.prepare"):
        (supplied, state, pages, page_inputs, metadata_pages, files, immutable,
         changed_records, changed_entities, invalidated) = _prepare_publication(root, run_id, batch, current)
    with measure(metrics, "publish.load"):
        proposed = resources.enter_context(_ProposedCorpus(root, run_id, files, metrics=metrics))
    with measure(metrics, "publish.validation"):
        package, issues = proposed.package(record_ids=changed_records, entity_ids=changed_entities,
                                           observation_ids=[row["id"] for row in supplied["observations"]],
                                           block_keys=[page["page_id"] + "/" + block["block_id"]
                                                       for pid, page in pages.items()
                                                       if pid in page_inputs and pid not in metadata_pages
                                                       for block in page["blocks"]], view="compact")
        # Moving or renaming a page checks its Markdown integrity, but does not
        # pretend to review its old interpretation or reread unchanged evidence.
        for pid in metadata_pages:
            proposed.ensure_page(pid)
            issues.extend(proposed.page_issues[pid])
            for block in pages[pid]["blocks"]:
                issues.extend(proposed.blocks[f'{pid}/{block["block_id"]}']["_issues"])
        # Publishing records can deliberately preserve disputed historical claims.
        allowed = {"stale_source", "condition_change", "new_candidates", "removed_candidates", "reasoning_review_required", "non_text_artifact",
                   "basis_review_required", "record_has_correction"}
        reviewed = {row["id"] for row in supplied["records"] if row.get("reviewed") is True}
        from discovery import _Sources
        checker_sources = _Sources(proposed)
        for rid in reviewed:
            invalid_basis = {"stale_source", "basis_review_required", "missing_source_record",
                             "missing_observation", "observation_unavailable", "source_cycle"}
            if any(item["code"] in invalid_basis for item in checker_sources.inspect(rid)["issues"]):
                raise RetrievalError("reviewed record still has unresolved source checks: " + rid)
        if package is None or any(issue["code"] not in allowed for issue in issues):
            raise RetrievalError("invalid publication: " + encode(issues))
    with measure(metrics, "publish.wiki_index"):
        checker = PageChecks(proposed, metrics)
        checks = checker.all()
        files["wiki/index.md"] = _wiki_index(state, pages, checks)
    with measure(metrics, "publish.write"):
        warnings = install(root, run_id, files, immutable, stable=current.stable)
    count(metrics, "publish_pages_loaded", len(current.loaded_pages | proposed.loaded_pages))
    actual_reads = set(current.read_files) | {
        path for path in proposed.read_files if path.is_relative_to(root)
        and path.relative_to(root).as_posix() not in proposed.proposed_files}
    count(metrics, "publish_evidence_files_read", len({path for path in actual_reads
                                                     if path.is_relative_to(root / "evidence")}))
    result = {"publication_status": "committed",
              "changed_record_ids": changed_records, "changed_entity_ids": changed_entities,
              "changed_page_ids": list(page_inputs),
              "content_changed_page_ids": [pid for pid in page_inputs if pid not in metadata_pages],
              "observation_ids": [row["id"] for row in supplied["observations"]],
              "state_revision": state["revision"], "needs_review_record_ids": invalidated,
              "needs_review_chain_ids": [rid for rid in invalidated if state["records"][rid]["kind"] == "Chain"]}
    if warnings:
        result["warnings"] = warnings
    # Authority is committed. Derived work must report its own failure without
    # turning a successful immutable observation into an apparent failed write.
    try:
        checker.save()
    except Exception as exc:
        result.setdefault("warnings", []).append({"code": "page_check_cache_failed", "detail": str(exc)})
    try:
        with measure(metrics, "publish.retrieval_index"):
            result["retrieval_index"] = sync_publication(current, root, run_id, result, metrics)
    except Exception as exc:
        result.setdefault("warnings", []).append({"code": "retrieval_index_update_failed", "detail": str(exc)})
    try:
        (root / "logs").mkdir(exist_ok=True)
        with (root / "logs/store.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(encode({"operation": "publish", "at": datetime.now(timezone.utc).isoformat(), **result}) + "\n")
    except Exception as exc:
        result.setdefault("warnings", []).append({"code": "store_log_failed", "detail": str(exc)})
    return result


def audit(root, run_id):
    """Inspect stored content and report author assertions separately from proof."""
    from wiki import audit as wiki_audit

    result = wiki_audit(root, run_id)
    corpus = Corpus(root, run_id)
    _validate_state(corpus.state)
    result["chains"] = [{"id": row["id"], "status": row["status"], "claims_verified": False}
                        for row in corpus.records.values() if row.get("kind") == "Chain"]
    result["state_revision"] = corpus.state["revision"]
    return result
