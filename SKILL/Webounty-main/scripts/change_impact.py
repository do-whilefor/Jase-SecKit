"""Explain the review impact of explicit session changes, without changing facts.

References identify affected judgments; they do not establish that a judgment is
false or that a new capability satisfies a need. Existing discovery candidates,
combinations, and representative paths are reused, never enumerated again here.
"""

from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy

from discovery import CORRECTIONS, discover


def _refs(values):
    if isinstance(values, (str, dict)):
        values = [values]
    return [value if isinstance(value, str) else value["id"] for value in values]


def combination_input_refs(combination):
    """Return each input's referenced providers and selected upstream sources.

    The consumer itself is excluded: a candidate notice reaching the consumer
    must not mark independent sibling inputs. This mapping also lets cursors
    detect changed branch sources without running capability discovery again.
    """
    consumer, plan = combination["consumer_ref"], combination.get("plan", {})
    upstream, selected_inputs, gap_providers = defaultdict(set), defaultdict(set), defaultdict(set)
    for edge in plan.get("bindings", []):
        upstream[edge["consumer_ref"]].add(edge["producer_ref"])
        selected_inputs[(edge["consumer_ref"], edge["need_index"])].add(edge["producer_ref"])
    for gap in plan.get("missing_preconditions", []):
        # Withdrawal can remove a selected upstream binding from the new
        # plan. Keep its reference through the selected branch's current gap.
        gap_providers[gap["record_ref"]].update(gap.get("candidate_provider_refs", []))

    result = {}
    for item in combination.get("inputs", []):
        refs = {edge["producer_ref"] for edge in item.get("alternatives", [])}
        pending = list(selected_inputs[(consumer, item["need_index"])])
        visited = set()
        while pending:
            ref = pending.pop()
            if ref in visited:
                continue
            visited.add(ref)
            refs.add(ref)
            refs.update(gap_providers[ref])
            pending.extend(upstream[ref] - visited)
        refs.discard(consumer)
        result[item["need_index"]] = refs
    return result


def _combination_reviews(combinations, origins, affected_record_refs):
    """Map propagated changes onto references in the supplied current plans.

    A candidate notice propagated to the consumer must not mark its independent
    sibling inputs. Trace each input's own alternatives and selected upstream
    branch instead. Coverage remains the discovery assessment, never new proof.
    """
    result = []
    for combination in combinations:
        touched = sorted({ref for ref in combination["record_refs"] if ("record", ref) in origins})
        if not touched:
            continue
        consumer, plan = combination["consumer_ref"], combination.get("plan", {})
        input_refs = combination_input_refs(combination)
        affected_inputs = []
        for item in combination.get("inputs", []):
            refs = input_refs[item["need_index"]]
            if consumer in affected_record_refs:
                # Authored consumer/source edits can alter all of its needs;
                # candidate-only propagation is deliberately excluded here.
                refs.add(consumer)
            via = sorted(ref for ref in refs if ("record", ref) in origins)
            if via:
                roots = set().union(*(origins[("record", ref)] for ref in via))
                affected_inputs.append({key: deepcopy(item[key]) for key in ("need_index", "type", "coverage")})
                affected_inputs[-1].update(source_refs=sorted(roots), via_refs=via)

        roots = set().union(*(origins[("record", ref)] for ref in touched))
        result.append({"id": combination["id"], "consumer_ref": consumer,
                       "source_refs": sorted(roots), "via_refs": touched,
                       "affected_inputs": affected_inputs,
                       "coverage": deepcopy(plan.get("coverage", {})),
                       "missing_preconditions": [
                           {key: deepcopy(gap[key]) for key in ("record_ref", "need_index", "type", "reason")
                            if key in gap}
                           for gap in plan.get("missing_preconditions", [])],
                       "conflicts": deepcopy(plan.get("conflicts", [])),
                       "unknown_conditions": deepcopy(plan.get("unknown_conditions", [])),
                       "reason": "combination_member_requires_review", "assessment": "candidate", "evidence": False})
    return result


def build_impact(corpus, changed, discovery=None):
    """Return read-only review pointers for known changed IDs or ``{id: ...}`` rows.

    Callers exclude navigation-only changes. An empty/unknown change set does
    not run discovery. Supplying even an empty discovery result suppresses a
    second discovery call; source checks remain the caller's evidence workflow.
    """
    groups = {"record": corpus.records, "observation": corpus.observations,
              "entity": corpus.entities, "artifact": corpus.artifacts,
              "page": corpus.pages, "block": corpus.blocks}
    nodes = {ref: (kind, ref) for kind, rows in reversed(list(groups.items())) for ref in rows}
    changed_refs = sorted(set(_refs(changed)).intersection(nodes))
    out = {"changed_refs": changed_refs, "affected_records": [], "affected_pages": [],
           "affected_chains": [], "affected_paths": [], "affected_combinations": [], "connections_to_review": [],
           "evidence": False}
    if not changed_refs:
        return out

    if getattr(corpus, "metadata", None) is not None:
        from metadata_cache import ImpactEdges
        edges = ImpactEdges(corpus, nodes)
    else:
        edges = defaultdict(set)

        def link(source, target, reason):
            if source in nodes and target in nodes:
                edges[nodes[source]].add((nodes[target], reason))

        scoped_pages = defaultdict(set)
        for pid, page in corpus.pages.items():
            for subject in page.get("discovery_scope", {}).get("subject_refs", []):
                scoped_pages[subject].add(pid)
            for field in ("source_refs", "record_refs", "subject_refs"):
                for ref in _refs(page.get(field, [])):
                    link(ref, pid, "page_source_changed")
        for rid, row in corpus.records.items():
            contradictions = set(_refs(row.get("contradicts", [])))
            corrections = {ref for field in CORRECTIONS for ref in _refs(row.get(field, []))}
            # A replacement affects the old judgment, not the other way around.
            for ref in corpus.record_dependencies[rid] - contradictions:
                link(ref, rid, "counterevidence_changed" if ref in corrections else "dependency_changed")
            for ref in contradictions:
                link(rid, ref, "counterevidence_changed")
            for ref in _refs(row.get("observation_refs", [])):
                link(ref, rid, "observation_changed")
            for ref in row.get("artifact_refs", []):
                link(ref["artifact_id"], rid, "artifact_changed")
            for connection in row.get("links", []):
                for ref in _refs(connection.get("evidence_refs", [])):
                    link(ref, rid, "connection_evidence_changed")
            for subject in _refs(row.get("subject_refs", [])):
                link(subject, rid, "subject_changed")
                for pid in scoped_pages[subject]:
                    link(rid, pid, "scoped_record_changed")
        for oid, row in corpus.observations.items():
            for field in ("artifact_id", "source_artifact_id"):
                if row.get(field):
                    link(row[field], oid, "artifact_changed")
            for subject in _refs(row.get("subject_refs", [])):
                link(subject, oid, "subject_changed")
                for pid in scoped_pages[subject]:
                    link(oid, pid, "scoped_observation_changed")
        for eid, row in corpus.entities.items():
            for field in ("owner_ref", "tenant_ref", "asset_ref"):
                if row.get(field):
                    link(row[field], eid, "entity_context_changed")
            for field in ("source_refs", "observation_refs"):
                for ref in _refs(row.get(field, [])):
                    link(ref, eid, "entity_source_changed")
        for bid, block in corpus.blocks.items():
            for field in ("source_refs", "subject_refs"):
                for ref in _refs(block.get(field, [])):
                    link(ref, bid, "block_source_changed")
            for ref in block.get("artifact_refs", []):
                link(ref["artifact_id"], bid, "artifact_changed")
            for ref in block.get("required_block_refs", []):
                link(ref["page_id"] + "/" + ref["block_id"], bid, "required_block_changed")
            link(bid, block["page_id"], "block_changed")

    origins, reasons = defaultdict(set), defaultdict(lambda: defaultdict(set))
    pending = deque()

    def mark(node, source_refs, reason, via_refs):
        reasons[node][reason].update(via_refs)
        added = set(source_refs) - origins[node]
        if added:
            origins[node].update(added)
            pending.append((node, added))

    def propagate():
        while pending:
            source, roots = pending.popleft()
            for target, reason in sorted(edges[source]):
                mark(target, roots, reason, [source[1]])

    for ref in changed_refs:
        node = nodes[ref]
        mark(node, [ref], node[0] + "_changed", [ref])
        if node[0] == "page":
            # Explicit page edits may change any block. Merely being affected
            # through one block must not fan out to unrelated sibling blocks.
            for block in corpus.pages[ref].get("blocks", []):
                bid = ref + "/" + block["block_id"]
                mark(nodes[bid], [ref], "page_changed", [ref])
    propagate()

    affected_record_refs = {ref for kind, ref in origins if kind == "record"}
    if discovery is None:
        # Include derived affected records when the input was an artifact or
        # entity; discover's changed-ID resolver need not repeat this traversal.
        discovery = discover(corpus, changed=sorted(set(changed_refs) | affected_record_refs))
    seen_connections = set()
    for edge in discovery.get("candidates", []):
        key = (edge["producer_ref"], edge["provide_index"], edge["consumer_ref"], edge["need_index"])
        endpoints = {key[0], key[2]}.intersection(affected_record_refs)
        if not endpoints or key in seen_connections:
            continue
        seen_connections.add(key)
        source_refs = set().union(*(origins[("record", ref)] for ref in endpoints))
        row = {field: deepcopy(edge[field]) for field in (
            "producer_ref", "provide_index", "consumer_ref", "need_index", "compatibility",
            "conflicts", "unknown_conditions", "source_issues", "producer_usable", "consumer_usable",
        ) if field in edge}
        row.update(source_refs=sorted(source_refs), reason="candidate_endpoint_changed",
                   assessment="candidate", evidence=False)
        out["connections_to_review"].append(row)
        # A newly learned producer can be relevant to a previously blocked or
        # negative consumer that never cited it. This is only a review pointer,
        # including when declared constraints conflict or evidence is unusable.
        consumer = edge["consumer_ref"]
        if edge["producer_ref"] in endpoints and consumer in corpus.records:
            mark(("record", consumer), source_refs, "input_candidate_changed", [edge["producer_ref"]])
    propagate()

    def explanation(node):
        return {"source_refs": sorted(origins[node]), "reasons": [
            {"code": code, "via_refs": sorted(via)} for code, via in sorted(reasons[node].items())],
            "evidence": False}

    for node in sorted(origins):
        kind, ref = node
        if kind == "record":
            row = {"id": ref, **explanation(node)}
            if corpus.records[ref].get("kind") == "Chain":
                out["affected_chains"].append(row)
            else:
                out["affected_records"].append(row)
        elif kind == "page":
            blocks = sorted(bid for bkind, bid in origins if bkind == "block"
                            and corpus.blocks[bid]["page_id"] == ref)
            out["affected_pages"].append({"page_id": ref, "block_refs": blocks, **explanation(node)})
    for path in discovery.get("paths", []):
        touched = [ref for ref in path["record_refs"] if ("record", ref) in origins]
        if touched:
            roots = set().union(*(origins[("record", ref)] for ref in touched))
            out["affected_paths"].append({"record_refs": list(path["record_refs"]),
                "source_refs": sorted(roots), "via_refs": touched,
                "reason": "path_member_requires_review", "assessment": "candidate", "evidence": False})
    out["affected_combinations"] = _combination_reviews(
        discovery.get("combinations", []), origins, affected_record_refs)
    return out
