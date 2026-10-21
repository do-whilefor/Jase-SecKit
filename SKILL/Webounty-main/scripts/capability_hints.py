"""Lexical review prompts for unresolved capability expressions, never edges.

An authored whole type or alias is the only mechanical type match. Shared words
can help the host find originals worth rereading, but cannot establish synonyms,
usable supply, or a working connection. This module only derives review data.
"""

from __future__ import annotations

from collections import defaultdict
import re
import unicodedata


def _terms(value):
    """Return visible lexical units without translation or semantic expansion."""
    if not isinstance(value, str):
        return set()
    value = unicodedata.normalize("NFKC", value).casefold()
    terms = set()
    for token in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", value):
        if "\u3400" <= token[0] <= "\u9fff" and len(token) > 1:
            terms.update(token[index:index + 2] for index in range(len(token) - 1))
        else:
            terms.add(token)
    return terms


def _spec_terms(spec):
    result = _terms(spec.get("type", "")) | _terms(spec.get("description", ""))
    for alias in spec.get("aliases", []):
        result.update(_terms(alias))
    return result


def build_type_reviews(records, focus_refs, candidates=None):
    """Review focused needs with missing expressions or unusable exact matches.

    ``records`` is the full-session record mapping, not the retrieved subset.
    A matching but unusable or conflicting provider still counts as a type
    match. When supplied, ``candidates`` must contain all current discovery
    candidates. Only their complete, explicit diagnostics can trigger a review
    of alternative expressions when every exact match is unusable or conflicts.
    Missing diagnostics or a still-reviewable exact match preserve the default.
    Own outputs do not satisfy own inputs. Provider text is tokenized once into
    postings, so each unmatched need visits only providers sharing its terms.
    No cap hides reviews or lexical alternatives, and no input is modified.
    """
    # Imported when called so discovery can import this module at initialization
    # while both features continue to use exactly the same matching semantics.
    from discovery import _constraint_check, _names

    focus = sorted(rid for rid in set(focus_refs) if rid in records)
    demands = [(rid, index, spec) for rid in focus
               for index, spec in enumerate(records[rid].get("capability", {}).get("needs", []))]
    if not demands:
        return []

    metadata = getattr(records, "relations", None)
    names = metadata.links("named_provides") if metadata is not None else defaultdict(set)
    postings = metadata.links("hint_term") if metadata is not None else defaultdict(set)
    providers, record_terms = {}, {}
    diagnosed = defaultdict(lambda: defaultdict(list))
    for edge in candidates or ():
        diagnosed[(edge.get("consumer_ref"), edge.get("need_index"))][
            (edge.get("producer_ref"), edge.get("provide_index"))].append(edge)

    def context_terms(rid):
        if rid not in record_terms:
            row = records[rid]
            record_terms[rid] = _terms(row.get("summary", "")) | _terms(row.get("title", ""))
        return record_terms[rid]

    for rid, row in (() if metadata is not None else records.items()):
        for index, spec in enumerate(row.get("capability", {}).get("provides", [])):
            key = (rid, index)
            providers[key] = spec
            for name in _names(spec):
                names[name].add(key)

    unresolved = []
    for cid, index, need in demands:
        matching = {key for name in _names(need) for key in names[name] if key[0] != cid}
        if not matching:
            unresolved.append((cid, index, need, matching, "no_complete_type_or_alias_match"))
            continue
        current = diagnosed[(cid, index)]
        # Verify coverage against the full-session whole-name index. A partial
        # candidate list must not hide another exact provider or another output.
        if not matching.issubset(current):
            continue
        if all(edge.get("consumer_usable") is True
               and isinstance(edge.get("producer_usable"), bool)
               and edge.get("compatibility") in {"compatible", "unknown", "incompatible"}
               and (edge["producer_usable"] is False or edge["compatibility"] == "incompatible")
               for key in matching for edge in current[key]):
            unresolved.append((cid, index, need, matching,
                               "all_complete_matches_unusable_review_alternatives"))
    if not unresolved:
        return []

    for key, spec in providers.items():
        for term in _spec_terms(spec) | context_terms(key[0]):
            postings[term].add(key)

    reviews = []
    for cid, need_index, need, matching, reason in unresolved:
        shared = defaultdict(set)
        # A consumer summary can describe several inputs. Its unrelated terms
        # must not turn a known sibling provider into a hint for this gap.
        for term in _spec_terms(need):
            for key in postings.get(term, ()):
                # Existing exact matches remain in discovery with their source
                # and conflict diagnostics; this list is only for other names.
                if key[0] != cid and key not in matching:
                    shared[key].add(term)

        suggestions = []
        for key in sorted(shared, key=lambda key: (-len(shared[key]), key)):
            pid, provide_index = key
            provided = (records[pid]["capability"]["provides"][provide_index]
                        if metadata is not None else providers[key])
            conflicts, unknown = _constraint_check(provided, need)
            suggestions.append({
                "producer_ref": pid, "provide_index": provide_index, "type": provided["type"],
                "matched_terms": sorted(shared[key]), "reason": "lexical_overlap_only",
                "assessment": "review_required", "evidence": False,
                "producer_status": records[pid].get("status", "unknown"),
                "conditions": {"provided": dict(provided.get("constraints", {})),
                               "required": dict(need.get("constraints", {}))},
                "conflicts": conflicts, "unknown_conditions": unknown,
                "record_refs": [pid, cid],
            })

        message = (
            "Use read --id with record_refs to inspect producer and consumer originals. Shared terms only identify "
            "expressions to review; they do not prove synonyms, usable supply, or a connection."
            if suggestions else
            "No lexical connection was found. Use read --id with the consumer_ref, "
            "check the capability expression, or obtain a new capability."
        )
        if matching:
            message = (
                "Complete type or alias matches exist, but every current matching candidate has an "
                "unusable provider or explicit condition conflict. Review alternative capability "
                "expressions; this is not a missing-type finding. " + message
            )
        reviews.append({
            "id": f"type-review:{cid}:{need_index}", "consumer_ref": cid,
            "need_index": need_index, "type": need["type"],
            "assessment": "review_required", "evidence": False,
            "reason": reason, "message": message,
            "suggestions": suggestions,
            "record_refs": sorted({cid, *(item["producer_ref"] for item in suggestions)}),
        })
    return reviews
