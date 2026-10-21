"""Compact AND/OR capability plans; every result remains unverified.

Each consumer's inputs are AND requirements. Providers of one input are OR
alternatives. A least fixed point identifies branches that can start without
bootstrapping a dependency cycle. One deterministic representative plan is then
selected; alternatives remain references, not a Cartesian product of plans.
"""

from collections import defaultdict
import heapq
import json

from conditions import known as _known


def _key(edge):
    return (edge["consumer_ref"], edge["need_index"],
            edge["producer_ref"], edge["provide_index"])


def _ref(edge):
    return {key: edge[key] for key in
            ("producer_ref", "provide_index", "consumer_ref", "need_index")}


def _eligible(edge):
    return (edge.get("compatibility") == "compatible"
            and edge.get("producer_usable") is True
            and edge.get("consumer_usable") is True)


def _needs(records, rid):
    return records[rid].get("capability", {}).get("needs", [])


def _grounded(records, edges, record_refs=None):
    """Find minimum startup ranks without recursion or a depth/output cap."""
    refs = set(records) if record_refs is None else set(record_refs)
    outgoing = defaultdict(list)
    blocked = set()
    for edge in edges:
        for role in ("producer", "consumer"):
            if edge.get(role + "_usable") is False:
                blocked.add(edge[role + "_ref"])
        if _eligible(edge):
            outgoing[edge["producer_ref"]].append(edge)
    remaining = {rid: len(_needs(records, rid)) for rid in refs}
    queue = [(0, rid) for rid in refs if not remaining[rid] and rid not in blocked]
    heapq.heapify(queue)
    ranks, ready_inputs, heights = {}, set(), defaultdict(int)
    while queue:
        rank, rid = heapq.heappop(queue)
        if rid in ranks:
            continue
        ranks[rid] = rank
        for edge in outgoing[rid]:
            consumer = edge["consumer_ref"]
            need = (consumer, edge["need_index"])
            if consumer not in refs or consumer in blocked or need in ready_inputs:
                continue
            ready_inputs.add(need)
            remaining[consumer] -= 1
            heights[consumer] = max(heights[consumer], rank + 1)
            if not remaining[consumer]:
                heapq.heappush(queue, (heights[consumer], consumer))
    return ranks


def _values(record_ref, role, index, constraints):
    return [{"constraint": key, "value": value, "record_ref": record_ref,
             "role": role, "index": index}
            for key, value in sorted(constraints.items())]


def _record_values(records, rid):
    values = _values(rid, "conditions", None, records[rid].get("conditions", {}))
    for index, need in enumerate(_needs(records, rid)):
        values.extend(_values(rid, "need", index, need.get("constraints", {})))
    return values


def _provide_values(records, edge):
    spec = records[edge["producer_ref"]]["capability"]["provides"][edge["provide_index"]]
    return _values(edge["producer_ref"], "provide", edge["provide_index"],
                   spec.get("constraints", {}))


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _joint_check(refs, values):
    """Compare authored same-name conditions across the selected records.

    This deliberately reports a review item when a named condition is absent
    from another selected branch. It neither proves joint exploitability nor
    declares that every possible OR selection has the same conflict.
    """
    by_name = defaultdict(list)
    for value in values:
        by_name[value["constraint"]].append(value)
    conflicts, unknown = [], []
    if not by_name:
        unknown.append({"code": "no_joint_conditions_declared", "record_refs": sorted(refs)})
    for name, entries in sorted(by_name.items()):
        entries = [json.loads(item) for item in sorted({_canonical(item) for item in entries})]
        known = [entry for entry in entries if _known(entry["value"])]
        if len({_canonical(entry["value"]) for entry in known}) > 1:
            conflicts.append({"code": "cross_branch_constraint_conflict", "constraint": name,
                              "values": known, "assessment": "requires_review"})
        absent = set(refs) - {entry["record_ref"] for entry in known}
        blank = [entry for entry in entries if not _known(entry["value"])]
        if absent or blank:
            unknown.append({"code": "cross_branch_constraint_unknown", "constraint": name,
                            "record_refs": sorted(absent), "values": entries})
    return conflicts, unknown


def _conflict_cost(existing, added):
    values = defaultdict(set)
    for entry in existing:
        if _known(entry["value"]):
            values[entry["constraint"]].add(_canonical(entry["value"]))
    return sum(bool(values[entry["constraint"]] - {_canonical(entry["value"])})
               for entry in added if _known(entry["value"]))


def _plan(records, by_need, all_edges, root, ranks):
    selected, expanded, active = {root}, set(), {root}
    values = _record_values(records, root)
    bindings, selected_edges, cycles = [], [], set()
    # Frames hold a record and its next input; no Python recursion is needed.
    stack = [(root, 0)]
    while stack:
        rid, index = stack[-1]
        if index == len(_needs(records, rid)):
            stack.pop()
            expanded.add(rid)
            active.remove(rid)
            continue
        stack[-1] = (rid, index + 1)
        options = [edge for edge in by_need.get((rid, index), ())
                   if edge.get("producer_usable") is True
                   and edge.get("consumer_usable") is True
                   and edge.get("compatibility") != "incompatible"]
        # A lower rank than every active ancestor is always safe. A longer
        # startup branch can still be preferable for its conditions, so do not
        # discard it merely for its rank: recheck startup with active ancestors
        # removed only when such a branch might point back into this traversal.
        earliest_active = min(ranks.get(ref, float("inf")) for ref in active)
        local_ranks = ranks
        if any(_eligible(edge) and edge["producer_ref"] in ranks
               and ranks[edge["producer_ref"]] >= earliest_active for edge in options):
            local_ranks = _grounded(records, all_edges, set(records) - active)

        def priority(edge):
            producer = edge["producer_ref"]
            added = _provide_values(records, edge)
            if producer not in selected:
                added += _record_values(records, producer)
            ready = _eligible(edge) and producer in local_ranks
            return (producer in active, not ready, not _eligible(edge),
                    _conflict_cost(values, added), local_ranks.get(producer, float("inf")), _key(edge))

        options.sort(key=priority)
        if not options:
            continue
        edge = options[0]
        producer = edge["producer_ref"]
        if producer in active:
            cycles.add((rid, index))
            continue
        selected_edges.append(edge)
        bindings.append({**_ref(edge), "compatibility": edge["compatibility"],
                         "assessment": "candidate", "evidence": False})
        values.extend(_provide_values(records, edge))
        if producer not in selected:
            selected.add(producer)
            values.extend(_record_values(records, producer))
        if producer not in expanded:
            active.add(producer)
            stack.append((producer, 0))

    selected_ranks = _grounded(records, selected_edges, selected)
    chosen = {(edge["consumer_ref"], edge["need_index"]): edge for edge in selected_edges}
    missing, covered, required = [], 0, 0
    referenced = set(selected)
    for rid in sorted(selected):
        for index, need in enumerate(_needs(records, rid)):
            required += 1
            options = by_need.get((rid, index), ())
            referenced.update(edge["producer_ref"] for edge in options)
            edge = chosen.get((rid, index))
            if edge and _eligible(edge) and edge["producer_ref"] in selected_ranks:
                covered += 1
                continue
            if (rid, index) in cycles:
                reason = "dependency_cycle"
            elif edge and _eligible(edge):
                reason = "upstream_preconditions_unresolved"
            elif edge:
                reason = "connection_unresolved"
            elif not options:
                reason = "no_candidate_provider"
            elif not any(option.get("producer_usable") and option.get("consumer_usable") for option in options):
                reason = "sources_unusable"
            else:
                reason = "connection_unresolved"
            gap = {"record_ref": rid, "need_index": index, "type": need["type"],
                   "constraints": need.get("constraints", {}), "reason": reason,
                   "candidate_provider_refs": sorted({option["producer_ref"] for option in options}),
                   "candidate_refs": [_ref(option) for option in options]}
            # Keep concrete diagnostics, while candidates themselves stay in the
            # discovery result and are referenced instead of being copied here.
            for field in ("conflicts", "unknown_conditions", "source_issues"):
                diagnostics = [{**_ref(option), **issue} for option in options
                               for issue in option.get(field, [])]
                if diagnostics:
                    gap[field] = diagnostics
            missing.append(gap)

    conflicts, unknown = _joint_check(selected, values)
    complete = covered == required and not conflicts and not unknown
    plan = {"record_refs": sorted(selected), "bindings": bindings,
            "coverage": {"required": required, "covered": covered, "complete": complete},
            "missing_preconditions": missing, "conflicts": conflicts,
            "unknown_conditions": unknown,
            "joint_conditions": {"assessment": "consistent" if not conflicts and not unknown else "unresolved",
                                 "check": "declared_conditions_only", "evidence": False},
            "selection": "representative; alternatives are not exhaustively combined"}
    return plan, referenced


def build_combinations(records, candidates, consumer_refs, *, minimum_inputs=2):
    """Build one AND group per relevant consumer with at least two inputs.

    Question-scoped checks may explicitly include single-input consumers.

    Input coverage is local: candidate_ready means a compatible, usable OR
    branch has all its recursive inputs. Only plan.coverage additionally checks
    the conditions of the branches actually selected together. Neither coverage
    value is evidence, and unresolved representative plans do not rule out other
    combinations of the preserved alternatives.
    """
    consumers = sorted(rid for rid in set(consumer_refs) if rid in records and len(_needs(records, rid)) >= minimum_inputs)
    if not consumers:
        return []
    candidates = sorted(candidates, key=_key)
    by_need = defaultdict(list)
    for edge in candidates:
        by_need[(edge["consumer_ref"], edge["need_index"])].append(edge)
    # A record outside the candidate endpoints cannot contribute a binding to
    # this graph. Include every endpoint and consumer, without loading unrelated
    # session records just to assign unused startup ranks.
    graph_refs = set(consumers) | {edge[role + "_ref"] for edge in candidates for role in ("producer", "consumer")}
    ranks = _grounded(records, candidates, graph_refs)
    result = []
    for consumer in consumers:
        needs = _needs(records, consumer)
        inputs = []
        for index, need in enumerate(needs):
            options = by_need.get((consumer, index), ())
            ready = any(_eligible(edge) and edge["producer_ref"] in ranks for edge in options)
            inputs.append({"need_index": index, "type": need["type"],
                           "alternatives": [_ref(edge) for edge in options],
                           "coverage": "candidate_ready" if ready else "unresolved"})
        plan, refs = _plan(records, by_need, candidates, consumer, ranks)
        result.append({"id": "combination:" + consumer, "consumer_ref": consumer,
                       "operator": "AND", "record_refs": sorted(refs), "inputs": inputs,
                       "plan": plan, "status": "candidate", "evidence": False,
                       "validation_required": "Verify each binding and simultaneous end-to-end conditions with original evidence; this representative candidate is not proof."})
    return result
