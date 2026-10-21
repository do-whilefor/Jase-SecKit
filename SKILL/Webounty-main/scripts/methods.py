"""Select complete built-in method cards; never treat methods as target evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


SKILL_ROOT = Path(__file__).resolve().parents[1]
METHOD_DIRECTORY = Path("references/methods")
MAX_CATALOG_BYTES = 65536
MAX_CARD_BYTES = 32768
MAX_METHODS = 32


def _strings(value, name, *, slugs=False, maximum=128):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{name} must be a bounded list")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 128
           or (slugs and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", item)) for item in value):
        raise ValueError(f"Invalid {name}")
    return list(dict.fromkeys(value))


def _source_refs(value):
    """Validate attribution metadata, without loading external source files at runtime."""
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError("Method sources must be a bounded list")
    for ref in value:
        if not isinstance(ref, dict):
            raise ValueError("Invalid method source")
        path = ref.get("path")
        if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("Method source path must be relative to its named source collection")
        if not isinstance(ref.get("section"), str) or not ref["section"].strip():
            raise ValueError("Method source must identify a section")
        start, end = ref.get("line_start"), ref.get("line_end")
        if type(start) is not int or type(end) is not int or not 1 <= start <= end:
            raise ValueError("Invalid method source line range")
        if not isinstance(ref.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]):
            raise ValueError("Method source requires its reviewed file hash")
    return value


def _bounded_read(path, limit):
    if not path.is_file():
        raise ValueError("Built-in method resource is not a regular file")
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Built-in method resource exceeds its size limit")
    return content


def _method_path(relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError("Method path must be a nonempty relative string")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Method path must remain in the built-in method directory")
    directory = (SKILL_ROOT / METHOD_DIRECTORY).resolve()
    resolved = (SKILL_ROOT / path).resolve()
    if not directory.is_relative_to(SKILL_ROOT) or not resolved.is_relative_to(directory):
        raise ValueError("Method path or symlink escapes the built-in method directory")
    return resolved


def _matches(query, term):
    folded = term.casefold()
    prefix = r"(?<![a-z0-9_])" if re.match(r"[a-z0-9_]", folded[0]) else ""
    suffix = r"(?![a-z0-9_])" if re.match(r"[a-z0-9_]", folded[-1]) else ""
    return re.search(prefix + re.escape(folded) + suffix, query) is not None


def _load_catalog():
    catalog = _method_path((METHOD_DIRECTORY / "catalog.json").as_posix())
    rows = json.loads(_bounded_read(catalog, MAX_CATALOG_BYTES).decode("utf-8"))
    if not isinstance(rows, list) or len(rows) > MAX_METHODS:
        raise ValueError("Method catalog must be a bounded list")
    entries, issues, seen = [], [], set()
    for index, row in enumerate(rows):
        method_id = row.get("id") if isinstance(row, dict) else None
        try:
            if not isinstance(row, dict):
                raise ValueError("Method catalog entry must be an object")
            if not isinstance(method_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", method_id):
                raise ValueError("Invalid method ID")
            if method_id in seen:
                raise ValueError("Duplicate method ID")
            seen.add(method_id)
            if not isinstance(row.get("title"), str) or not row["title"].strip():
                raise ValueError("Method title must be a nonempty string")
            keywords = row.get("keywords")
            if not isinstance(keywords, list) or not 0 < len(keywords) <= 128:
                raise ValueError("Method keywords must be a bounded nonempty list")
            if any(not isinstance(term, str) or not term.strip() or len(term) > 128 for term in keywords):
                raise ValueError("Invalid method keyword")
            intents = _strings(row.get("intents", []), "method intents", slugs=True, maximum=16)
            signals = _strings(row.get("signals", []), "method signals")
            sources = _source_refs(row.get("source_refs", []))
            path = _method_path(row.get("path"))
            if path.suffix != ".md":
                raise ValueError("Method card must be a Markdown file")
            entries.append({**row, "intents": intents, "signals": signals,
                            "source_refs": sources, "_path": path})
        except (OSError, RuntimeError, ValueError) as exc:
            issue = {"code": "method_unavailable", "catalog_index": index, "detail": str(exc)}
            if isinstance(method_id, str):
                issue["method_id"] = method_id
            issues.append(issue)
    return entries, issues


def select_methods(query, method_ids=(), limit=3, *, intents=()):
    """Return method cards and retrieval issues from the packaged catalog only."""
    if not isinstance(query, str):
        return [], [{"code": "methods_unavailable", "detail": "Method query must be a string"}]
    if type(limit) is not int or not 0 <= limit <= MAX_METHODS:
        return [], [{"code": "methods_unavailable", "detail": "Method limit must be an integer from 0 to 32"}]
    if isinstance(method_ids, str):
        method_ids = (method_ids,)
    if not isinstance(method_ids, (list, tuple)) or any(not isinstance(mid, str) for mid in method_ids):
        return [], [{"code": "methods_unavailable", "detail": "Method IDs must be strings"}]
    if isinstance(intents, str):
        intents = (intents,)
    if not isinstance(intents, (list, tuple)) or any(not isinstance(intent, str) for intent in intents):
        return [], [{"code": "methods_unavailable", "detail": "Method intents must be strings"}]
    try:
        entries, issues = _load_catalog()
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        return [], [{"code": "methods_unavailable", "detail": str(exc)}]

    explicit = list(dict.fromkeys(method_ids))
    known = {entry["id"] for entry in entries}
    for method_id in explicit:
        if method_id not in known:
            issues.append({"code": "unknown_method", "method_id": method_id})
    explicit_rank = {method_id: index for index, method_id in enumerate(explicit)}
    requested_intents = list(dict.fromkeys(intents))
    known_intents = {intent for entry in entries for intent in entry["intents"]}
    for intent in requested_intents:
        if intent not in known_intents:
            issues.append({"code": "unknown_method_intent", "intent": intent})
    intent_rank = {intent: index for index, intent in enumerate(requested_intents)}
    folded = query.casefold()
    ranked = []
    for entry in entries:
        matches = sorted({term for term in entry["keywords"] if _matches(folded, term)})
        signals = sorted({term for term in entry["signals"] if _matches(folded, term)})
        matched_intents = sorted(set(entry["intents"]) & intent_rank.keys(), key=intent_rank.get)
        if entry["id"] in explicit_rank:
            tier, order, reason = 0, explicit_rank[entry["id"]], "explicit_id"
        elif matched_intents:
            tier, order, reason = 1, intent_rank[matched_intents[0]], "explicit_intent"
        elif signals:
            tier, order, reason = 2, 0, "signal_match"
        elif matches:
            tier, order, reason = 3, 0, "keyword_match"
        else:
            continue
        # Keyword padding must not gain priority over a precise diagnostic signal.
        coverage = len(matches) / len(set(entry["keywords"]))
        rank = (tier, order, -min(len(signals), 3), -coverage, -len(matches), entry["id"])
        selection = {"reason": reason, "matched_intents": matched_intents,
                     "matched_signals": signals}
        ranked.append((rank, entry, matches, selection))
    ranked.sort(key=lambda item: item[0])

    selected = []
    for _, entry, matches, selection in ranked:
        if len(selected) >= limit:
            break
        try:
            raw = _bounded_read(entry["_path"], MAX_CARD_BYTES)
            content = raw.decode("utf-8")
            if not content.strip():
                raise ValueError("Method card is empty")
        except (OSError, UnicodeError, ValueError) as exc:
            issues.append({"code": "method_unavailable", "method_id": entry["id"], "detail": str(exc)})
            continue
        selected.append({"id": entry["id"], "title": entry["title"], "kind": "method",
                         "evidence": False, "content": content, "path": entry["path"],
                         "sha256": hashlib.sha256(raw).hexdigest(), "matched_terms": matches,
                         "intents": entry["intents"], "selection": selection,
                         "source_refs": entry["source_refs"],
                         "source_collection": "Web-Vulnhunt" if entry["source_refs"] else None,
                         "applicability": "requires_current_run_verification"})
    selected_ids = {entry["id"] for entry in selected}
    failed = {issue.get("method_id") for issue in issues if issue["code"] == "method_unavailable"}
    for method_id in explicit:
        if method_id in known - selected_ids - failed:
            issues.append({"code": "method_not_selected", "method_id": method_id, "reason": "selection_limit"})
    selected_intents = {intent for entry in selected for intent in entry["intents"]}
    for intent in requested_intents:
        if intent in known_intents - selected_intents:
            issues.append({"code": "method_intent_not_selected", "intent": intent,
                           "reason": "selection_limit_or_unavailable"})
    return selected, issues


def retrieve_methods(query, method_ids=(), *, intents=(), limit=3, budget_chars=12000):
    """Read methods without requiring or manufacturing a current target run."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Method query must be nonempty")
    if type(budget_chars) is not int or not 1024 <= budget_chars <= 2_000_000:
        raise ValueError("Method budget must be from 1024 to 2000000 characters")
    cards, issues = select_methods(query, method_ids, limit, intents=intents)
    result = {"kind": "method_context", "evidence": False, "status": "ready",
              "methods": [], "navigation": [], "issues": issues,
              "budget": {"limit_chars": budget_chars, "used_chars": 0}}

    def measure(value):
        while True:
            size = len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            if size == value["budget"]["used_chars"]:
                return size
            value["budget"]["used_chars"] = size

    for card in cards:
        result["methods"].append(card)
        if measure(result) > budget_chars - 256:
            result["methods"].pop()
            result["navigation"].append({"id": card["id"], "path": card["path"], "reason": "budget_exhausted"})
    result["status"] = ("review_required" if issues or result["navigation"]
                        else "ready" if result["methods"] else "no_match")
    if measure(result) > budget_chars:
        result["methods"], result["navigation"] = [], []
        result["issues"] = [{"code": "budget_exhausted", "detail": "Method diagnostics exceed the budget"}]
        result["status"] = "unavailable"
        measure(result)
    return result
