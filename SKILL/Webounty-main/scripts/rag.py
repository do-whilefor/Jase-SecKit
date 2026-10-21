#!/usr/bin/env python3
"""本轮 Wiki / 状态 / 封存观察检索；仅标准库，派生缓存限本会话。"""

from __future__ import annotations

import argparse
import base64
from collections import OrderedDict, defaultdict
from functools import wraps
import hashlib
import heapq
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

from methods import select_methods
from search_index import rank as rank_corpus, RANKING_VERSION
from ranking_context import mirror_owner
from telemetry import count, measure as stage_measure
from context_views import (compact_artifact, compact_block, compact_mandatory,
                           compact_navigation, compact_observation, compact_record)
from evidence_io import fingerprint, scan, text_chunks


def corpus_stage(name):
    """Timings are inclusive: package/index may contain verification work."""
    def decorate(function):
        @wraps(function)
        def measured(corpus, *args, **kwargs):
            metrics = kwargs.get("metrics", getattr(corpus, "metrics", None))
            with stage_measure(metrics, name):
                return function(corpus, *args, **kwargs)
        return measured
    return decorate


class RetrievalError(ValueError):
    """输入或运行边界不满足读取契约。"""


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ref_ids(refs):
    if isinstance(refs, (str, dict)):
        refs = [refs]
    return [r if isinstance(r, str) else r["id"] for r in refs]


RELATIONS = (
    "requires", "evidence_refs", "contradicted_by", "step_refs",
    "supporting_fact_ids", "contradicting_fact_ids", "corrected_by",
    "correction_refs", "superseded_by", "source_refs", "contradicts",
)
CORRECTIONS = ("contradicted_by", "corrected_by", "correction_refs", "superseded_by")


def dependencies(record):
    refs = set()
    for key in RELATIONS:
        values = record.get(key, [])
        refs.update(ref_ids([values] if isinstance(values, str) else values))
    if record.get("kind") == "Chain":
        refs.update(ref_ids(record.get("steps", [])))
        for link in record.get("links", []):
            refs.update(link[key] for key in ("producer_ref", "consumer_ref") if link.get(key))
    for entry in record.get("history", []):
        refs.update(ref_ids(entry.get("evidence_refs", [])))
    return refs


def signature(kind, obj):
    out = {"kind": kind, "id": obj["id"], "revision": obj["revision"]}
    if kind == "observation":
        out["content_hash"] = obj["content_hash"]
    return out


def words(text):
    terms = set(re.findall(r"[a-z0-9_/-]+", text.casefold()))
    for phrase in re.findall(r"[\u3400-\u9fff]+", text):
        terms.update(phrase[i:i + 2] for i in range(len(phrase) - 1))
    return terms


def text_values(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(text_values(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(text_values(v) for v in value)
    return str(value)


class Corpus:
    # Retain only small byte buffers. These are cache sizes, not input limits.
    CACHE_FILE_BYTES = 256 * 1024
    CACHE_TOTAL_BYTES = 2 * 1024 * 1024

    @corpus_stage("load")
    def __init__(self, root, run_id, *, lazy_pages=False, lazy_metadata=False, metrics=None, current_conditions=None):
        self.metrics = metrics
        if current_conditions is not None and (not isinstance(current_conditions, dict) or
                any(not isinstance(key, str) or not isinstance(value, str) for key, value in current_conditions.items())):
            raise RetrievalError("current_conditions must be an object of strings")
        self.current_conditions = dict(current_conditions or {})
        self.source_checker = None
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir() or not run_id:
            raise RetrievalError("root 必须是本轮资料目录，run_id 不可为空")
        self.run_id = run_id
        from publication import recover
        try:
            recover(self.root, run_id)
        except ValueError as exc:
            raise RetrievalError(str(exc)) from exc
        self.path_cache = {}
        self.metadata = None
        self.read_files = {}
        self.byte_cache = OrderedDict()
        self.cached_bytes = 0
        self.file_checks = {}
        self.total_bytes = 0
        self.load_issues = []
        self.page_issues = defaultdict(list)
        self.art_cache, self.obs_cache, self.check_cache, self.line_cache = {}, {}, {}, {}
        self.observation_status = {}
        self.closure_cache, self.knowledge_check_cache, self.reasoning_cache = {}, {}, {}
        self.loaded_pages = set()
        # The nested layout is canonical; the root manifest supports early fixtures.
        self.manifest_path = "wiki/manifest.json"
        if not self.path(self.manifest_path).exists():
            self.manifest_path = "manifest.json"
        if lazy_metadata:
            from metadata_cache import open_current
            cached = open_current(self)
            if cached is not None:
                cached.bind(self)
                if not lazy_pages:
                    for pid in self.pages:
                        self.ensure_page(pid)
                return
        self.state = self.read_json("state.json")
        try:
            self.manifest = self.read_json(self.manifest_path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            self.manifest = {"run_id": run_id, "pages": []}
            self.load_issues.append({"code": "manifest_unavailable", "detail": "Wiki 索引不可用，回退当前状态与已登记观察。"})
        if self.state.get("run_id") != run_id or self.manifest.get("run_id") != run_id:
            raise RetrievalError("run_id 与 state / manifest 不匹配")
        self.records = self.state["records"]
        self.entities = self.state["entities"]
        self.observations = self.state["observations"]
        self.artifacts = self.state["artifacts"]
        self.pages = {}
        self.blocks = {}
        self.subject_index = {}
        all_ids = set()
        for name, group in (("records", self.records), ("entities", self.entities),
                            ("observations", self.observations), ("artifacts", self.artifacts)):
            if not isinstance(group, dict):
                raise RetrievalError(f"{name} 不是有效的本轮索引")
            for key, value in group.items():
                if value.get("id") != key or key in all_ids:
                    raise RetrievalError("索引 ID 重复或不匹配")
                all_ids.add(key)
                if value.get("run_id", run_id) != run_id:
                    raise RetrievalError("索引混入其他 run_id")
                kind = {"records": "record", "entities": "entity", "observations": "observation"}.get(name)
                if kind:
                    for subject in value.get("subject_refs", []):
                        self.subject_index.setdefault(subject, set()).add((kind, key))
        for page in self.manifest["pages"]:
            pid = page["page_id"]
            if page.get("run_id") != run_id or pid in self.pages:
                raise RetrievalError("Wiki 页面 run_id 不匹配或 ID 重复")
            self.pages[pid] = page
            self.page_issues[pid] = []
            for block in page["blocks"]:
                key = f'{pid}/{block["block_id"]}'
                if key in self.blocks:
                    raise RetrievalError("Wiki 块 ID 重复")
                self.blocks[key] = {**block, "page_id": pid, "text": "", "_issues": []}
        self.record_dependencies = {rid: dependencies(row) for rid, row in self.records.items()}
        self.cycle_dependencies = dict(self.record_dependencies)
        for rid, row in self.records.items():
            contradicted = set(ref_ids(row.get("contradicts", [])))
            paired = {target for target in contradicted
                      if rid in ref_ids(self.records.get(target, {}).get("contradicted_by", []))}
            if paired:
                # NEW.contradicts=OLD and OLD.contradicted_by=NEW describe one
                # relation. Ignore only its explicit inverse for cycle detection;
                # source_refs/requires/history edges to OLD must still survive.
                self.cycle_dependencies[rid] = dependencies({
                    **row, "contradicts": sorted(contradicted - paired)})
        self.reverse_corrections = {}
        for rid, row in self.records.items():
            for field in (*CORRECTIONS, "contradicts"):
                for target in ref_ids(row.get(field, [])):
                    self.reverse_corrections.setdefault(target, set()).add(rid)
        self.derived_paths = {self.path(p["path"]) for p in self.pages.values()}
        self.derived_paths.update(self.path(p) for p in (
            "state.json", "manifest.json", "wiki/manifest.json", "wiki-knowledge.json"))
        self.derived_hashes = {p["content_hash"] for p in self.pages.values()}
        if lazy_metadata and not self.load_issues:
            from metadata_cache import save, open_current
            save(self)
            cached = open_current(self)
            if cached is not None:
                cached.bind(self)
        if not lazy_pages:
            for pid in self.pages:
                self.ensure_page(pid)

    @corpus_stage("verification")
    def ensure_page(self, pid):
        """Load and verify one page; ranking can reuse other pages' term projections."""
        if pid in self.loaded_pages:
            return
        page = self.pages[pid]
        issues = self.page_issues[pid]
        try:
            raw = self.read_bytes(page["path"])
            if digest(raw) != page["content_hash"]:
                issues.append({"code": "page_hash_mismatch", "page_id": pid})
            content = raw.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            content = ""
            issues.append({"code": "page_missing", "page_id": pid, "detail": str(exc)})
        anchors = list(re.finditer(r'<a id="([^"]+)"></a>', content))
        spans = {}
        for index, match in enumerate(anchors):
            anchor = match.group(1)
            if anchor in spans:
                issues.append({"code": "duplicate_anchor", "page_id": pid})
            end = anchors[index + 1].start() if index + 1 < len(anchors) else len(content)
            spans[anchor] = content[match.start():end]
        for block in page["blocks"]:
            bid = block["block_id"]
            body = spans.get(block["anchor"], "")
            block_issues = []
            if not body or digest(body.encode()) != block["content_hash"]:
                block_issues.append({"code": "block_hash_mismatch", "block_id": bid})
            self.blocks[f"{pid}/{bid}"].update(text=body, _issues=block_issues)
        self.loaded_pages.add(pid)

    def path(self, relative):
        relative = os.fspath(relative)
        if relative in self.path_cache:
            count(self.metrics, "paths_reused")
            return self.path_cache[relative]
        if os.path.isabs(relative):
            raise RetrievalError("资料路径必须相对本轮 root")
        resolved = os.path.realpath(os.path.join(self.root, relative))
        if os.path.commonpath((self.root, resolved)) != str(self.root):
            raise RetrievalError("资料路径或符号链接越出本轮 root")
        self.path_cache[relative] = Path(resolved)
        count(self.metrics, "paths_resolved")
        return self.path_cache[relative]

    def close(self):
        if self.metadata is not None:
            self.metadata.close()
            self.metadata = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def records_with_flag(self, flag):
        if self.metadata is not None:
            return [self.records[rid] for rid in sorted(self.metadata.links("flag")[flag])]
        kind, status = {"goals": ("Goal", "active"), "blockers": ("Step", "blocked")}[flag]
        return [row for row in self.records.values() if row.get("kind") == kind and row.get("status") == status]

    def source_blocks(self, refs):
        refs = set(refs)
        if self.metadata is not None:
            return self.metadata.union("source_block", refs)
        return {bid for bid, row in self.blocks.items() if refs.intersection(ref_ids(row.get("source_refs", [])))}

    def read_bytes(self, relative):
        p = self.path(relative)
        if p in self.byte_cache:
            self.byte_cache.move_to_end(p)
            return self.byte_cache[p]
        before = fingerprint(p)
        with p.open("rb") as stream:
            data = stream.read()
        if before != fingerprint(p):
            raise RetrievalError("资料在读取期间发生变化")
        self.total_bytes += len(data)
        self.read_files.setdefault(p, before)
        self.remember_bytes(p, data)
        count(self.metrics, "files_read")
        count(self.metrics, "bytes_read", len(data))
        return data

    def remember_bytes(self, path, data):
        if len(data) > self.CACHE_FILE_BYTES:
            return
        if path in self.byte_cache:
            self.cached_bytes -= len(self.byte_cache.pop(path))
        self.byte_cache[path] = data
        self.cached_bytes += len(data)
        while self.cached_bytes > self.CACHE_TOTAL_BYTES:
            _, previous = self.byte_cache.popitem(last=False)
            self.cached_bytes -= len(previous)

    def source_path(self, relative):
        return self.path(relative)

    def file_size(self, relative):
        return self.source_path(relative).stat().st_size

    def inspect_file(self, relative):
        """Hash selected originals incrementally; keep no full source byte copy."""
        path = self.source_path(relative)
        if path not in self.file_checks:
            result = scan(path)
            self.read_files.setdefault(path, result["fingerprint"])
            self.file_checks[path] = result
            self.total_bytes += result["bytes"]
            count(self.metrics, "files_read")
            count(self.metrics, "bytes_read", result["bytes"])
        return self.file_checks[path]

    def read_json(self, relative):
        return json.loads(self.read_bytes(relative))

    @corpus_stage("verification")
    def stable(self):
        # Detect ordinary concurrent changes; a caller still needs a single writer.
        from publication import pending
        if pending(self.root):
            return False
        for path, previous in self.read_files.items():
            if path.resolve() != path or not path.resolve().is_relative_to(self.root):
                return False
            try:
                count(self.metrics, "snapshot_files_checked")
                if fingerprint(path) != previous:
                    return False
            except OSError:
                return False
        return True

    @corpus_stage("verification")
    def artifact(self, aid):
        if aid in self.art_cache:
            return self.art_cache[aid]
        meta = self.artifacts.get(aid)
        issues, data = [], None
        if meta is None:
            issues.append({"code": "missing_reference", "artifact_id": aid})
        else:
            if not meta.get("sealed"):
                issues.append({"code": "artifact_unsealed", "artifact_id": aid})
            if meta.get("kind") in {"wiki", "report", "derived", "method"}:
                issues.append({"code": "derived_source", "artifact_id": aid})
            try:
                # Inline observation JSON is decoded only when needed. Large
                # external originals are verified without materializing bytes.
                if self.file_size(meta["path"]) <= self.CACHE_FILE_BYTES:
                    data = self.read_bytes(meta["path"])
                    checked_hash, checked_bytes = digest(data), len(data)
                else:
                    checked = self.inspect_file(meta["path"])
                    checked_hash, checked_bytes = checked["sha256"], checked["bytes"]
                count(self.metrics, "artifacts_verified")
                if checked_hash != meta["sha256"] or checked_bytes != meta["bytes"]:
                    issues.append({"code": "artifact_hash_mismatch", "artifact_id": aid})
                if self.path(meta["path"]) in self.derived_paths or checked_hash in self.derived_hashes:
                    issues.append({"code": "derived_source", "artifact_id": aid})
            except OSError:
                issues.append({"code": "artifact_missing", "artifact_id": aid})
        result = {"id": aid, "status": "unavailable" if issues else "ready",
                  "provenance": meta, "issues": issues, "data": data if not issues else None}
        self.art_cache[aid] = result
        return result

    def artifact_data(self, aid):
        artifact = self.artifact(aid)
        if artifact["status"] != "ready":
            return None
        return artifact["data"] if artifact["data"] is not None else self.read_bytes(artifact["provenance"]["path"])

    def artifact_window(self, aid, offset, length):
        if offset < 0 or length <= 0:
            raise ValueError("offset must be nonnegative and length must be positive")
        artifact = self.artifact(aid)
        row = {key: value for key, value in artifact.items() if key != "data"}
        if artifact["status"] != "ready":
            return row
        if offset > artifact["provenance"]["bytes"]:
            raise ValueError("offset is outside the artifact")
        with self.source_path(artifact["provenance"]["path"]).open("rb") as stream:
            stream.seek(offset)
            data = stream.read(length)
        count(self.metrics, "range_bytes_read", len(data))
        row["range"] = {"offset": offset, "length": len(data), "sha256": digest(data),
                        "total_bytes": artifact["provenance"]["bytes"],
                        "next_offset": offset + len(data), "eof": offset + len(data) >= artifact["provenance"]["bytes"]}
        try:
            row.update(content=data.decode("utf-8"), encoding="utf-8")
        except UnicodeError:
            row.update(content=base64.b64encode(data).decode("ascii"), encoding="base64")
        return row

    def source_chunks(self, oid):
        aid = self.observations[oid].get("source_artifact_id")
        if not aid:
            return
        if oid not in self.observation_status:
            self.observation(oid)
        if self.observation_status[oid] != "ready":
            return
        artifact = self.artifact(aid)
        if artifact["status"] != "ready" or artifact["provenance"].get("text_encoding") != "utf-8":
            return
        for locator, text in text_chunks(self.source_path(artifact["provenance"]["path"])):
            yield {"artifact_id": aid, **locator}, text

    def release_observation(self, oid):
        """Indexing one observation must not retain all previous raw payloads."""
        self.obs_cache.pop(oid, None)
        self.observation_status.pop(oid, None)
        aid = self.observations[oid]["artifact_id"]
        self.art_cache.pop(aid, None)
        self.line_cache.pop(aid, None)

    def observation(self, oid):
        if oid in self.obs_cache:
            return self._observation_match(oid, self.obs_cache[oid])
        index = self.observations[oid]
        artifact = self.artifact(index["artifact_id"])
        issues, raw = list(artifact["issues"]), None
        if index.get("source_artifact_id"):
            issues.extend(self.artifact(index["source_artifact_id"])["issues"])
        data = self.artifact_data(index["artifact_id"])
        if data is not None:
            lines = self.artifact_lines(index["artifact_id"], data)
            number = index.get("line", 0)
            if not isinstance(number, int) or not 1 <= number <= len(lines):
                issues.append({"code": "observation_location_missing", "id": oid})
            else:
                line = lines[number - 1]
                if digest(line) != index["content_hash"]:
                    issues.append({"code": "observation_hash_mismatch", "id": oid})
                else:
                    try:
                        raw = json.loads(line)
                        count(self.metrics, "observations_decoded")
                        if raw.get("run_id") != self.run_id:
                            raise RetrievalError("观察原件混入其他 run_id")
                        if raw.get("observation_id") != oid:
                            issues.append({"code": "observation_id_mismatch", "id": oid})
                        source = raw.get("source_artifact")
                        source_id = index.get("source_artifact_id")
                        if source_id or source is not None:
                            # The sealed observation binds the imported original;
                            # a valid hash on an unrelated artifact is insufficient.
                            meta = self.artifacts.get(source_id, {})
                            if (not source_id or not isinstance(source, dict)
                                    or source.get("artifact_id") != source_id
                                    or any(source.get(key) != meta.get(key) for key in ("path", "sha256"))):
                                issues.append({"code": "observation_source_mismatch", "id": oid})
                    except (json.JSONDecodeError, UnicodeError):
                        issues.append({"code": "observation_parse_error", "id": oid})
        out = {"id": oid, "revision": index["revision"], "index": index,
               "status": "unavailable" if issues else "ready", "raw": raw if not issues else None,
               "provenance": {"artifact_id": index["artifact_id"],
                              "path": self.artifacts.get(index["artifact_id"], {}).get("path"),
                              "line": index.get("line"), "content_hash": index["content_hash"]},
                "issues": issues}
        if out["status"] == "ready" and index.get("excerpt_selectors"):
            from excerpts import observation_excerpts
            out["excerpts"] = observation_excerpts(self, out)
        self.observation_status[oid] = out["status"]
        if self.artifacts.get(index["artifact_id"], {}).get("bytes", 0) <= self.CACHE_FILE_BYTES:
            self.obs_cache[oid] = out
        return self._observation_match(oid, out)

    def _observation_match(self, oid, observation):
        # Source windows belong to the current query, never the observation cache.
        hit = getattr(self, "retrieval_source_matches", {}).get(oid)
        if observation["status"] == "ready" and hit is not None:
            return {**observation, "source_match": dict(hit)}
        return observation

    def artifact_lines(self, aid, data):
        if len(data) > self.CACHE_FILE_BYTES:
            return data.splitlines(keepends=True)
        if aid not in self.line_cache:
            self.line_cache[aid] = data.splitlines(keepends=True)
        return self.line_cache[aid]

    def artifact_reference_issues(self, ref):
        artifact = self.artifact(ref["artifact_id"])
        issues = list(artifact["issues"])
        if "line" in ref and artifact["status"] == "ready":
            line = ref["line"]
            found = False
            if isinstance(line, int) and not isinstance(line, bool) and line >= 1:
                data = artifact["data"]
                if data is None and artifact["provenance"].get("kind") == "observation":
                    data = self.artifact_data(ref["artifact_id"])
                if data is not None:
                    found = line <= len(self.artifact_lines(ref["artifact_id"], data))
                else:
                    with self.source_path(artifact["provenance"]["path"]).open("rb") as stream:
                        found = any(number == line for number, _ in enumerate(stream, 1))
            if not found:
                issues.append({"code": "artifact_location_missing", "artifact_id": ref["artifact_id"], "line": line})
        return issues

    def candidates(self, page):
        scope = page["discovery_scope"]
        subjects, roots = set(scope["subject_refs"]), set(scope["root_record_refs"])
        related = {("entity", rid) for rid in subjects if rid in self.entities}
        related.update(("record", rid) for rid in roots if rid in self.records)
        for subject in subjects:
            related.update(self.subject_index.get(subject, ()))
        # Explicit corrections/refutations can arrive before subject association.
        linked, _ = self.record_closure(rid for kind, rid in related if kind == "record")
        related.update(("record", rid) for rid in linked)
        # Publication marks explicit forward source observations/entities read.
        # Keep those same current references in scope even without subject tags;
        # use current records so removed refs and revised signatures still differ
        # from the page's authored checked_candidates snapshot.
        for rid in linked:
            row = self.records[rid]
            related.update(("observation", oid) for oid in ref_ids(row.get("observation_refs", []))
                           if oid in self.observations)
            related.update(("entity", eid) for eid in ref_ids(row.get("subject_refs", []))
                           if eid in self.entities)
        groups = {"record": self.records, "observation": self.observations, "entity": self.entities}
        result = [signature(kind, groups[kind][rid]) for kind, rid in sorted(related)]
        return sorted(result, key=encode)

    def source_issues(self, refs):
        issues = []
        for ref in refs:
            rid = ref if isinstance(ref, str) else ref["id"]
            row = self.records.get(rid) or self.entities.get(rid)
            if row is None:
                issues.append({"code": "missing_reference", "id": rid})
            elif isinstance(ref, dict) and row["revision"] != ref["revision"]:
                issues.append({"code": "stale_source", "id": rid,
                               "expected": ref["revision"], "current": row["revision"]})
        return issues

    def page_check(self, pid):
        self.ensure_page(pid)
        if pid in self.check_cache:
            return self.check_cache[pid]
        page = self.pages[pid]
        issues = list(self.page_issues[pid]) + self.source_issues(page["source_refs"])
        old = {encode(x): x for x in page["checked_candidates"]}
        now = {encode(x): x for x in self.candidates(page)}
        new = [now[k] for k in sorted(now.keys() - old.keys())]
        removed = [old[k] for k in sorted(old.keys() - now.keys())]
        if new:
            issues.append({"code": "new_candidates", "count": len(new)})
        if removed:
            issues.append({"code": "removed_candidates", "count": len(removed)})
        for block in page["blocks"]:
            issues.extend(self.blocks[f'{pid}/{block["block_id"]}']["_issues"])
            issues.extend(self.source_issues(block["source_refs"]))
            for ref in block.get("artifact_refs", []):
                issues.extend(self.artifact_reference_issues(ref))
        conditions = page.get("conditions", {})
        subjects = set(page["discovery_scope"]["subject_refs"])
        for goal in self.records_with_flag("goals"):
            if subjects.intersection(goal.get("subject_refs", [])):
                current = goal.get("scope", {})
                for axis in ("environment", "session_generation"):
                    if axis in current and axis in conditions and current[axis] != conditions[axis]:
                        issues.append({"code": "condition_change", "axis": axis,
                                       "previous": conditions[axis], "current": current[axis]})
        for candidate in now.values():
            if candidate["kind"] == "record":
                for ref in self.records[candidate["id"]].get("artifact_refs", []):
                    issues.extend(self.artifact_reference_issues(ref))
            if candidate["kind"] != "observation":
                continue
            obs = self.observation(candidate["id"])
            issues.extend(obs["issues"])
            if obs["raw"]:
                for axis in ("environment", "session_generation"):
                    if axis in obs["raw"] and axis in conditions and obs["raw"][axis] != conditions[axis]:
                        issues.append({"code": "condition_change", "axis": axis, "id": obs["id"]})
        unique = {encode(i): i for i in issues}
        issues = [unique[k] for k in sorted(unique)]
        bad = {"page_missing", "page_hash_mismatch", "block_hash_mismatch", "duplicate_anchor"}
        status = "unavailable" if any(i["code"] in bad for i in issues) else "review_required" if issues else "ready"
        out = {"page_id": pid, "status": status, "issues": issues,
               "new_candidates": new, "removed_candidates": removed}
        self.check_cache[pid] = out
        return out

    def block_closure(self, keys):
        pending, found, issues = list(keys), set(), []
        while pending:
            key = pending.pop()
            if key in found:
                continue
            if key not in self.blocks:
                issues.append({"code": "missing_reference", "block_ref": key})
                continue
            found.add(key)
            block = self.blocks[key]
            refs = block.get("required_block_refs", [])
            if block.get("role") == "history" and not refs:
                issues.append({"code": "history_without_correction", "block_ref": key})
            pending.extend(f'{r["page_id"]}/{r["block_id"]}' for r in refs)
        return found, issues

    def record_closure(self, seeds):
        key = tuple(sorted(set(seeds)))
        if key in self.closure_cache:
            return self.closure_cache[key]
        pending, found, issues = list(key), set(), []
        while pending:
            rid = pending.pop()
            if rid in found:
                continue
            if rid not in self.records:
                issues.append({"code": "missing_reference", "id": rid})
                continue
            found.add(rid)
            pending.extend(self.record_dependencies[rid] | self.reverse_corrections.get(rid, set()))
        # Detect evidence dependency cycles, excluding generated reverse lookups
        # and an explicitly paired contradiction inverse. Closure keeps both ends.
        colors = {}
        for start in sorted(found):
            if colors.get(start):
                continue
            stack = [(start, False)]
            while stack:
                rid, leaving = stack.pop()
                if leaving:
                    colors[rid] = 2
                    continue
                if colors.get(rid) == 2:
                    continue
                if colors.get(rid) == 1:
                    issues.append({"code": "dependency_cycle", "id": rid})
                    continue
                colors[rid] = 1
                stack.append((rid, True))
                stack.extend((target, False) for target in sorted(self.cycle_dependencies[rid] & found, reverse=True))
        self.closure_cache[key] = (found, issues)
        return found, issues

    @corpus_stage("package")
    def package(self, block_keys=(), record_ids=(), observation_ids=(), entity_ids=(),
                *, view="evidence", _validate_knowledge=True, _expand_artifacts=True):
        """Build the requested view while verifying the same complete source closure.

        Knowledge checks use full observations internally, without decoding source
        artifact text merely to discard it from a compact response.
        """
        if view not in {"compact", "evidence"}:
            raise ValueError("view must be compact or evidence")
        bkeys, issues = self.block_closure(block_keys)
        seeds = set(record_ids)
        eids = set(entity_ids)
        oids = set(observation_ids)
        blocks, checks = [], []
        for key in sorted(bkeys):
            block = self.blocks[key]
            page = self.pages[block["page_id"]]
            check = self.page_check(page["page_id"])
            if check["status"] == "unavailable":
                issues.extend(check["issues"])
                return None, issues
            checks.append(check)
            for rid in ref_ids(block["source_refs"]):
                (eids if rid in self.entities else seeds).add(rid)
            blocks.append({k: v for k, v in block.items() if not k.startswith("_")
                           and not (view == "compact" and block.get("representation") == "record" and k == "text")})
            blocks[-1].update(status=check["status"], path=page["path"],
                              conditions={**page.get("conditions", {}), **block.get("conditions", {})},
                              evidence_role="derived_explanation")
            if view == "compact":
                blocks[-1] = compact_block(self, blocks[-1])
        rids, processed_entities = set(), set()
        # Close only explicit provenance and ownership edges, never similarity edges.
        while True:
            current_rids, more = self.record_closure(seeds)
            issues.extend(more)
            rids.update(current_rids)
            for rid in current_rids:
                eids.update(self.records[rid].get("subject_refs", []))
                oids.update(self.records[rid].get("observation_refs", []))
                if self.records[rid].get("kind") == "Chain":
                    for link in self.records[rid].get("links", []):
                        oids.update(ref_ids(link.get("evidence_refs", [])))
            for oid in oids:
                eids.update(self.observations.get(oid, {}).get("subject_refs", []))
            pending_entities = eids - processed_entities
            if not pending_entities:
                break
            for eid in sorted(pending_entities):
                entity = self.entities.get(eid)
                if entity is None:
                    issues.append({"code": "missing_reference", "id": eid})
                    continue
                seeds.update(ref_ids(entity.get("source_refs", [])))
                for field in ("owner_ref", "tenant_ref", "asset_ref"):
                    if entity.get(field):
                        eids.add(entity[field])
            processed_entities.update(pending_entities)
        if any(i["code"] in {"missing_reference", "history_without_correction", "dependency_cycle"} for i in issues):
            return None, issues
        artifact_ids = set()
        if self.source_checker is None:
            from discovery import _Sources
            self.source_checker = _Sources(self)
        for rid in rids:
            row = self.records[rid]
            issues.extend(self.source_checker.basis_issues(rid))
            if row.get("kind") == "Fact" and not (row.get("observation_refs") or row.get("artifact_refs") or row.get("source_refs")):
                issues.append({"code": "fact_without_source", "id": rid})
            oids.update(row.get("observation_refs", []))
            eids.update(row.get("subject_refs", []))
            for ref in row.get("artifact_refs", []):
                artifact_ids.add(ref["artifact_id"])
                issues.extend(self.artifact_reference_issues(ref))
        for block in blocks:
            artifact_ids.update(r["artifact_id"] for r in block.get("artifact_refs", []))
            for ref in block.get("artifact_refs", []):
                issues.extend(self.artifact_reference_issues(ref))
        observations = []
        for oid in sorted(oids):
            if oid not in self.observations:
                return None, issues + [{"code": "missing_reference", "id": oid}]
            obs = self.observation(oid)
            observations.append(compact_observation(obs) if view == "compact" else obs)
            if view == "evidence" and obs["raw"] is not None:
                count(self.metrics, "packaged_raw_observations" if _expand_artifacts
                      else "validation_raw_observations")
            issues.extend(obs["issues"])
            eids.update(obs["index"].get("subject_refs", []))
            artifact_ids.add(obs["index"]["artifact_id"])
            if obs["index"].get("source_artifact_id"):
                artifact_ids.add(obs["index"]["source_artifact_id"])
        artifacts = []
        for aid in sorted(artifact_ids):
            artifact = self.artifact(aid)
            issues.extend(artifact["issues"])
            artifacts.append(compact_artifact(artifact) if view == "compact"
                             else {k: v for k, v in artifact.items() if k != "data"})
            if (view == "evidence" and _expand_artifacts and artifact["status"] == "ready"
                    and not any(o["index"]["artifact_id"] == aid for o in observations)):
                try:
                    count(self.metrics, "source_text_expansions")
                    artifacts[-1]["content"] = self.artifact_data(aid).decode("utf-8")
                    count(self.metrics, "source_text_chars", len(artifacts[-1]["content"]))
                except UnicodeError:
                    issues.append({"code": "non_text_artifact", "artifact_id": aid})
        for eid in eids:
            if eid not in self.entities:
                issues.append({"code": "missing_reference", "id": eid})
        if _validate_knowledge:
            for key in sorted(bkeys):
                if "knowledge" not in self.blocks[key]:
                    continue
                if key not in self.knowledge_check_cache:
                    # Lazy import avoids the Wiki audit module's dependency on
                    # Corpus and costs nothing for unannotated legacy blocks.
                    from wiki import validate_block_knowledge
                    own_package, more = self.package(block_keys=[key], _validate_knowledge=False,
                                                     _expand_artifacts=False)
                    if own_package is None:
                        return None, issues + more
                    with stage_measure(self.metrics, "verification"):
                        self.knowledge_check_cache[key] = validate_block_knowledge(self, key, own_package)
                issues.extend(self.knowledge_check_cache[key])
            if any(issue["code"].startswith("knowledge_") for issue in issues):
                return None, issues
            for block in blocks:
                key = block["page_id"] + "/" + block["block_id"]
                if key in self.reasoning_cache:
                    block["reasoning"] = self.reasoning_cache[key]
        return {"blocks": blocks, "records": [compact_record(self.records[r]) if view == "compact"
                                               else self.records[r] for r in sorted(rids)],
                "observations": observations, "entities": [self.entities[e] for e in sorted(eids) if e in self.entities],
                "artifacts": artifacts, "page_checks": checks}, issues


@corpus_stage("index")
def search(corpus, query, anchors, *, with_exact=False, with_reasons=False):
    """Rank complete evidence units; lexical relevance does not establish truth."""
    return rank_corpus(corpus, query, anchors, with_exact=with_exact, with_reasons=with_reasons)


def cross_candidates(corpus, observations, limit):
    original = [corpus.observation(row["id"]) if "raw" not in row else row for row in observations]
    valid = [row for row in original if row["raw"] is not None]
    subjects, dimensions, by_subject = [], [], {}
    object_patterns = [(eid, re.compile(r"(?<![\w-])" + re.escape(eid) + r"(?![\w-])"))
                       for eid, entity in corpus.entities.items() if entity.get("kind") == "object"]
    # Compute each observation's dimensions once, then compare only shared-subject pairs.
    for index, observation in enumerate(valid):
        raw = observation["raw"]
        refs = set(observation["index"].get("subject_refs", []))
        shared = {eid for eid in refs if corpus.entities.get(eid, {}).get("kind") in {"object", "endpoint", "flow"}}
        subjects.append(shared)
        for eid in shared:
            by_subject.setdefault(eid, set()).add(index)
        dims = {axis: raw.get(axis) for axis in ("actor_ref", "environment", "session_generation", "stage", "signal_kind")}
        dims["endpoint"] = sorted(eid for eid in refs if corpus.entities.get(eid, {}).get("kind") == "endpoint")
        request = raw.get("request", {})
        request_text = encode(request)
        dims["object"] = sorted(set(raw.get("request_object_refs", [])) |
                                {eid for eid, pattern in object_patterns if pattern.search(request_text)})
        dims["request_method"] = request.get("method")
        dims["request_input"] = {key: value for key, value in request.items() if key != "auth_ref"}
        dimensions.append(dims)

    count = 0

    def pairs():
        nonlocal count
        for index, left in enumerate(valid):
            related = set()
            for eid in subjects[index]:
                related.update(by_subject[eid])
            for other in sorted(i for i in related if i > index):
                right = valid[other]
                a, b = left["raw"], right["raw"]
                dims_a, dims_b = dimensions[index], dimensions[other]
                shared = sorted(subjects[index] & subjects[other])
                changed = sorted(key for key in dims_a if dims_a[key] != dims_b[key])
                difference = a.get("response") != b.get("response")
                if not changed and not difference:
                    continue
                same_input = bool(a.get("request", {}).get("url")) and dims_a["request_input"] == dims_b["request_input"]
                specific = any(corpus.entities[eid]["kind"] in {"object", "endpoint"} for eid in shared)
                count += 1
                yield {"left_ref": left["id"], "right_ref": right["id"],
                       "relation": "same_request_input" if same_input else "shared_subject" if specific else "same_flow",
                       "shared_refs": shared, "changed_axes": changed,
                       "request_object_refs": {left["id"]: dims_a["object"], right["id"]: dims_b["object"]},
                       "response_difference": difference,
                       "note": "对照候选；共同实体不证明因果，条件差异需由 LLM 评估。"}

    result = heapq.nsmallest(limit, pairs(), key=lambda c: (
        c["relation"] != "same_request_input", c["relation"] == "same_flow",
        len(c["changed_axes"]), c["left_ref"], c["right_ref"]))
    return result, count - len(result)


PACKING_RESERVE_CHARS = 450


def retrieve(root, run_id, query, anchors=(), budget_chars=None, max_candidates=None,
             *, include_methods=False, method_ids=(), method_intents=(), cross_limit=0,
             view="evidence", cursor=None, refresh=False, metrics=None,
             mode="combined", question_ref=None, context_epoch=None, current_conditions=None):
    anchors = list(anchors)
    if mode not in {"combined", "lexical"}:
        raise RetrievalError("mode must be combined or lexical")
    if question_ref:
        anchors = list(dict.fromkeys([question_ref, *anchors]))
    if not isinstance(query, str) or (not query.strip() and not anchors):
        raise RetrievalError("query 或 anchor 至少提供一项")
    if budget_chars is not None and (isinstance(budget_chars, bool) or not isinstance(budget_chars, int) or budget_chars < 1024):
        raise RetrievalError("budget_chars 必须为空或不小于 1024 的整数")
    if max_candidates is not None and (isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or max_candidates < 1):
        raise RetrievalError("max_candidates 必须为空或正整数")
    if isinstance(cross_limit, bool) or not isinstance(cross_limit, int) or cross_limit < 0:
        raise RetrievalError("cross_limit 必须为非负整数；0 表示不运行观察两两对照")
    corpus = None
    try:
        corpus = Corpus(root, run_id, lazy_pages=True, lazy_metadata=True, metrics=metrics,
                        current_conditions=current_conditions)
        if question_ref is not None and question_ref not in corpus.records:
            raise RetrievalError("question_ref must identify an existing session record")
        method_units, method_issues = (select_methods(query, method_ids, intents=method_intents)
                                      if include_methods or method_ids or method_intents else ([], []))
        def build(pack_limit):
            result = _retrieve(corpus, query, list(anchors), pack_limit, max_candidates,
                               method_units, method_issues, cross_limit=cross_limit, related_only=view == "compact",
                               view=view, mode=mode)
            packed_chars = result["budget"]["used_chars"]
            result["budget"]["limit_chars"] = budget_chars
            result["retrieval_request"] = {"mode": mode, "ranking_version": RANKING_VERSION,
                "query": query, "anchors": sorted(set(anchors)),
                "question_ref": question_ref, "max_candidates": max_candidates,
                "cross_limit": cross_limit, "include_methods": include_methods,
                "method_ids": sorted(method_ids), "method_intents": sorted(method_intents),
                "current_conditions": current_conditions or {}}
            if question_ref is not None:
                from question_context import assess_question
                result["question_context"] = assess_question(corpus, question_ref, result, mode=mode)
            if not corpus.stable():
                result = {"run_id": corpus.run_id, "state_revision": corpus.state["revision"],
                    "status": "unavailable", "gaps": [{"code": "snapshot_changed"}],
                    "records": [], "observations": [], "artifacts": [], "blocks": [], "entities": [],
                    "chain_discovery": {"candidates": [], "paths": [], "combinations": [], "type_reviews": []},
                    "budget": {"limit_chars": budget_chars, "used_chars": 0, "omitted_units": 0}}
            from context_views import finalize_context
            with stage_measure(metrics, "context_view"):
                return finalize_context(corpus, result, view=view, cursor=cursor, refresh=refresh,
                                        context_epoch=context_epoch), packed_chars

        # Size the final envelope too: request/task/question/delta fields follow
        # evidence packing and can exceed its small diagnostic reserve. Repack
        # whole source closures, never trim their bodies or acknowledge failed
        # delivery. An existing cursor first gets a chance to suppress old bodies.
        pack_limit = None if cursor is not None else budget_chars
        result, packed_chars = build(pack_limit)
        while budget_chars is not None and result["budget"].get("required_chars", 0) > budget_chars:
            if pack_limit is None:
                pack_limit = budget_chars
            elif pack_limit > 1024:
                overflow = result["budget"]["required_chars"] - budget_chars
                # Skip unused packing allowance when a large task/question
                # envelope dominates output. Keep the selector's diagnostic
                # reserve; reducing that allowance alone need not remove a unit.
                occupied_limit = min(pack_limit, packed_chars + PACKING_RESERVE_CHARS)
                pack_limit = max(1024, occupied_limit - overflow)
            else:
                break
            result, packed_chars = build(pack_limit)
        return result

    except RetrievalError:
        raise
    except (OSError, KeyError, TypeError, AttributeError, UnicodeError, json.JSONDecodeError) as exc:
        raise RetrievalError(f"资料结构无法读取：{exc}") from exc
    finally:
        if corpus is not None:
            corpus.close()


def _retrieve(corpus, query, anchors, budget_chars, max_candidates,
              method_units=(), method_issues=(), *, cross_limit=0, related_only=False, view="evidence", mode="combined"):
    from discovery import discover

    ranked, search_issues, exact, reasons = search(corpus, query, anchors, with_exact=True, with_reasons=True)
    # Scan the full session BEFORE lexical/candidate/output limits. Relation discovery
    # is not restricted to observations which happened to fit the returned package.
    discovery_anchors = list(dict.fromkeys(anchors + [key for kind, key in sorted(exact) if kind == "record"]))
    chain = {}
    if mode == "combined":
        with stage_measure(corpus.metrics, "discovery"):
            chain = discover(corpus, query=query, anchors=discovery_anchors)
    relation_keys = [("record", rid) for rid in chain.get("record_refs", []) if rid in corpus.records]
    for key in relation_keys:
        reasons.setdefault(key, []).append({"kind": "capability_relation"})
    explicit = [key for key in ranked if any(r["kind"] == "exact_anchor" for r in reasons.get(key, []))]
    exact_order = explicit + [key for key in ranked if key in exact and key not in explicit]
    relation_ids = {key for _, key in relation_keys}
    related_blocks = [("block", key) for key in sorted(corpus.source_blocks(relation_ids))]
    for key in related_blocks:
        reasons.setdefault(key, []).append({"kind": "capability_source"})
    rank_positions = {key: index for index, key in enumerate(ranked)}
    goals = corpus.records_with_flag("goals")
    blockers = corpus.records_with_flag("blockers")
    diagnostics = list(corpus.load_issues) + list(search_issues) + list(method_issues) + list(chain.get("issues", []))
    navigation, fresh_keys, unclassified_keys, checks = [], [], [], []
    mirror_keys = list(getattr(corpus, "retrieval_mirrors", {}))
    relevant_pages = sorted({corpus.blocks[key]["page_id"]
                             for kind, key in ranked + related_blocks + mirror_keys if kind == "block"})
    # Preserve freshness scanning independently of packing limits. Global uncertain
    # material is surfaced after exact requests, needed relations and normal hits.
    for pid in relevant_pages:
        check = corpus.page_check(pid)
        checks.append(check)
        navigation.append({"page_id": pid, "path": corpus.pages[pid]["path"], "status": check["status"]})
        diagnostics.extend({**issue, "page_id": pid} for issue in check["issues"])
        for candidate in check["new_candidates"]:
            key = candidate["kind"], candidate["id"]
            fresh_keys.append(key)
            reasons.setdefault(key, []).append({"kind": "new_page_source", "page_id": pid})
    relevant = set(ranked + relation_keys + related_blocks + fresh_keys)
    seeds = {rid for kind, rid in relevant if kind == "record"}
    seeds.update(row["id"] for row in goals + blockers)
    for kind, key in relevant:
        if kind == "block":
            seeds.update(ref_ids(corpus.blocks[key].get("source_refs", [])))
    source_ids, _ = corpus.record_closure(seeds)
    relevant.update(("record", rid) for rid in source_ids)
    for rid in source_ids:
        relevant.update(("observation", oid) for oid in corpus.records[rid].get("observation_refs", []))
        relevant.update(("entity", eid) for eid in corpus.records[rid].get("subject_refs", []))
    outside_unclassified = 0
    for kind, group in (("record", corpus.records), ("observation", corpus.observations), ("entity", corpus.entities)):
        if corpus.metadata is not None:
            uncertain_ids = sorted(rid for row_kind, rid in corpus.metadata.links("flag")["unclassified"]
                                   if row_kind == kind)
        else:
            uncertain_ids = sorted(group)
        for rid in uncertain_ids:
            if corpus.metadata is not None and related_only and (kind, rid) not in relevant:
                outside_unclassified += 1
                continue
            row = group[rid]
            uncertain = row.get("classification") in {"unclassified", "uncertain", "unlinked"}
            uncertain |= kind == "observation" and not row.get("subject_refs")
            if uncertain and related_only and (kind, rid) not in relevant:
                outside_unclassified += 1
                continue
            if uncertain:
                diagnostics.append({"code": "unclassified", "kind": kind, "id": rid})
                unclassified_keys.append((kind, rid))
                reasons.setdefault((kind, rid), []).append({"kind": "unclassified_review"})
    if outside_unclassified:
        diagnostics.append({"code": "unclassified_outside_query", "count": outside_unclassified,
                            "detail": "本会话另有未关联资料，未作为当前问题证据返回；仍可全库检索或按 ID 读取。"})
    for goal in goals:
        for rid in goal.get("unclassified_record_refs", []):
            kind = "observation" if rid in corpus.observations else "entity" if rid in corpus.entities else "record"
            diagnostics.append({"code": "unclassified", "kind": kind, "id": rid})
            unclassified_keys.append((kind, rid))
            reasons.setdefault((kind, rid), []).append({"kind": "unclassified_review"})
    if not ranked and not relation_keys:
        diagnostics.append({"code": "no_hit", "detail": "没有定位到相关资料；不表示反证或已覆盖。"})
        navigation = [{"page_id": pid, "path": page["path"], "retrieval_reason": "仅目录导航，未命中"}
                      for pid, page in sorted(corpus.pages.items())]
    ordered = []
    for key in exact_order + relation_keys + related_blocks + ranked + fresh_keys + unclassified_keys:
        owner = mirror_owner(corpus, key[1], exact) if key[0] == "block" else None
        # Page freshness checks above and package validation below remain active.
        ordered.append(owner or key)
    ordered = list(dict.fromkeys(ordered))
    out = {"run_id": corpus.run_id, "state_revision": corpus.state["revision"], "query": query,
           "status": "ready", "mandatory_context": {"goals": goals, "blockers": blockers},
           "blocks": [], "records": [], "observations": [], "entities": [], "artifacts": [],
           "cross_candidates": [], "page_checks": [], "methods": [], "method_navigation": [],
           "chain_discovery": {"candidates": [], "paths": [], "combinations": [], "type_reviews": [],
                               "record_refs": [], "issues": []},
           "retrieval_reasons": [], "gaps": [], "navigation": [], "omissions": [],
           "budget": {"limit_chars": budget_chars, "used_chars": 0, "omitted_units": 0}}
    if view == "compact":
        out["view"] = view
        out["mandatory_context"] = compact_mandatory(out["mandatory_context"])
    missing_mandatory = False
    failures, omissions = {}, []
    unlimited = budget_chars is None
    limit = float("inf") if budget_chars is None else budget_chars
    reserve = PACKING_RESERVE_CHARS if budget_chars is not None else 0
    size_cache = {}
    package_accumulators = {field: {} for field in (
        "blocks", "records", "observations", "entities", "artifacts", "page_checks")}

    def row_size(row):
        key = id(row)
        if key not in size_cache:
            size_cache[key] = (row, len(encode(row)))
        return size_cache[key][1]

    def measure(value):
        size = 2 + max(0, len(value) - 1)
        for field, content in value.items():
            size += row_size(field) + 1
            if isinstance(content, list):
                size += 2 + max(0, len(content) - 1) + sum(row_size(row) for row in content)
            elif field == "budget":
                size += len(encode(content))
            else:
                size += row_size(content)
        fixed = size - len(str(value["budget"]["used_chars"]))
        while fixed + len(str(size)) != size:
            size = fixed + len(str(size))
        value["budget"]["used_chars"] = size
        return size

    def fits(value):
        return unlimited or measure(value) <= limit - reserve

    def package_keys(value):
        keys = {("block", row["page_id"] + "/" + row["block_id"]) for row in value["blocks"]}
        for kind, field in (("record", "records"), ("observation", "observations"), ("entity", "entities")):
            keys.update((kind, row["id"]) for row in value[field])
        return keys

    def merge_package(base, package):
        if unlimited:
            # Every accepted package retains its complete source closure. Accumulate
            # by identity and sort once, rather than rebuilding every earlier list.
            for field, rows in package.items():
                merged = package_accumulators[field]
                for row in rows:
                    key = row.get("id") or (row["page_id"], row.get("block_id", ""))
                    if key not in merged:
                        base[field].append(row)
                    merged[key] = row
            return base
        result = {**base, "budget": dict(base["budget"])}
        for field, rows in package.items():
            def identity(row):
                return row.get("id") or (row["page_id"], row.get("block_id", ""))
            merged = {identity(row): row for row in result[field]}
            merged.update({identity(row): row for row in rows})
            if field == "blocks":
                result[field] = sorted(merged.values(), key=lambda row: (
                    rank_positions.get(("block", row["page_id"] + "/" + row["block_id"]), len(ranked)), str(identity(row))))
            else:
                result[field] = sorted(merged.values(), key=lambda row: str(identity(row)))
        return result

    mandatory, issues = corpus.package(record_ids=[r["id"] for r in goals + blockers], view=view)
    diagnostics.extend(issues)
    if mandatory is not None and fits(trial := merge_package(out, mandatory)):
        out = trial
    else:
        missing_mandatory = True
        out["mandatory_context"] = {"goal_refs": [r["id"] for r in goals], "blocker_refs": [r["id"] for r in blockers]}
        diagnostics.append({"code": "mandatory_context_unavailable"})
        omissions.append({"kind": "mandatory_context", "reason": "budget_exhausted" if mandatory is not None else "invalid_source"})
    covered = package_keys(out)
    considered = ordered[:max_candidates]
    if not missing_mandatory:
        arguments = {"block": "block_keys", "record": "record_ids", "observation": "observation_ids", "entity": "entity_ids"}
        for key in considered:
            if key in covered:
                continue
            package, issues = corpus.package(**{arguments[key[0]]: [key[1]]}, view=view)
            diagnostics.extend(issues)
            if package is None:
                failures[key] = "invalid_source"
            elif fits(trial := merge_package(out, package)):
                out = trial
                covered.update(package_keys(package))
            else:
                failures[key] = "budget_exhausted"
    if unlimited:
        for field, merged in package_accumulators.items():
            if field == "blocks":
                out[field] = sorted(merged.values(), key=lambda row: (
                    rank_positions.get(("block", row["page_id"] + "/" + row["block_id"]), len(ranked)),
                    str((row["page_id"], row.get("block_id", "")))))
            else:
                out[field] = [merged[key] for key in sorted(merged, key=str)]
    # Count omissions only after complete dependency packages have been admitted:
    # a below-cutoff record may already be present as another record's evidence.
    for key in ordered:
        if key not in covered:
            reason = "mandatory_context_unavailable" if missing_mandatory else failures.get(key, "candidate_limit")
            omissions.append({"kind": key[0], "id": key[1], "reason": reason})
    candidate_omitted = sum(row["reason"] == "candidate_limit" for row in omissions)
    if candidate_omitted:
        diagnostics.append({"code": "candidate_limit", "omitted": candidate_omitted})

    def append_optional(field, row, *, identity=None):
        nonlocal out
        if unlimited:
            out[field].append(row)
            return True
        trial = {**out, "budget": dict(out["budget"]), field: [*out[field], row]}
        if fits(trial):
            out = trial
            return True
        omissions.append({"kind": field, "id": identity or row.get("id", ""), "reason": "budget_exhausted"})
        return False

    # Compact graph explanations follow evidence, so a large discovery graph cannot
    # evict an explicitly requested observation under an optional caller budget.
    for field in ("candidates", "combinations", "type_reviews", "paths", "record_refs", "issues"):
        if unlimited:
            out["chain_discovery"][field] = list(chain.get(field, []))
            continue
        for index, row in enumerate(chain.get(field, [])):
            trial_chain = {**out["chain_discovery"], field: [*out["chain_discovery"][field], row]}
            trial = {**out, "budget": dict(out["budget"]), "chain_discovery": trial_chain}
            if fits(trial):
                out = trial
            else:
                omissions.append({"kind": "chain_discovery." + field, "id": str(index), "reason": "budget_exhausted"})
    # Explain both direct retrieval and provenance which travelled with a unit.
    for kind, key in sorted(covered):
        append_optional("retrieval_reasons", {"kind": kind, "id": key,
                        "reasons": reasons.get((kind, key), [{"kind": "required_context"}])}, identity=key)
    if cross_limit and not missing_mandatory:
        # Optional diagnostic only: compare observations related to actual hits and
        # capability candidates, never all globally unclassified material.
        focus = set()
        for kind, key in set(ranked + relation_keys):
            if kind == "observation":
                focus.add(key)
            elif kind == "record":
                focus.update(corpus.records[key].get("observation_refs", []))
            elif kind == "block":
                for rid in ref_ids(corpus.blocks[key].get("source_refs", [])):
                    focus.update(corpus.records.get(rid, {}).get("observation_refs", []))
        observations = [row for row in out["observations"] if row["id"] in focus]
        cross, cross_omitted = cross_candidates(corpus, observations, cross_limit)
        if cross_omitted:
            diagnostics.append({"code": "cross_candidate_limit", "omitted": cross_omitted})
            omissions.append({"kind": "cross_candidates", "reason": "cross_candidate_limit", "count": cross_omitted})
        for row in cross:
            append_optional("cross_candidates", row, identity=row["left_ref"] + "/" + row["right_ref"])
    for unit in method_units:
        if missing_mandatory:
            loaded = False
            reason = "mandatory_context_unavailable"
            omissions.append({"kind": "methods", "id": unit["id"], "reason": reason})
        else:
            loaded = append_optional("methods", unit)
            reason = "budget_exhausted"
        if not loaded:
            diagnostics.append({"code": "method_not_loaded", "id": unit["id"], "reason": reason})
            append_optional("method_navigation", {"id": unit["id"], "path": unit["path"], "reason": reason}, identity=unit["id"])
    seen_pages = {row["page_id"] for row in out["page_checks"]}
    for check in checks:
        if check["page_id"] not in seen_pages:
            append_optional("page_checks", check, identity=check["page_id"])
    for row in navigation:
        if view == "compact":
            row = compact_navigation(corpus, row)
        append_optional("navigation", row, identity=row["page_id"])

    if not corpus.stable():
        # Clear every derived claim, including graph suggestions, from a mixed snapshot.
        for field in ("blocks", "records", "observations", "entities", "artifacts", "cross_candidates", "page_checks", "retrieval_reasons"):
            out[field] = []
        out["chain_discovery"] = {"candidates": [], "paths": [], "combinations": [], "type_reviews": [],
                                  "record_refs": [], "issues": []}
        out["mandatory_context"] = compact_mandatory({}) if view == "compact" else {}
        diagnostics.append({"code": "snapshot_changed", "detail": "读取期间资料改变，请重试。"})
    if any(row["reason"] == "budget_exhausted" for row in omissions):
        diagnostics.append({"code": "budget_exhausted", "detail": "部分完整材料未返回；用精确 anchor 补取或增加预算，不能据遗漏下结论。"})
    unique = {encode(row): row for row in diagnostics}
    diagnostics = list(unique.values())
    # Detailed diagnostics also respect an explicit output budget. Counts of omitted
    # details remain visible; global unclassified alerts cannot displace exact evidence.
    hidden_diagnostics = 0
    for row in diagnostics:
        if unlimited:
            out["gaps"].append(row)
            continue
        trial = {**out, "budget": dict(out["budget"]), "gaps": [*out["gaps"], row]}
        if fits(trial):
            out = trial
        else:
            hidden_diagnostics += 1
    critical_codes = {row["code"] for row in diagnostics} & {
        "budget_exhausted", "mandatory_context_unavailable", "snapshot_changed", "candidate_limit"
    }
    present_codes = {row["code"] for row in out["gaps"]}
    out["gaps"].extend({"code": code} for code in sorted(critical_codes - present_codes))
    if hidden_diagnostics:
        out["gaps"].append({"code": "diagnostic_details_omitted", "count": hidden_diagnostics,
                            "codes": sorted({row["code"] for row in diagnostics})})
    # Omission counts are exact even when their full IDs do not fit the caller's
    # requested budget. This is an output-size option, never a model token limit.
    total_omissions = sum(row.get("count", 1) for row in omissions)
    hidden_omissions = 0
    for row in omissions:
        if unlimited:
            out["omissions"].append(row)
            continue
        trial = {**out, "budget": dict(out["budget"]), "omissions": [*out["omissions"], row]}
        if fits(trial):
            out = trial
        else:
            hidden_omissions += row.get("count", 1)
    out["budget"]["omitted_units"] = total_omissions
    if hidden_omissions:
        out["budget"]["omitted_details"] = hidden_omissions
    out["status"] = "review_required" if diagnostics or omissions else "ready"
    fatal = missing_mandatory or any(row["code"] == "snapshot_changed" for row in diagnostics)
    if fatal or not any(out[field] for field in ("blocks", "records", "observations", "entities")):
        out["status"] = "unavailable"
    if not unlimited and measure(out) > limit:
        # The tiny-budget response cannot carry complete required evidence. Return
        # navigation and explicit diagnostics rather than partial claims.
        out = {"run_id": corpus.run_id, "state_revision": corpus.state["revision"], "status": "unavailable",
               "blocks": [], "records": [], "observations": [], "entities": [], "artifacts": [],
               "cross_candidates": [], "page_checks": [], "mandatory_context": {},
               "methods": [], "method_navigation": [], "retrieval_reasons": [],
               "chain_discovery": {"candidates": [], "paths": [], "combinations": [], "type_reviews": [],
                                   "record_refs": [], "issues": []},
               "navigation": [], "omissions": [],
               "gaps": [{"code": "budget_exhausted", "detail": "必要材料和诊断超过输出预算，请增加预算后重试。"}],
               "budget": {"limit_chars": budget_chars, "used_chars": 0,
                          "omitted_units": total_omissions + len(covered), "omitted_details": total_omissions + len(covered)}}
        for row in navigation:
            trial = {**out, "budget": dict(out["budget"]), "navigation": [*out["navigation"], row]}
            if measure(trial) <= limit:
                out = trial
        if measure(out) > limit:
            raise RetrievalError("运行标识本身已超过输出预算")
    if not out["navigation"] and navigation:
        row = {key: navigation[0][key] for key in ("page_id", "path")}
        if out.get("view") == "compact":
            row = compact_navigation(corpus, row)
        trial = {**out, "budget": dict(out["budget"]), "navigation": [row]}
        if measure(trial) <= limit:
            out = trial
    # Native compact output is sized once by finalize_context after optional delta
    # filtering; unrestricted retrieval does not need an earlier serialization.
    if view != "compact" or not unlimited:
        measure(out)
    return out


def main(argv=None, *, include_methods=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--query", default="")
    parser.add_argument("--anchor", action="append", default=[])
    parser.add_argument("--mode", choices=("combined", "lexical"), default="combined")
    parser.add_argument("--question-ref", help="Existing record defining the question and its declared needs")
    parser.add_argument("--budget-chars", type=int, help="可选 JSON 字符预算；默认不限制")
    parser.add_argument("--max-candidates", type=int, help="可选材料候选数；默认不限制")
    parser.add_argument("--cross-limit", type=int, default=0, help="启用观察两两对照并指定结果数；默认关闭")
    parser.add_argument("--method-id", action="append", default=[])
    parser.add_argument("--method-intent", action="append", default=[])
    parser.add_argument("--no-methods", action="store_true")
    parser.add_argument("--view", choices=("compact", "evidence"), default="compact")
    parser.add_argument("--cursor", help="本会话读取游标；重复使用以仅返回变化")
    parser.add_argument("--refresh", action="store_true", help="上下文压缩后重发当前查询完整视图")
    parser.add_argument("--context-epoch", help="宿主上下文代次；变化时重置交付游标")
    parser.add_argument("--current-conditions", type=json.loads, help="当前执行条件的 JSON 对象")
    args = parser.parse_args(argv)
    if args.no_methods and (args.method_id or args.method_intent):
        parser.error("--no-methods cannot be combined with --method-id or --method-intent")
    try:
        result = retrieve(args.root, args.run_id, args.query, args.anchor, args.budget_chars, args.max_candidates,
                          include_methods=include_methods and not args.no_methods,
                          method_ids=args.method_id, method_intents=args.method_intent, cross_limit=args.cross_limit,
                          view=args.view, cursor=args.cursor, refresh=args.refresh,
                          mode=args.mode, question_ref=args.question_ref, context_epoch=args.context_epoch,
                          current_conditions=args.current_conditions)
    except RetrievalError as exc:
        print(encode({"error": str(exc)}), file=sys.stderr)
        return 2
    print(encode(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
