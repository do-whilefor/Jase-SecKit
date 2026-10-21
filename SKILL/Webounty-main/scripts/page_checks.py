"""Rebuildable page-check projections used only while publishing Wiki navigation.

The cache never marks authored candidates read and is not used by retrieval or
audit. State-derived signatures detect new candidates and changed sources;
file metadata detects ordinary edits without reopening every evidence file.
"""

from __future__ import annotations

import copy
import json

from rag import digest, encode, ref_ids
from telemetry import count


CACHE_PATH = "cache/page-checks.json"
VERSION = 1
PAGE_INTEGRITY = {"page_missing", "page_hash_mismatch", "block_hash_mismatch", "duplicate_anchor"}


def _status(check):
    issues = check["issues"]
    check["status"] = ("unavailable" if any(row["code"] in PAGE_INTEGRITY for row in issues)
                       else "review_required" if issues else "ready")
    return check


def _saved_pages(path, run_id):
    """Discard damaged derived entries; authoritative inputs are checked normally."""
    try:
        saved = json.loads(path.read_bytes())
    except (OSError, ValueError, UnicodeError):
        return {}
    if (not isinstance(saved, dict) or saved.get("version") != VERSION
            or saved.get("run_id") != run_id or not isinstance(saved.get("pages"), dict)):
        return {}
    pages = {}
    for pid, entry in saved["pages"].items():
        if not isinstance(entry, dict) or not isinstance(entry.get("check"), dict):
            continue
        check = entry["check"]
        if check.get("page_id") != pid or check.get("status") not in ("ready", "review_required", "unavailable"):
            continue
        fields = {"issues": ("code",), "new_candidates": ("kind", "id"), "removed_candidates": ("kind", "id")}
        if all(isinstance(check.get(field), list) and all(
                isinstance(row, dict) and all(isinstance(row.get(key), str) for key in keys)
                for row in check[field]) for field, keys in fields.items()):
            pages[pid] = entry
    return pages


class PageChecks:
    def __init__(self, corpus, metrics=None):
        self.corpus = corpus
        self.metrics = metrics
        path = corpus.path(CACHE_PATH)
        self.previous = _saved_pages(path, corpus.run_id)
        self.entries = {}
        self.file_states = {}
        self.goals_by_subject = {}
        for rid, row in corpus.records.items():
            if row.get("kind") == "Goal" and row.get("status") == "active":
                for subject in row.get("subject_refs", []):
                    self.goals_by_subject.setdefault(subject, set()).add(rid)

    def _file_state(self, relative, *, written=False):
        key = (relative, written)
        if key not in self.file_states:
            self.file_states[key] = self._read_file_state(relative, written=written)
        return self.file_states[key]

    def _read_file_state(self, relative, *, written=False):
        proposed = getattr(self.corpus, "proposed_files", {})
        if not written and relative in proposed:
            from evidence_io import FileCopy
            value = proposed[relative]
            return ["proposed", value.metadata["sha256"] if isinstance(value, FileCopy) else digest(value)]
        path = self.corpus.path(relative)
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        return [str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]

    def _inputs(self, pid):
        corpus, page = self.corpus, self.corpus.pages[pid]
        candidates = corpus.candidates(page)
        observations = [corpus.observations[row["id"]] for row in candidates if row["kind"] == "observation"]
        record_artifact_refs = {row["id"]: corpus.records[row["id"]]["artifact_refs"]
                                for row in candidates if row["kind"] == "record"
                                and corpus.records[row["id"]].get("artifact_refs")}
        aids = {row["artifact_id"] for row in observations}
        aids.update(row["source_artifact_id"] for row in observations if row.get("source_artifact_id"))
        aids.update(ref["artifact_id"] for block in page["blocks"] for ref in block.get("artifact_refs", []))
        aids.update(ref["artifact_id"] for refs in record_artifact_refs.values() for ref in refs)
        artifacts = [corpus.artifacts.get(aid, {"id": aid}) for aid in sorted(aids)]
        references = list(page["source_refs"])
        references.extend(ref for block in page["blocks"] for ref in block["source_refs"])
        sources = {rid: corpus.records.get(rid) or corpus.entities.get(rid) for rid in ref_ids(references)}
        subjects = set(page["discovery_scope"]["subject_refs"])
        goals = [corpus.records[rid] for rid in sorted({rid for subject in subjects
                                                      for rid in self.goals_by_subject.get(subject, ())})]
        semantic = {"candidates": candidates, "checked_candidates": page["checked_candidates"],
                    "sources": sources, "source_refs": references, "conditions": page.get("conditions", {}),
                    "observations": observations, "artifacts": artifacts, "goals": goals,
                    "record_artifact_refs": record_artifact_refs,
                    "block_artifact_refs": [block.get("artifact_refs", []) for block in page["blocks"]]}
        return {"source_signature": digest(encode(semantic).encode()),
                "page_signature": digest(encode({"path": page["path"], "content_hash": page["content_hash"],
                    "blocks": [{key: block[key] for key in ("block_id", "anchor", "content_hash")}
                               for block in page["blocks"]]}).encode()),
                "evidence_paths": sorted({row["path"] for row in artifacts if "path" in row}),
                "page_path": page["path"]}

    def check(self, pid):
        corpus = self.corpus
        inputs = self._inputs(pid)
        evidence_files = {path: self._file_state(path) for path in inputs["evidence_paths"]}
        page_file = self._file_state(inputs["page_path"])
        old = self.previous.get(pid, {})
        reusable = (old.get("source_signature") == inputs["source_signature"]
                    and old.get("evidence_files") == evidence_files)
        # A block edited in this batch may already have been checked while its
        # provenance package was validated. Do not repeat that evidence work.
        if pid in corpus.check_cache:
            check = copy.deepcopy(corpus.check_cache[pid])
            count(self.metrics, "pages_checked")
        elif reusable:
            check = copy.deepcopy(old["check"])
            count(self.metrics, "page_checks_reused")
            if (old.get("page_signature") != inputs["page_signature"] or old.get("page_file") != page_file):
                corpus.ensure_page(pid)
                check["issues"] = [issue for issue in check["issues"] if issue["code"] not in PAGE_INTEGRITY]
                check["issues"].extend(corpus.page_issues[pid])
                for block in corpus.pages[pid]["blocks"]:
                    check["issues"].extend(corpus.blocks[f'{pid}/{block["block_id"]}']["_issues"])
                _status(check)
                count(self.metrics, "page_integrity_checks")
        else:
            check = copy.deepcopy(corpus.page_check(pid))
            count(self.metrics, "pages_checked")
        self.entries[pid] = {**inputs, "evidence_files": evidence_files, "page_file": page_file, "check": check}
        return copy.deepcopy(check)

    def all(self):
        checks = {pid: self.check(pid) for pid in self.corpus.pages}
        # Required blocks are explicit interpretation dependencies. Their checks
        # propagate to the referring page even if its own bytes did not change.
        result = copy.deepcopy(checks)
        for pid, page in self.corpus.pages.items():
            keys = [pid + "/" + block["block_id"] for block in page["blocks"]]
            closure, issues = self.corpus.block_closure(keys)
            check = result[pid]
            check["issues"].extend(issues)
            for target in sorted({self.corpus.blocks[key]["page_id"] for key in closure} - {pid}):
                if checks[target]["status"] != "ready":
                    check["issues"].append({"code": "required_block_review", "page_id": target,
                                            "status": checks[target]["status"]})
            _status(check)
        return result

    def save(self):
        """Capture actual file metadata only after the batch has been written."""
        for entry in self.entries.values():
            entry["page_file"] = self._file_state(entry["page_path"], written=True)
            entry["evidence_files"] = {path: self._file_state(path, written=True) for path in entry["evidence_paths"]}
        path = self.corpus.path(CACHE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encode({"version": VERSION, "run_id": self.corpus.run_id, "pages": self.entries}) + "\n",
                        encoding="utf-8")
