"""Session-local capability discovery; all returned connections remain hypotheses.

The index scans the full current corpus before retrieval packages are assembled.
It uses authored types/aliases, never CVSS, arbitrary token overlap, or an LLM.
Paths are representative shortest paths around the requested anchors, not an
exponential enumeration of every possible chain or a claim of exploitability.
"""

from __future__ import annotations

from collections import defaultdict, deque
import json
import re
import unicodedata

from conditions import check as check_conditions
from search_index import query_terms


UNUSABLE = frozenset({
    "refuted", "corrected", "superseded", "stale", "withdrawn", "rejected",
    "invalidated", "needs_review", "review_required", "failed", "disproved",
})
TENTATIVE = frozenset({"candidate", "hypothesis", "pending", "unverified", "unknown"})
CORRECTIONS = ("corrected_by", "correction_refs", "superseded_by", "contradicted_by")
# Forward supporting relations from rag.dependencies. Correction/opposition
# relations are checked separately; Chain.steps/links are navigation, not proof.
SUPPORT_RELATIONS = ("requires", "evidence_refs", "step_refs", "supporting_fact_ids", "source_refs")


def _refs(values):
    if isinstance(values, (str, dict)):
        values = [values]
    return [value if isinstance(value, str) else value["id"] for value in values]


def _support_refs(row):
    result = []
    for field in SUPPORT_RELATIONS:
        values = row.get(field, [])
        result.extend([values] if isinstance(values, (str, dict)) else values)
    for entry in row.get("history", []):
        values = entry.get("evidence_refs", [])
        result.extend([values] if isinstance(values, (str, dict)) else values)
    return result


def _name(value):
    # Normalize whole names, not their individual words. "download credential"
    # cannot match "login credential" merely because both contain credential.
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"[\s_-]+", " ", value)


def _names(spec):
    return {_name(name) for name in [spec.get("type", ""), *spec.get("aliases", [])] if name.strip()}


def _terms(value):
    for token in re.findall(r"[a-z0-9_/-]+|[\u3400-\u9fff]+", value.casefold()):
        if "\u3400" <= token[0] <= "\u9fff" and len(token) > 1:
            yield from (token[i:i + 2] for i in range(len(token) - 1))
        else:
            yield token


class _Sources:
    def __init__(self, corpus):
        self.corpus = corpus
        self.cache = {}
        self.reverse = defaultdict(set)
        metadata = getattr(corpus.records, "relations", None)
        if metadata is not None:
            self.reverse = metadata.links("contradiction")
        for rid, row in (() if metadata is not None else corpus.records.items()):
            # "new contradicts old" invalidates its target. Conversely,
            # "old corrected_by/superseded_by new" invalidates its owner;
            # those outward references are handled in inspect(), not reversed.
            for ref in _refs(row.get("contradicts", [])):
                self.reverse[ref].add(rid)

    def basis_issues(self, rid):
        """The same local-basis diagnostics are used by read, context and discovery."""
        row = self.corpus.records[rid]
        issues = []
        if row.get("basis_status") == "needs_review" or row.get("status") in {"needs_review", "review_required"}:
            issues.append({"code": "basis_review_required", "record_id": rid})
        corrections = set(self.reverse[rid])
        for key in CORRECTIONS:
            corrections.update(_refs(row.get(key, [])))
        if corrections:
            issues.append({"code": "record_has_correction", "record_id": rid, "record_refs": sorted(corrections)})
        for source in _support_refs(row):
            sid = source if isinstance(source, str) else source["id"]
            linked = self.corpus.records.get(sid)
            if linked is None:
                issues.append({"code": "missing_source_record", "record_id": rid, "source_id": sid})
            elif isinstance(source, dict) and source.get("revision", linked.get("revision")) != linked.get("revision"):
                issues.append({"code": "stale_source", "record_id": rid, "source_id": sid,
                               "expected": source["revision"], "current": linked.get("revision")})
        current = getattr(self.corpus, "current_conditions", {})
        if current and (row.get("conditions") or row.get("capability") or row.get("observation_refs") or row.get("artifact_refs") or _support_refs(row)):
            declared = dict(row.get("conditions", {}))
            # Only an explicitly declared common execution context is compared.
            # Capability input/output constraints can legitimately describe other actors.
            conflicts, unknown = check_conditions(
                {key: declared[key] for key in current if key in declared}, current)
            for item in conflicts:
                issues.append({"code": "current_condition_conflict", "record_id": rid, **item})
            for item in unknown:
                issues.append({"code": "current_condition_unknown", "record_id": rid, **item})
        return issues

    def inspect(self, rid, trail=()):
        if rid in self.cache:
            return self.cache[rid]
        if rid in trail:
            return {"observations": set(), "artifacts": set(),
                    "issues": [{"code": "source_cycle", "record_id": rid}], "usable": False}
        row = self.corpus.records[rid]
        issues, observations = self.basis_issues(rid), set()
        artifacts = set()
        usable = not issues
        if row.get("status", "").casefold() in UNUSABLE:
            issues.append({"code": "record_unusable", "record_id": rid, "status": row["status"]})
            usable = False
        if row.get("status", "").casefold() in TENTATIVE:
            issues.append({"code": "record_tentative", "record_id": rid})
        for oid in _refs(row.get("observation_refs", [])):
            if oid not in self.corpus.observations:
                issues.append({"code": "missing_observation", "record_id": rid, "observation_id": oid})
                usable = False
                continue
            checked = self.corpus.observation(oid)
            if checked["status"] == "ready":
                observations.add(oid)
            else:
                issues.append({"code": "observation_unavailable", "record_id": rid, "observation_id": oid})
                usable = False
        for ref in row.get("artifact_refs", []):
            artifact_issues = self.corpus.artifact_reference_issues(ref)
            if artifact_issues:
                issues.extend({**issue, "record_id": rid} for issue in artifact_issues)
                usable = False
            else:
                artifacts.add(ref["artifact_id"])
        for source in _support_refs(row):
            sid = source if isinstance(source, str) else source["id"]
            linked = self.corpus.records.get(sid)
            if linked is None:
                usable = False
                continue
            found = self.inspect(sid, (*trail, rid))
            observations.update(found["observations"])
            artifacts.update(found["artifacts"])
            issues.extend(found["issues"])
            usable = usable and found["usable"]
        if not observations and not artifacts:
            issues.append({"code": "no_source_evidence", "record_id": rid})
        result = {"observations": observations, "artifacts": artifacts, "issues": issues, "usable": usable}
        # A result containing a cycle depends on the call trail; avoid memoizing it.
        if not any(issue["code"] == "source_cycle" for issue in issues):
            self.cache[rid] = result
        return result


def _constraint_check(provide, need):
    return check_conditions(provide.get("constraints", {}), need.get("constraints", {}))


def _seeds(corpus, query, anchors, changed):
    records = corpus.records
    metadata = getattr(records, "relations", None)
    seeds = set()
    requested = set(anchors) | set(changed)
    for ref in requested:
        if ref in records:
            seeds.add(ref)
        page = getattr(corpus, "pages", {}).get(ref)
        for page in ([page] if page else []):
            if ref == page.get("page_id"):
                seeds.update(_refs(page.get("source_refs", [])))
                for block in page.get("blocks", []):
                    seeds.update(_refs(block.get("source_refs", [])))
        block = getattr(corpus, "blocks", {}).get(ref)
        if block:
            seeds.update(_refs(block.get("source_refs", [])))
        if metadata is not None:
            seeds.update(metadata.links("record_anchor")[ref])
        else:
            for rid, row in records.items():
                if ref in row.get("subject_refs", []) or ref in _refs(row.get("observation_refs", [])):
                    seeds.add(rid)
    if query.strip():
        terms = query_terms(query, _terms)
        if metadata is not None:
            seeds.update(metadata.union("seed_term", terms))
        for rid, row in (() if metadata is not None else records.items()):
            authored = json.dumps({key: row.get(key) for key in
                                  ("id", "summary", "title", "capability", "subject_refs")}, ensure_ascii=False)
            if terms.intersection(_terms(authored)):
                seeds.add(rid)
        blocks = getattr(corpus, "blocks", {})
        block_rows = blocks.loaded.values() if metadata is not None else blocks.values()
        for block in block_rows:
            if terms.intersection(_terms(block.get("text", ""))):
                seeds.update(_refs(block.get("source_refs", [])))
    # A current blocked step is an appropriate default focus even when the user
    # has not supplied the words describing its missing prerequisite.
    if not seeds and not requested:
        if metadata is not None:
            seeds.update(metadata.links("flag")["default_seeds"])
        else:
            seeds.update(rid for rid, row in records.items()
                         if row.get("capability", {}).get("needs") and row.get("status") in {"active", "blocked"})
    # Goal/Chain anchors can refer to their component records without capability.
    reverse_sources = metadata.links("reverse_support") if metadata is not None else defaultdict(set)
    for rid, row in (() if metadata is not None else records.items()):
        for ref in _refs(_support_refs(row)):
            reverse_sources[ref].add(rid)
    pending = list(seeds)
    while pending:
        rid = pending.pop()
        if rid not in records:
            continue
        row = records[rid]
        linked_refs = set(reverse_sources[rid])
        linked_refs.update(_refs(_support_refs(row)))
        for key in ("steps", "contradicts", *CORRECTIONS):
            linked_refs.update(_refs(row.get(key, [])))
        for linked in linked_refs:
            if linked in records and linked not in seeds:
                seeds.add(linked)
                pending.append(linked)
    return {rid for rid in seeds if rid in records}


def _matching_edges(records, seeds, focused, sources, review_seeds=()):
    """Join full-session type indexes only along the selected component.

    Incompatible boundary edges remain in the result. Their far endpoints are
    not expanded, so unrelated tenants sharing a type do not form a global
    producer-by-consumer product before the relevant component is selected.
    Explicit changes additionally follow nonconflicting downstream references
    for review, even after withdrawal. This does not make those edges usable.
    """
    provided, needed = defaultdict(set), defaultdict(set)
    provides, needs = {}, {}
    record_provides, record_needs = defaultdict(list), defaultdict(list)
    metadata = getattr(records, "relations", None)
    if metadata is not None:
        provided, needed = metadata.links("named_provides"), metadata.links("named_needs")
        provides, needs = metadata.links("provides"), metadata.links("needs")
        record_provides, record_needs = metadata.links("record_provides"), metadata.links("record_needs")
    for rid, row in (() if metadata is not None else records.items()):
        for field, names_by_spec, by_name, by_record in (
            ("provides", provides, provided, record_provides),
            ("needs", needs, needed, record_needs),
        ):
            for index, spec in enumerate(row.get("capability", {}).get(field, [])):
                key = (rid, index)
                names_by_spec[key] = _names(spec)
                by_record[rid].append(key)
                for name in names_by_spec[key]:
                    by_name[name].add(key)

    def outgoing(key):
        pid, pindex = key
        for name in provides[key]:
            for cid, nindex in needed[name]:
                if pid != cid:
                    yield pid, cid, pindex, nindex

    def incoming(key):
        cid, nindex = key
        for name in needs[key]:
            for pid, pindex in provided[name]:
                if pid != cid:
                    yield pid, cid, pindex, nindex

    checks, viable = {}, {}

    def assess(edge):
        pid, cid, pindex, nindex = edge
        checks[edge] = _constraint_check(records[pid]["capability"]["provides"][pindex],
                                         records[cid]["capability"]["needs"][nindex])

    def usable(rid):
        if rid not in viable:
            row = records[rid]
            viable[rid] = not (row.get("basis_status") == "needs_review"
                               or row.get("status", "").casefold() in UNUSABLE
                               or sources.reverse[rid]
                               or any(row.get(key) for key in CORRECTIONS))
        return viable[rid]

    review_reached = set(review_seeds)
    if focused:
        seen, pending = set(seeds), deque(sorted(seeds))
        while pending:
            rid = pending.popleft()
            for keys, matching in ((record_provides[rid], outgoing), (record_needs[rid], incoming)):
                for key in keys:
                    for edge in matching(key):
                        if edge not in checks:
                            assess(edge)
                        pid, cid, _, _ = edge
                        if checks[edge][0]:
                            continue
                        if pid == rid and rid in review_reached and cid not in review_reached:
                            # A consumer may already have been visited through
                            # a usable edge. Revisit it once when a changed
                            # downstream review route reaches it, so a later
                            # unusable edge cannot hide dependent AND groups.
                            review_reached.add(cid)
                            seen.add(cid)
                            pending.append(cid)
                        if usable(pid) and usable(cid):
                            other = cid if pid == rid else pid
                            if other not in seen:
                                seen.add(other)
                                pending.append(other)
    else:
        # An unfocused request still returns every actual type/alias match.
        for key in needs:
            for edge in incoming(key):
                if edge not in checks:
                    assess(edge)
    return checks, provides, needs, review_reached


def _missing(records, route, by_need):
    """Account for every input on every step, including the first producer.

    Even a compatible candidate is only a proposed satisfier. The returned
    bindings and path-wide validation requirement make that distinction explicit.
    """
    positions = {rid: index for index, rid in enumerate(route)}
    missing, bindings = [], []
    for rid in route:
        for index, need in enumerate(records[rid].get("capability", {}).get("needs", [])):
            providers = [edge for edge in by_need.get((rid, index), ())
                         if edge["producer_ref"] in positions
                         and positions[edge["producer_ref"]] < positions[rid]]
            compatible = [edge for edge in providers
                          if edge["compatibility"] == "compatible" and edge["producer_usable"]]
            if compatible:
                bindings.append({"record_ref": rid, "need_index": index,
                                 "producer_refs": sorted({edge["producer_ref"] for edge in compatible}),
                                 "assessment": "candidate", "evidence": False})
                continue
            missing.append({"record_ref": rid, "need_index": index, "type": need["type"],
                            "constraints": need.get("constraints", {}),
                            "reason": "connection_unresolved" if providers else "no_prior_provider_in_path",
                            "candidate_provider_refs": sorted({edge["producer_ref"] for edge in providers}),
                            "unknown_conditions": [condition for edge in providers for condition in edge["unknown_conditions"]],
                            "conflicts": [conflict for edge in providers for conflict in edge["conflicts"]]})
    return missing, bindings


def _paths(records, candidates, seeds):
    forward, backward = defaultdict(list), defaultdict(list)
    by_need = defaultdict(list)
    for edge in candidates:
        by_need[(edge["consumer_ref"], edge["need_index"])].append(edge)
        if edge["compatibility"] == "incompatible" or not edge["producer_usable"] or not edge["consumer_usable"]:
            continue
        forward[edge["producer_ref"]].append(edge)
        backward[edge["consumer_ref"]].append(edge)
    for edges in [*forward.values(), *backward.values()]:
        edges.sort(key=lambda edge: (edge["compatibility"] != "compatible", edge["producer_ref"], edge["consumer_ref"]))
    routes = set()
    # One BFS in either direction per focus. All direct alternatives remain in
    # candidates; the paths show a compact representative route to each endpoint.
    for seed in sorted(seeds):
        upstream, downstream = [], []
        for adjacency, reverse in ((forward, False), (backward, True)):
            queue, visited = deque([(seed,)]), {seed}
            while queue:
                route = queue.popleft()
                for edge in adjacency.get(route[-1], []):
                    nxt = edge["producer_ref"] if reverse else edge["consumer_ref"]
                    if nxt in visited:
                        continue
                    visited.add(nxt)
                    extended = (*route, nxt)
                    actual = tuple(reversed(extended)) if reverse else extended
                    routes.add(actual)
                    (upstream if reverse else downstream).append(actual)
                    queue.append(extended)
        # A newly learned bridge may sit in the middle of the useful chain.
        # Join representative prefix/suffix routes, never arbitrary simple
        # paths. There is at most one prefix/suffix per endpoint for this focus.
        for prefix in upstream:
            for suffix in downstream:
                if set(prefix[:-1]).intersection(suffix[1:]):
                    continue
                routes.add((*prefix, *suffix[1:]))
    result = []
    for route in sorted(routes, key=lambda route: (-len(route), route)):
        missing, bindings = _missing(records, route, by_need)
        result.append({"record_refs": list(route), "missing_preconditions": missing,
                       "bindings": bindings, "status": "candidate", "evidence": False,
                       "validation_required": "Verify each connection and simultaneous end-to-end conditions with original evidence."})
    return result


def discover(corpus, query="", anchors=(), changed=()):
    """Find full-corpus supply/demand candidates, then focus on related branches.

    compatibility only describes declared type/condition/source consistency.
    It never verifies that an actual output works as an actual downstream input.
    No write, network, embedding service, model call, or hidden output cap occurs.
    """
    anchors, changed = tuple(anchors), tuple(changed)
    records = corpus.records
    seeds = _seeds(corpus, query, anchors, changed)
    sources = _Sources(corpus)
    focused_request = bool(query.strip() or anchors or changed or seeds)
    review_seeds = _seeds(corpus, "", (), changed) if changed else set()
    checks, provided_names, needed_names, review_reached = _matching_edges(
        records, seeds, focused_request, sources, review_seeds)
    candidates = []
    for pid, cid, pindex, nindex in sorted(checks):
        conflicts, unknown = checks[(pid, cid, pindex, nindex)]
        producer, consumer = sources.inspect(pid), sources.inspect(cid)
        source_issues = producer["issues"] + consumer["issues"]
        compatibility = "incompatible" if conflicts else "unknown" if unknown or source_issues else "compatible"
        reason = {"compatible": "Declared types and conditions match; connection still needs validation.",
                  "unknown": "Type matches, but conditions or supporting sources remain unresolved.",
                  "incompatible": "Type matches, but explicit conditions conflict."}[compatibility]
        candidates.append({"producer_ref": pid, "consumer_ref": cid,
                           "provide_index": pindex, "need_index": nindex,
                           "compatibility": compatibility, "missing_preconditions": [],
                           "conflicts": conflicts, "unknown_conditions": unknown,
                           "reason": reason, "matched_names": sorted(provided_names[(pid, pindex)] & needed_names[(cid, nindex)]),
                           "evidence": False, "record_refs": [pid, cid],
                           "observation_refs": sorted(producer["observations"] | consumer["observations"]),
                           "artifact_refs": sorted(producer["artifacts"] | consumer["artifacts"]),
                           "source_issues": source_issues,
                           "producer_usable": producer["usable"], "consumer_usable": consumer["usable"]})

    # Changed downstream references are review scope, not usable connections.
    # Keep them when filtering so a withdrawn upstream provider does not erase
    # the downstream combination whose prerequisites now require review.
    # Explicitly incompatible branches still stop both kinds of traversal.
    connected = set(seeds) | review_reached
    adjacency = defaultdict(set)
    for edge in candidates:
        if edge["compatibility"] != "incompatible" and edge["producer_usable"] and edge["consumer_usable"]:
            adjacency[edge["producer_ref"]].add(edge["consumer_ref"])
            adjacency[edge["consumer_ref"]].add(edge["producer_ref"])
    pending = deque(sorted(connected))
    while pending:
        for rid in sorted(adjacency[pending.popleft()] - connected):
            connected.add(rid)
            pending.append(rid)
    if focused_request:
        candidates = [edge for edge in candidates if connected.intersection(edge["record_refs"])]
    priority = {"compatible": 0, "unknown": 1, "incompatible": 2}
    changed_refs = set(changed)
    candidates.sort(key=lambda edge: (
        not bool(changed_refs.intersection(edge["record_refs"])),
        not bool(seeds.intersection(edge["record_refs"])),
        priority[edge["compatibility"]], edge["producer_ref"], edge["consumer_ref"],
        edge["provide_index"], edge["need_index"]))
    pairs = defaultdict(lambda: defaultdict(list))
    for edge in candidates:
        pairs[tuple(edge["record_refs"])][(edge["consumer_ref"], edge["need_index"])].append(edge)
    for edge in candidates:
        edge["missing_preconditions"], edge["bindings"] = _missing(records, edge["record_refs"], pairs[tuple(edge["record_refs"])])
    issues = [issue for edge in candidates for issue in edge["source_issues"]]
    if not seeds:
        issues.append({"code": "no_discovery_focus", "detail": "No related anchor found; no multi-hop paths expanded."})
    paths = _paths(records, candidates, seeds)
    all_refs = connected | {ref for edge in candidates for ref in edge["record_refs"]}
    # Correction sources must be loaded alongside disputed capabilities.
    for issue in issues:
        all_refs.update(ref for ref in issue.get("record_refs", []) if ref in records)
    from combinations import build_combinations
    from capability_hints import build_type_reviews
    focus = all_refs if focused_request else set(records)
    combinations = build_combinations(records, candidates, focus)
    type_reviews = build_type_reviews(records, focus, candidates=candidates)
    all_refs.update(row["consumer_ref"] for row in combinations + type_reviews)
    # Type-review suggestions are unread lexical leads, not proven graph members.
    # Leave their record_refs on the review for deliberate read-by-ID follow-up.
    return {"candidates": candidates, "paths": paths,
            "combinations": combinations, "type_reviews": type_reviews,
            "record_refs": sorted(all_refs),
            "issues": [json.loads(item) for item in sorted({json.dumps(issue, ensure_ascii=False, sort_keys=True) for issue in issues})]}
