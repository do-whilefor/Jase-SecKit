"""Compact evidence views and explicit, session-local delivery cursors.

The cursor remembers signatures of delivered objects, never a second fact store.
It is not a claim that the host still understands or retains previous context.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from wiki_structure import navigation_paths


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_encode(value).encode()).hexdigest()


def _measure(result):
    budget = result.setdefault("budget", {"limit_chars": None, "omitted_units": 0})
    budget["used_chars"] = 0
    size = len(_encode(result))
    while size != budget["used_chars"]:
        budget["used_chars"] = size
        size = len(_encode(result))
    return size


def _refs(values):
    if isinstance(values, (str, dict)):
        values = [values]
    return [value if isinstance(value, str) else value["id"] for value in values]


def compact_record(source):
    row = dict(source)
    if "history" in row:
        history = row.pop("history")
        row["history_ref"] = {"read_ref": row["id"], "entries": len(history), "sha256": _hash(history)}
    return row


def compact_observation(source):
    row = {key: value for key, value in source.items() if key != "raw"}
    raw = source.get("raw") or {}
    row["raw_expanded"] = False
    row["read_ref"] = row["id"]
    context = {key: raw[key] for key in (
        "actor_ref", "environment", "session_generation", "credential_generation", "target_version",
        "observed_at", "trace_ref", "truncated", "stage", "signal_kind", "request_object_refs",
    ) if key in raw}
    request = raw.get("request", {})
    if isinstance(request, dict):
        context.update({"request_" + key: request[key] for key in ("method", "url") if key in request})
    response = raw.get("response", {})
    if isinstance(response, dict):
        context.update({"response_" + key: response[key] for key in ("status", "status_code") if key in response})
    if context:
        row["context"] = context
    if not row.get("index", {}).get("summary") and raw.get("summary"):
        row["summary"] = raw["summary"]
    return row


def compact_artifact(source):
    row = {key: value for key, value in source.items() if key not in {"content", "data"}}
    row.update(content_expanded=False, read_ref=row["id"])
    return row


def compact_navigation(corpus, source):
    if not hasattr(corpus, "navigation_paths"):
        corpus.navigation_paths = navigation_paths(corpus.pages)
    pid = source["page_id"]
    return {**source, "ancestry": corpus.navigation_paths[pid],
            "parent_page_id": corpus.pages[pid].get("parent_page_id")}


def compact_block(corpus, source):
    # Do not copy the auto-generated record mirror into the delivery package.
    is_record = source.get("representation") == "record"
    row = compact_navigation(corpus, {key: value for key, value in source.items()
                                     if not (is_record and key == "text")})
    row["read_ref"] = row["page_id"] + "/" + row["block_id"]
    if is_record:
        row["record_refs"] = [rid for rid in _refs(row.get("source_refs", [])) if rid in corpus.records]
        row["text_expanded"] = False
    # Authored blocks retain their whole judgment, including restrictions and gaps.
    return row


def compact_mandatory(mandatory):
    return {
        "goal_refs": mandatory.get("goal_refs", [row["id"] for row in mandatory.get("goals", [])]),
        "blocker_refs": mandatory.get("blocker_refs", [row["id"] for row in mandatory.get("blockers", [])]),
    }


def task_core(corpus, result):
    """Small current-state projection; never remembered separately from the Wiki."""
    goals = []
    for row in corpus.records_with_flag("goals"):
        goals.append({key: row[key] for key in (
            "id", "summary", "hard_constraints", "scope", "next_action", "active_question_ref") if key in row})
    request = result.get("retrieval_request", {})
    question_ref = request.get("question_ref")
    current = corpus.records.get(question_ref, {}) if question_ref else {}
    return {"goals": goals, "question_ref": question_ref,
            "next_action": current.get("next_action"),
            "current_conditions": getattr(corpus, "current_conditions", {}),
            "review_refs": sorted({row.get("record_id", row.get("id")) for row in result.get("gaps", [])
                                   if row.get("code") in {"basis_review_required", "stale_source", "record_has_correction",
                                                          "current_condition_conflict", "current_condition_unknown"}
                                   and (row.get("record_id") or row.get("id"))})}


def _compact(corpus, result):
    out = {**result, "budget": dict(result["budget"]), "view": "compact"}
    mandatory = result.get("mandatory_context", {})
    out["mandatory_context"] = compact_mandatory(mandatory)
    out["records"] = [compact_record(row) for row in result.get("records", [])]
    out["observations"] = [compact_observation(row) for row in result.get("observations", [])]
    out["artifacts"] = [compact_artifact(row) for row in result.get("artifacts", [])]
    out["blocks"] = [compact_block(corpus, row) for row in result.get("blocks", [])]
    out["navigation"] = [compact_navigation(corpus, row) for row in result.get("navigation", [])]
    return out


_GROUPS = ("blocks", "records", "observations", "entities", "artifacts", "page_checks",
           "methods", "navigation", "method_navigation", "cross_candidates")
_SINGULAR = {"blocks": "block", "records": "record", "observations": "observation",
             "entities": "entity", "artifacts": "artifact", "methods": "method"}
_DISCOVERY_GROUPS = ("candidates", "paths", "combinations", "type_reviews")


def _combination_delivery(row, source_signature):
    """Small previous-delivery summaries, never a second store of evidence."""
    from change_impact import combination_input_refs
    input_refs = combination_input_refs(row)
    bindings = row["plan"].get("bindings", [])
    return {"consumer_ref": row["consumer_ref"], "coverage": row["plan"]["coverage"],
            "inputs": {str(item["need_index"]): {
                "coverage": item["coverage"], "signature": _hash(item),
                "dependencies": source_signature(input_refs.get(item["need_index"], set())),
                "providers": sorted({edge["producer_ref"] for edge in bindings
                                     if edge["consumer_ref"] == row["consumer_ref"]
                                     and edge["need_index"] == item["need_index"]}),
            } for item in row["inputs"]}}


def _combination_change(rid, previous, current):
    before, after = previous["inputs"], current["inputs"]
    inputs = [{"need_index": int(index), "previous": before.get(index, {}).get("coverage"),
               "current": after.get(index, {}).get("coverage"),
               "selected_provider_refs": after.get(index, {}).get("providers", [])}
              for index in sorted(before.keys() | after.keys(), key=int)
              if before.get(index) != after.get(index)]
    return {"id": rid, "consumer_ref": current["consumer_ref"],
            "previous_coverage": previous["coverage"], "current_coverage": current["coverage"],
            "inputs": inputs, "evidence": False,
            "basis": "since_cursor_delivery", "assessment": "candidate"}


def _identity(group, row):
    if group == "blocks":
        return row["page_id"] + "/" + row["block_id"]
    if group in {"navigation", "page_checks"}:
        return row["page_id"]
    if group == "cross_candidates":
        return _encode([row["left_ref"], row["right_ref"]])
    if group == "chain_discovery.candidates":
        return _encode([row["producer_ref"], row["provide_index"], row["consumer_ref"], row["need_index"]])
    if group == "chain_discovery.paths":
        return _encode(row["record_refs"])
    return row["id"]


def _metadata(group, row):
    keys = {"ancestry", "parent_page_id", "title", "path"} if group in {"blocks", "navigation"} else set()
    if group == "methods":
        keys = {"matched_terms", "selection"}
    return {key: row[key] for key in keys if key in row}


def _signature(group, row):
    navigation_keys = _metadata(group, row)
    semantic = {key: value for key, value in row.items() if key not in navigation_keys}
    if group == "blocks":
        # A page move or heading rename does not revise the actual judgment.
        semantic.pop("content_hash", None)
        if "text" in semantic:
            text = semantic["text"]
            if text.startswith('<a id="') and "\n\n" in text:
                semantic["text"] = text.split("\n\n", 1)[1]
    return {"content": _hash(semantic),
            "navigation": _hash(navigation_keys)}


def _source_signatures(corpus, result):
    """Bind conclusions to current source closure without a global revision key."""
    rows = {row["id"]: row for group in ("records", "observations", "entities", "artifacts")
            for row in result.get(group, [])}
    signatures = {rid: _hash(row) for rid, row in rows.items()}
    edges = {}
    for rid, row in rows.items():
        targets = set(corpus.record_dependencies.get(rid, ())) | set(corpus.reverse_corrections.get(rid, ()))
        for field in ("source_refs", "observation_refs", "subject_refs"):
            targets.update(_refs(row.get(field, [])))
        targets.update(ref["artifact_id"] for ref in row.get("artifact_refs", []))
        for field in ("owner_ref", "tenant_ref", "asset_ref"):
            if row.get(field):
                targets.add(row[field])
        for link in row.get("links", []):
            targets.update(_refs(link.get("evidence_refs", [])))
        index = row.get("index", {})
        targets.update(index[field] for field in ("artifact_id", "source_artifact_id") if index.get(field))
        edges[rid] = targets
    cache = {}

    def closure(seeds):
        key = tuple(sorted(seeds))
        if key not in cache:
            found, pending = set(), list(key)
            while pending:
                rid = pending.pop()
                if rid in found:
                    continue
                found.add(rid)
                pending.extend(edges.get(rid, ()))
            cache[key] = _hash({rid: signatures.get(rid, "not_in_returned_package") for rid in sorted(found)})
        return cache[key]

    return closure


def _can_advance(result):
    if result.get("status") == "unavailable":
        return False
    if any(row.get("code") == "snapshot_changed" for row in result.get("gaps", [])):
        return False
    return not any(row.get("status") == "unavailable"
                   for group in ("observations", "artifacts", "page_checks") for row in result.get(group, []))


def _block_dependency_signatures(result, source_signature):
    """Required Wiki judgments and freshness checks belong to source closure too."""
    blocks = {row["page_id"] + "/" + row["block_id"]: row for row in result.get("blocks", [])}
    checks = {row["page_id"]: row for row in result.get("page_checks", [])}
    fingerprints = {key: {
        "judgment": _signature("blocks", row)["content"],
        "sources": source_signature(_refs(row.get("source_refs", []))),
        "page_check": _hash(checks.get(row["page_id"])),
    } for key, row in blocks.items()}
    signatures = {}
    for root in blocks:
        found, pending = set(), [root]
        while pending:
            key = pending.pop()
            if key in found:
                continue
            found.add(key)
            pending.extend(ref["page_id"] + "/" + ref["block_id"]
                           for ref in blocks.get(key, {}).get("required_block_refs", []))
        signatures[root] = _hash({key: fingerprints.get(key, "not_in_returned_package") for key in sorted(found)})
    return signatures


def _load_cursor(path, scope):
    """Delivery acknowledgements are disposable; malformed cache is not evidence loss."""
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(previous, dict) or any(previous.get(key) != value for key, value in scope.items()):
            raise ValueError("cursor scope mismatch")
        if not isinstance(previous.get("delivered"), dict) or not isinstance(previous.get("queries", {}), dict):
            raise ValueError("invalid cursor maps")
        if previous.get("context_epoch") is not None and not isinstance(previous["context_epoch"], str):
            raise ValueError("invalid context epoch")
        for key, signature in previous["delivered"].items():
            identity = json.loads(key)
            if (not isinstance(identity, list) or len(identity) != 2
                    or not all(isinstance(value, str) for value in identity)
                    or not isinstance(signature, dict)
                    or not all(isinstance(signature.get(field), str) for field in ("content", "navigation"))):
                raise ValueError("invalid delivery signature")
            if ("dependencies" in signature and not isinstance(signature["dependencies"], str)
                    or "review_consumer" in signature and not isinstance(signature["review_consumer"], str)):
                raise ValueError("invalid dependency signature")
            if identity[0] == "chain_discovery.combinations" or "combination" in signature:
                combination = signature.get("combination")
                if (not isinstance(combination, dict) or not isinstance(combination.get("consumer_ref"), str)
                        or "coverage" not in combination or not isinstance(combination.get("inputs"), dict)
                        or any(not index.isdecimal() or not isinstance(row, dict)
                               for index, row in combination["inputs"].items())):
                    raise ValueError("invalid combination signature")
        if any(not isinstance(value, str) for value in previous.get("queries", {}).values()):
            raise ValueError("invalid query signature")
        return previous, False
    except FileNotFoundError:
        return None, False
    except (OSError, UnicodeError, ValueError, TypeError):
        return None, True


def _save_cursor(path, saved):
    """Replace only a fully written acknowledgement; interrupted writes retain the old one."""
    path.parent.mkdir(exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(_encode(saved) + "\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def finalize_context(corpus, result, *, view="compact", cursor=None, refresh=False, context_epoch=None):
    """Apply a view after retrieval; an optional cursor sends only changed units.

    ``refresh`` resets all remembered delivery signatures for this view/cursor,
    then sends the complete current query result. Nonmatching old IDs are never
    interpreted as deleted. Evidence reads without a cursor retain their exact
    original low-level contract.
    """
    if view not in {"compact", "evidence"}:
        raise ValueError("view must be compact or evidence")
    if cursor is not None and (not isinstance(cursor, str) or not cursor.strip()):
        raise ValueError("cursor must be a nonempty name")
    if (refresh or context_epoch is not None) and cursor is None:
        raise ValueError("refresh/context_epoch requires a cursor")
    if context_epoch is not None and (not isinstance(context_epoch, str) or not context_epoch.strip()):
        raise ValueError("context_epoch must be a nonempty string")
    out = (result if view == "evidence" and cursor is None else
           _compact(corpus, result) if view == "compact" and result.get("view") != "compact"
           else {**result, "budget": dict(result["budget"]), "view": view})
    if (view == "compact" or cursor is not None) and not any(
            gap.get("code") == "snapshot_changed" for gap in result.get("gaps", [])):
        out["task_core"] = task_core(corpus, result)
    cursor_path, saved = None, None
    if cursor is not None:
        scope = {"version": 2, "run_id": corpus.run_id, "session_id": corpus.state.get("session_id"), "view": view}
        cursor_path = Path(corpus.root) / "cache" / ("context-" + _hash({**scope, "cursor": cursor}) + ".json")
        previous, invalid_cursor = (None, False) if refresh else _load_cursor(cursor_path, scope)
        epoch_changed = previous is not None and previous.get("context_epoch") != context_epoch
        reset_reason = ("explicit_refresh" if refresh else "invalid_cursor" if invalid_cursor else
                        "context_epoch_changed" if epoch_changed else "new_cursor" if previous is None else None)
        refresh = refresh or epoch_changed
        delivered = {} if refresh or previous is None else dict(previous["delivered"])
        queries = {} if refresh or previous is None else dict(previous.get("queries", {}))
        saved = {**scope, "context_epoch": context_epoch, "delivered": dict(delivered), "queries": queries}
        source_view = _compact(corpus, result) if view == "evidence" else out
        query_units = {}
        source_signature = _source_signatures(corpus, source_view)
        block_dependencies = _block_dependency_signatures(source_view, source_signature)
        delta = {"cursor": cursor, "refresh": refresh, "context_epoch": context_epoch, "reset_reason": reset_reason, "scope": "current_result_only", "changes": [],
                 "metadata_changes": [], "cursor_advanced": False}
        unchanged = []

        def changed(group, row):
            rid = _identity(group, row)
            kind = _SINGULAR.get(group, group)
            key = _encode([kind, rid])
            current = _signature(group, row)
            if group in {"records", "entities"}:
                current["dependencies"] = source_signature([rid])
            elif group == "blocks":
                current["dependencies"] = block_dependencies[rid]
            elif group == "chain_discovery.combinations":
                current["dependencies"] = source_signature(row["record_refs"])
                current["combination"] = _combination_delivery(row, source_signature)
            elif group == "chain_discovery.type_reviews":
                current["review_consumer"] = row["consumer_ref"]
            old = delivered.get(key)
            saved["delivered"][key] = current
            query_units[key] = current
            ref = {"kind": kind, "id": rid}
            if current == old:
                unchanged.append(ref)
                return False
            if old is not None:
                if current["content"] == old["content"] and current.get("dependencies") == old.get("dependencies"):
                    update = {**ref, **_metadata(group, row)}
                    if group == "blocks" and "content_hash" in row:
                        update["content_hash"] = row["content_hash"]
                    delta["metadata_changes"].append(update)
                    return False
                reason = "dependencies" if current["content"] == old["content"] else "content"
                delta["changes"].append({**ref, "change": reason})
                if group == "chain_discovery.combinations":
                    delta.setdefault("combination_changes", []).append(
                        _combination_change(rid, old["combination"], current["combination"]))
            return True

        for group in _GROUPS:
            out[group] = [row for row in out.get(group, []) if changed(group, row)]
        out["chain_discovery"] = dict(out.get("chain_discovery", {}))
        for group in _DISCOVERY_GROUPS:
            out["chain_discovery"][group] = [row for row in out["chain_discovery"].get(group, [])
                                              if changed("chain_discovery." + group, row)]
        request = result.get("retrieval_request")
        if request is not None:
            request_key = _hash({**request, "budget_chars": result["budget"].get("limit_chars")})
            # Reuse per-unit signatures already computed for delta delivery;
            # do not serialize all compact bodies again to detect repeats.
            current_result = _hash({"state_revision": result["state_revision"], "units": query_units,
                "question_context": result.get("question_context"), "gaps": result.get("gaps", []),
                "discovery_issues": result.get("chain_discovery", {}).get("issues", [])})
            complete = _can_advance(result) and not result["budget"].get("omitted_units", 0)
            repeated = complete and queries.get(request_key) == current_result
            out["retrieval_progress"] = {
                "same_request_unchanged": repeated, "evidence": False,
                "recommendation": ("stop_repeating_query" if repeated else
                                   "inspect_material" if complete else "resolve_incomplete_retrieval"),
                "basis": "same_request_and_current_result_since_cursor_delivery",
                "answer_support": "not_assessed"}
            if complete:
                saved["queries"][request_key] = current_result

        # A removed Wiki block is known from the complete current manifest,
        # independently of this query's matches. Never infer removal from an
        # unreadable manifest or simply from a different query result.
        if _can_advance(result) and not getattr(corpus, "load_issues", []):
            for key in delivered:
                kind, rid = json.loads(key)
                if kind == "block" and rid not in corpus.blocks:
                    delta.setdefault("removed_refs", []).append({"kind": kind, "id": rid,
                        "reason": "removed_from_current_manifest", "evidence": False})
                    saved["delivered"].pop(key, None)
        # Only retire a derived view when its consumer was actually revisited.
        # Absence from a different query still says nothing about deletion.
        revisited = set(result.get("chain_discovery", {}).get("record_refs", []))
        can_retire = _can_advance(result) and not result["budget"].get("omitted_units", 0)
        for group in ("combinations", "type_reviews"):
            kind = "chain_discovery." + group
            present = {row["id"] for row in result.get("chain_discovery", {}).get(group, [])}
            for key, old in delivered.items():
                previous_kind, rid = json.loads(key)
                consumer = (old.get("combination", {}).get("consumer_ref") if group == "combinations"
                            else old.get("review_consumer"))
                if can_retire and previous_kind == kind and consumer in revisited and rid not in present:
                    delta.setdefault("retired_refs", []).append({"kind": kind, "id": rid,
                        "consumer_ref": consumer, "reason": "no_longer_emitted_for_current_consumer",
                        "evidence": False})
                    saved["delivered"].pop(key, None)
        out["unchanged_refs"] = unchanged
        out["delta"] = delta

        # Previously delivered content and newly encountered evidence can change
        # the current research direction. This describes the reader's knowledge,
        # not a claim that every newly encountered record was just created.
        if (previous is not None and not refresh
                and result.get("retrieval_request", {}).get("mode") != "lexical"
                and result.get("status") != "unavailable"
                and not any(row.get("code") == "snapshot_changed" for row in result.get("gaps", []))):
            changed_refs = [row["id"] for group in ("records", "observations", "entities", "artifacts")
                            for row in out.get(group, [])]
            changed_refs.extend(row["page_id"] + "/" + row["block_id"] for row in out.get("blocks", []))
            if changed_refs:
                from change_impact import build_impact
                from telemetry import measure
                with measure(getattr(corpus, "metrics", None), "change_impact"):
                    out["change_impact"] = build_impact(corpus, changed_refs,
                                                       discovery=result.get("chain_discovery", {}))
                out["change_impact"]["basis"] = "new_or_changed_since_cursor_delivery"

    # Task-core and impact expansion can touch sources after initial retrieval.
    # Never acknowledge a delta assembled across two different snapshots.
    if not corpus.stable():
        out = {"run_id": corpus.run_id, "state_revision": corpus.state["revision"],
               "status": "unavailable", "view": view,
               "gaps": [{"code": "snapshot_changed", "detail": "资料在视图构建期间变化，请重新读取。"}],
               "budget": {**result["budget"], "used_chars": 0},
               **{group: [] for group in _GROUPS},
               "chain_discovery": {group: [] for group in _DISCOVERY_GROUPS}}
        if cursor is not None:
            out["delta"] = {"cursor_advanced": False}
        _measure(out)
        return out
    limit = out["budget"].get("limit_chars")
    if cursor is not None:
        out["delta"]["cursor_advanced"] = _can_advance(result)
    required_chars = _measure(out)
    if limit is not None and required_chars > limit:
        discarded = sum(len(out.get(group, [])) for group in (*_GROUPS, "unchanged_refs"))
        discarded += sum(len(out.get("chain_discovery", {}).get(group, [])) for group in _DISCOVERY_GROUPS)
        discarded += sum(len(out.get("delta", {}).get(group, []))
                         for group in ("metadata_changes", "combination_changes", "retired_refs", "removed_refs"))
        discarded += sum(len(value) for key, value in out.get("change_impact", {}).items()
                         if isinstance(value, list) and key != "changed_refs")
        out = {"run_id": corpus.run_id, "state_revision": corpus.state["revision"], "status": "unavailable",
               "view": view, "gaps": [{"code": "budget_exhausted",
               "detail": "完整视图和差量引用超过本次输出预算，请增加预算；资料本身未据此判为无效。"}],
               "budget": {"limit_chars": limit, "used_chars": 0, "required_chars": required_chars,
                          "omitted_units": result["budget"].get("omitted_units", 0) + discarded}}
        if cursor is not None:
            out["delta"] = {"cursor_advanced": False}
        if "task_core" in result or view == "compact":
            trial = {**out, "budget": dict(out["budget"]), "task_core": task_core(corpus, result)}
            if _measure(trial) <= limit:
                out = trial
        _measure(out)
        return out
    if saved is not None and out["delta"]["cursor_advanced"]:
        _save_cursor(cursor_path, saved)
    return out
