"""Small ranking hints from declared context and verified record mirrors.

These helpers never establish evidence validity. The selected record still goes
through Corpus.package and its complete source checks.
"""

from conditions import check


def condition_signal(corpus, key, row):
    """Compare only explicitly requested axes; unknown conditions are neutral."""
    current = getattr(corpus, "current_conditions", {})
    if not current:
        return None
    declared = row.get("conditions", {})
    if key[0] == "block":
        page = corpus.pages.get(row["page_id"], {})
        owner = mirror_owner(corpus, key[1])
        inherited = corpus.records[owner[1]].get("conditions", {}) if owner else {}
        declared = {**inherited, **page.get("conditions", {}), **declared}
    required = {axis: declared.get(axis) for axis in current}
    conflicts, unknown = check(current, required)
    unresolved = {item["constraint"] for item in conflicts + unknown}
    matched = [{"constraint": axis, "provided": current[axis], "required": required[axis]}
               for axis in sorted(current) if axis not in unresolved]
    return {"multiplier": 1 + 0.15 * (len(matched) - len(conflicts)) / len(current),
            "matched": matched, "conflicts": conflicts, "unknown": unknown}


def mirror_owner(corpus, bid, exact=()):
    """Identify a current generated copy without discarding authored semantics.

    Only revision-pinned mirrors can be folded. Explicit block requests, additional
    conditions, knowledge, and dependencies retain a separately addressable block.
    The caller supplies index/page integrity checks; this helper performs no I/O.
    """
    if ("block", bid) in exact:
        return None
    block = corpus.blocks.get(bid)
    if not block or block.get("representation") != "record":
        return None
    if (block.get("role", "explanation") != "explanation" or "knowledge" in block
            or block.get("required_block_refs") or block.get("artifact_refs")):
        return None
    refs = block.get("source_refs", [])
    if not isinstance(refs, list) or len(refs) != 1 or not isinstance(refs[0], dict):
        return None
    ref = refs[0]
    owner = corpus.records.get(ref.get("id"))
    if owner is None or ref.get("revision") is None or ref["revision"] != owner.get("revision"):
        return None
    page = corpus.pages.get(block["page_id"])
    if page is None:
        return None
    declared = {**page.get("conditions", {}), **block.get("conditions", {})}
    if any(owner.get("conditions", {}).get(axis) != value for axis, value in declared.items()):
        return None
    if block.get("_issues") or getattr(corpus, "page_issues", {}).get(block["page_id"]):
        return None
    return "record", ref["id"]
