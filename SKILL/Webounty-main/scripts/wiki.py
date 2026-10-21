#!/usr/bin/env python3
"""Audit Wiki content and create an optimized, separate derived corpus."""

from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path
import re
import shutil

from rag import Corpus, RetrievalError, digest, encode, ref_ids


HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
ANCHOR = re.compile(r'<a id="[^"]+"></a>')
LINK = re.compile(r"!?\[[^\]\n]*\]\([^\)\n]+\)")
REVIEW_ISSUES = {"new_candidates", "removed_candidates", "stale_source", "condition_change",
                 "reasoning_review_required"}
NAVIGATION_TITLES = {
    "navigation", "related pages", "related links", "contents", "index",
    "\u76f8\u5173\u9875\u9762", "\u76f8\u5173\u89e3\u91ca", "\u4ece\u95ee\u9898\u8fdb\u5165",
    "\u5bfc\u822a", "\u76ee\u5f55", "\u76f8\u5173\u94fe\u63a5",
}


def block_title(block):
    heading = HEADING.search(block["text"])
    return heading.group(1).strip() if heading else block.get("title", "")


def is_navigation(block):
    if block.get("role") == "history" or block_title(block).casefold() not in NAVIGATION_TITLES:
        return False
    body = HEADING.sub("", ANCHOR.sub("", block["text"]))
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines or not LINK.search(body):
        return False
    for index, line in enumerate(lines):
        if line.startswith("|") and line.endswith("|"):
            if LINK.search(line) or re.fullmatch(r"[|:\-\s]+", line):
                continue
            if index + 1 < len(lines) and re.fullmatch(r"[|:\-\s]+", lines[index + 1]):
                continue
        remainder = LINK.sub("", line)
        if re.sub(r"[\s*\-+\d.()\[\]:;,|\u00b7\u3002\uff0c\uff1b]+", "", remainder):
            return False
    return True


def derived_subjects(corpus, block):
    if not hasattr(corpus, "_wiki_entity_pattern"):
        alternatives = "|".join(re.escape(eid) for eid in sorted(corpus.entities, key=len, reverse=True))
        corpus._wiki_entity_pattern = re.compile(
            r"(?<![A-Za-z0-9_-])(?:" + (alternatives or r"(?!)") + r")(?![A-Za-z0-9_-])")
    subjects = set(corpus._wiki_entity_pattern.findall(block["text"]))
    for source_id in ref_ids(block.get("source_refs", [])):
        source = (corpus.records.get(source_id) or corpus.observations.get(source_id)
                  or corpus.entities.get(source_id))
        if source is not None:
            subjects.update(set(source.get("subject_refs", [])) & corpus.entities.keys())
        if source_id in corpus.entities:
            subjects.add(source_id)
    return sorted(subjects)


def optimized_manifest(corpus):
    manifest = copy.deepcopy(corpus.manifest)
    changes = Counter()
    for page in manifest["pages"]:
        for block in page["blocks"]:
            loaded = corpus.blocks[f'{page["page_id"]}/{block["block_id"]}']
            title = block_title(loaded)
            if title and not block.get("title"):
                block["title"] = title
                changes["titles_added"] += 1
            if "subject_refs" not in block:
                block["subject_refs"] = derived_subjects(corpus, loaded)
                changes["block_scopes_added"] += 1
            if is_navigation(loaded) and block.get("role") != "navigation":
                block["role"] = "navigation"
                changes["navigation_roles_set"] += 1
            if "conditions" in block and block["conditions"] == page.get("conditions"):
                del block["conditions"]
                changes["inherited_conditions_removed"] += 1
    return manifest, dict(changes)


# Optional human-authored block metadata. Source fields remain authoritative;
# these facets organize questions and evidence without deciding vulnerability status.
KNOWLEDGE_PATH = "wiki-knowledge.json"
KNOWLEDGE_FACETS = ("boundary", "controls", "counterevidence_refs", "limitations", "reopen_when")
KNOWLEDGE_REF_FIELDS = {
    "supporting_refs": {"record", "observation"},
    "counterevidence_refs": {"record", "observation"},
    "record_refs": {"record"}, "observation_refs": {"observation"},
    "actor_refs": {"entity"}, "entrypoint_refs": {"entity"}, "object_refs": {"entity"},
    "producer_refs": {"record"}, "consumer_refs": {"record"},
    "basis_refs": {"record", "observation"},
}
CONTEXT_FIELDS = {"environment": str, "target_version": str, "credential_generation": str}
REASONING_FACETS = ("experiments", "capability_links", "lifecycle")
RELATION_FIELDS = (
    "requires", "evidence_refs", "contradicted_by", "step_refs", "supporting_fact_ids",
    "contradicting_fact_ids", "corrected_by", "correction_refs", "superseded_by",
    "source_refs", "contradicts",
)


def _knowledge_shape_issues(annotation, block_ref):
    issues = []

    def invalid(field):
        issues.append({"code": "knowledge_invalid", "block_ref": block_ref, "field": field})

    def check_fields(value, types, field, required=()):
        if not isinstance(value, dict):
            invalid(field)
            return
        for key, item in value.items():
            expected = types.get(key)
            if expected is None or not isinstance(item, expected):
                invalid(f"{field}.{key}")
            elif expected is list and key not in {"controls", "experiments", "capability_links",
                                                 "control_indexes"} and any(not isinstance(x, str) for x in item):
                invalid(f"{field}.{key}")
        for key in required:
            if key not in value:
                invalid(f"{field}.{key}")

    def enum(value, key, choices, field):
        if key in value and (not isinstance(value[key], str) or value[key] not in choices):
            invalid(f"{field}.{key}")

    def context(value, field):
        if "context" in value:
            check_fields(value["context"], CONTEXT_FIELDS, f"{field}.context")

    check_fields(annotation, {
        "boundary": dict, "controls": list, "supporting_refs": list,
        "counterevidence_refs": list, "limitations": list, "reopen_when": list,
        "next_discriminator": str,
        "experiments": list, "capability_links": list, "lifecycle": dict,
    }, "knowledge")
    if not isinstance(annotation, dict):
        return issues
    if "boundary" in annotation:
        check_fields(annotation["boundary"], {
            "actor_refs": list, "entrypoint_refs": list, "object_refs": list,
            "relationship": str, "action": str, "state": str,
            "trusted_fields": list, "expectation": str,
        }, "knowledge.boundary")
    if isinstance(annotation.get("controls"), list):
        for index, control in enumerate(annotation["controls"]):
            field = f"knowledge.controls[{index}]"
            check_fields(control, {"kind": str, "observation_refs": list,
                                   "record_refs": list, "note": str, "validity": str,
                                   "context": dict}, field, ("kind",))
            if not isinstance(control, dict):
                continue
            enum(control, "kind", {"owner_baseline", "negative_control", "contrast"}, field)
            enum(control, "validity", {"valid", "invalid", "unknown"}, field)
            context(control, field)
            if not (control.get("observation_refs") or control.get("record_refs")):
                invalid(field)
    for index, experiment in enumerate(annotation.get("experiments", []) if isinstance(
            annotation.get("experiments", []), list) else []):
        field = f"knowledge.experiments[{index}]"
        check_fields(experiment, {
            "id": str, "claim_kind": str, "changed_variable": str,
            "expected": str, "falsifier": str, "observation_refs": list,
            "control_indexes": list, "observer": str, "assessment": str,
            "context": dict, "confounders": list,
        }, field, ("id", "claim_kind", "changed_variable", "expected", "falsifier",
                   "observation_refs", "control_indexes", "observer", "assessment", "context"))
        if not isinstance(experiment, dict):
            continue
        enum(experiment, "claim_kind", {"enumeration", "authorization", "reachability",
                                      "capability", "impact", "retest"}, field)
        enum(experiment, "observer", {"valid", "invalid", "unknown"}, field)
        enum(experiment, "assessment", {"supports", "refutes", "inconclusive"}, field)
        if isinstance(experiment.get("control_indexes"), list) and any(
                type(x) is not int or x < 0 for x in experiment["control_indexes"]):
            invalid(f"{field}.control_indexes")
        context(experiment, field)
    for index, link in enumerate(annotation.get("capability_links", []) if isinstance(
            annotation.get("capability_links", []), list) else []):
        field = f"knowledge.capability_links[{index}]"
        check_fields(link, {
            "producer_refs": list, "consumer_refs": list, "from_stage": str,
            "to_stage": str, "output": str, "required_input": str,
            "compatibility": str, "observation_refs": list, "unresolved_preconditions": list,
        }, field, ("producer_refs", "consumer_refs", "from_stage", "to_stage", "output",
                   "required_input", "compatibility", "observation_refs", "unresolved_preconditions"))
        if not isinstance(link, dict):
            continue
        for key in ("from_stage", "to_stage"):
            enum(link, key, {"reachability", "capability", "impact"}, field)
        enum(link, "compatibility", {"matched", "mismatched", "unknown"}, field)
    if "lifecycle" in annotation:
        lifecycle = annotation["lifecycle"]
        field = "knowledge.lifecycle"
        check_fields(lifecycle, {"state": str, "basis_refs": list, "experiment_ids": list,
                                "context": dict, "changed_variables": list}, field,
                     ("state", "basis_refs", "experiment_ids", "context"))
        if isinstance(lifecycle, dict):
            enum(lifecycle, "state", {"open", "closed_for_conditions", "retest_pending",
                                     "retested_for_conditions", "unknown"}, field)
            context(lifecycle, field)
    return issues


def _knowledge_issues(value, corpus, reachable, block_ref, field="knowledge"):
    """Validate authored references, without treating text or declared status as proof."""
    issues = []
    if not isinstance(value, dict):
        return [{"code": "knowledge_invalid", "block_ref": block_ref, "field": field}]
    for key, item in value.items():
        location = f"{field}.{key}"
        if key in KNOWLEDGE_REF_FIELDS:
            if not isinstance(item, list) or any(not isinstance(ref, str) for ref in item):
                issues.append({"code": "knowledge_invalid", "block_ref": block_ref, "field": location})
                continue
            for ref in item:
                kind = ("record" if ref in corpus.records else "observation" if ref in corpus.observations
                        else "entity" if ref in corpus.entities else None)
                if kind not in KNOWLEDGE_REF_FIELDS[key]:
                    issues.append({"code": "knowledge_reference_missing", "block_ref": block_ref,
                                   "field": location, "id": ref})
                elif key in {"actor_refs", "entrypoint_refs", "object_refs"} and (
                        corpus.entities[ref].get("kind") != {
                            "actor_refs": "actor", "entrypoint_refs": "endpoint", "object_refs": "object"}[key]):
                    issues.append({"code": "knowledge_reference_kind", "block_ref": block_ref,
                                   "field": location, "id": ref})
                elif ref not in reachable:
                    issues.append({"code": "knowledge_reference_unlinked", "block_ref": block_ref,
                                   "field": location, "id": ref})
        elif isinstance(item, dict):
            issues.extend(_knowledge_issues(item, corpus, reachable, block_ref, location))
        elif isinstance(item, list):
            for index, entry in enumerate(item):
                if isinstance(entry, dict):
                    issues.extend(_knowledge_issues(entry, corpus, reachable, block_ref,
                                                    f"{location}[{index}]"))
    return issues


def validate_block_knowledge(corpus, block_ref, package):
    """Check annotations against an already resolved package, without recursive packaging.

    Pass the block's own source package when excluding evidence from unrelated blocks
    is required. Existence and source reachability do not prove an annotation's prose.
    """
    block = corpus.blocks.get(block_ref)
    if block is None:
        return [{"code": "missing_reference", "block_ref": block_ref}]
    if "knowledge" not in block:
        return []
    reachable = set()
    if package is not None:
        for group in ("records", "entities", "observations"):
            reachable.update(row["id"] for row in package.get(group, []))
    annotation = block["knowledge"]
    issues = (_knowledge_shape_issues(annotation, block_ref)
              + _knowledge_issues(annotation, corpus, reachable, block_ref))
    if not issues:
        reasoning = block_reasoning(corpus, block_ref, package)
        if hasattr(corpus, "reasoning_cache") and any(key in annotation for key in REASONING_FACETS):
            corpus.reasoning_cache[block_ref] = reasoning
        issues.extend(reasoning["review_gaps"])
    return issues


class _ProvenanceRoots:
    """Resolve explicit provenance inside one immutable Corpus snapshot.

    Each uncached seed walks its reachable graph once, with a single visited set.
    Only complete walks are cached: memoizing a partial DFS result in a cycle can
    silently lose an origin reachable through an ancestor. Origin sets also prevent
    a shared DAG from expanding into one duplicate origin per path.
    """

    def __init__(self, corpus):
        self.corpus = corpus
        self.nodes, self.completed, self.locations, self.origins = {}, {}, {}, {}
        self.line_hashes = {}
        for observation in corpus.observations.values():
            self.line_hashes.setdefault((observation.get("artifact_id"), observation.get("line")),
                                        observation.get("content_hash"))

    def origin(self, aid, line=None, content_hash=None):
        key = aid, line, content_hash
        if key in self.origins:
            return self.origins[key]
        meta = self.corpus.artifacts.get(aid, {})
        result = None
        if meta.get("sha256"):
            if line is not None and content_hash is None:
                content_hash = self.line_hashes.get((aid, line))
            identity = {"artifact_sha256": meta["sha256"], "line": line,
                        "content_hash": content_hash}
            location = {**identity, "artifact_id": aid, "path": meta.get("path")}
            result = digest(encode(identity).encode()), encode(location)
            self.locations[result] = location
        self.origins[key] = result
        return result

    def node(self, ref):
        if ref in self.nodes:
            return self.nodes[ref]
        children, observation_ids, origins = set(), set(), set()
        if ref in self.corpus.observations:
            row = self.corpus.observations[ref]
            observation_ids.add(ref)
            value = self.origin(row.get("artifact_id"), row.get("line"), row.get("content_hash"))
            if value is not None:
                origins.add(value)
        else:
            row = self.corpus.records.get(ref, {})
            children.update(row.get("observation_refs", []))
            for field in ("source_refs", "evidence_refs", "supporting_fact_ids", "contradicting_fact_ids"):
                children.update(ref_ids(row.get(field, [])))
            for item in row.get("artifact_refs", []):
                value = self.origin(item.get("artifact_id"), item.get("line"))
                if value is not None:
                    origins.add(value)
        result = frozenset(children), frozenset(observation_ids), frozenset(origins)
        self.nodes[ref] = result
        return result

    def roots(self, ref):
        if ref in self.completed:
            return self.completed[ref]
        pending, visited, observation_ids, origins = [ref], set(), set(), set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            children, direct_observations, direct_origins = self.node(current)
            pending.extend(children - visited)
            observation_ids.update(direct_observations)
            origins.update(direct_origins)
        result = frozenset(observation_ids), frozenset(origins)
        self.completed[ref] = result
        return result


def _provenance_roots(corpus):
    if not hasattr(corpus, "_wiki_provenance_roots"):
        corpus._wiki_provenance_roots = _ProvenanceRoots(corpus)
    return corpus._wiki_provenance_roots


def _source_families(corpus, refs):
    """Group explicit copies of an original; distinct JSONL lines stay distinct.

    No independence count is produced. Separate captures can still share an upstream
    cause, and hashes establish byte identity, not truth or independent experiments.
    """
    groups, unresolved = {}, set()
    resolver = _provenance_roots(corpus)
    for ref in sorted(refs):
        _, origins = resolver.roots(ref)
        if not origins:
            unresolved.add(ref)
        for identity, location_key in origins:
            group = groups.setdefault(identity, {"id": identity, "source_refs": set(), "origins": {}})
            group["source_refs"].add(ref)
            group["origins"][location_key] = dict(resolver.locations[identity, location_key])
    return {"groups": [{"id": key, "source_refs": sorted(group["source_refs"]),
                        "origins": [group["origins"][x] for x in sorted(group["origins"])]}
                       for key, group in sorted(groups.items())],
            "unresolved_refs": sorted(unresolved), "independence": "unknown",
            "meaning": "explicit provenance groups; neither group count nor copies prove independent corroboration"}


def block_reasoning(corpus, block_ref, package):
    """Mechanical consistency checks over authored reasoning, never claim verification.

    Call only after shape/reference validation, with this block's own source package.
    Missing premises retain the prose and evidence but force a review signal.
    """
    annotation = corpus.blocks[block_ref].get("knowledge", {})
    controls = annotation.get("controls", [])
    experiments = annotation.get("experiments", [])
    gaps, effective, refs = [], {}, set()

    def gap(field, reason, code="reasoning_review_required"):
        gaps.append({"code": code, "block_ref": block_ref, "field": field, "reason": reason})

    def known(value):
        return isinstance(value, str) and value.strip().casefold() not in {"", "unknown", "unspecified"}

    def complete(context):
        return all(known(context.get(key)) for key in CONTEXT_FIELDS)

    def collect(value):
        if not isinstance(value, dict):
            return
        for key, item in value.items():
            if key in KNOWLEDGE_REF_FIELDS and key not in {"actor_refs", "entrypoint_refs", "object_refs"}:
                refs.update(item)
            elif isinstance(item, dict):
                collect(item)
            elif isinstance(item, list):
                for child in item:
                    collect(child)

    collect(annotation)
    observations = {row["id"]: row.get("raw") or {} for row in (package or {}).get("observations", [])}
    actors = {row["id"] for row in (package or {}).get("entities", []) if row.get("kind") == "actor"}

    resolver = _provenance_roots(corpus)
    observation_sets, family_sets = {}, {}

    def observation_roots(source_refs):
        key = frozenset(source_refs)
        if key not in observation_sets:
            found = set()
            for ref in key:
                found.update(resolver.roots(ref)[0])
            observation_sets[key] = found & observations.keys()
        return observation_sets[key]

    def source_families(source_refs):
        key = frozenset(source_refs)
        if key not in family_sets:
            family_sets[key] = _source_families(corpus, key)
        return family_sets[key]

    def check_observed_context(oids, context, field):
        if not oids:
            gap(field, "control or experiment lacks an original observation")
        for oid in sorted(oids):
            raw = observations.get(oid, {})
            if raw.get("transport_status", "complete") != "complete":
                gap(field, f"observation {oid} did not complete transport")
            for dimension, source_key in (("environment", "environment"), ("target_version", "target_version"),
                                          ("credential_generation", "session_generation")):
                if source_key not in raw:
                    gap(f"{field}.{dimension}", f"observation {oid} does not establish this context dimension")
                elif str(raw[source_key]) != context.get(dimension):
                    gap(f"{field}.{dimension}", f"context differs from observation {oid}")

    def trigger(oid):
        raw = observations.get(oid, {})
        request = raw.get("request")
        actor = raw.get("actor_ref")
        if (not isinstance(request, dict) or not known(request.get("method")) or not known(request.get("url"))
                or not known(actor) or corpus.entities.get(actor, {}).get("kind") != "actor"
                or actor not in actors):
            return None
        # Credential references, headers, and any other recorded request dimensions
        # can affect the observed path. A partial projection silently loses them.
        return {"request": request, "actor_ref": actor}

    def protocol(oid):
        raw = observations.get(oid, {})
        request = raw.get("request") or {}
        endpoints = {ref for ref in raw.get("subject_refs", [])
                     if corpus.entities.get(ref, {}).get("kind") == "endpoint"}
        return request.get("method") if isinstance(request, dict) else None, endpoints

    seen = set()
    for index, experiment in enumerate(experiments):
        field = f"knowledge.experiments[{index}]"
        eid = experiment["id"]
        before = len(gaps)
        if not known(eid) or eid in seen:
            gap(f"{field}.id", "experiment IDs must be nonempty and unique within the block", "knowledge_invalid")
        seen.add(eid)
        if not all(known(experiment[key]) for key in ("changed_variable", "expected", "falsifier")):
            gap(field, "observable discriminators are not specified")
        if experiment["observer"] != "valid" or not experiment["observation_refs"]:
            gap(field, "observer or original observation is unavailable")
        if experiment["assessment"] == "inconclusive":
            gap(field, "experiment remains inconclusive")
        if not complete(experiment["context"]):
            gap(f"{field}.context", "environment, target version, and credential generation must remain explicit")
        check_observed_context(experiment["observation_refs"], experiment["context"], f"{field}.context")
        selected_controls = []
        for control_index in experiment["control_indexes"]:
            if control_index >= len(controls):
                gap(f"{field}.control_indexes", "control index does not resolve within the block", "knowledge_invalid")
                continue
            control = controls[control_index]
            selected_controls.append(control)
            if control.get("validity", "unknown") != "valid":
                gap(f"{field}.control_indexes", "selected control validity is not established")
            if control.get("context") != experiment["context"]:
                gap(f"{field}.control_indexes", "control and experiment conditions differ or are unspecified")
            control_refs = set(control.get("observation_refs", [])) | set(control.get("record_refs", []))
            control_oids = observation_roots(control_refs)
            check_observed_context(control_oids, control.get("context", {}),
                                   f"{field}.control_indexes")
            if not all(any(protocol(test_oid)[0] is not None
                           and protocol(test_oid)[0] == protocol(control_oid)[0]
                           and protocol(test_oid)[1] & protocol(control_oid)[1]
                           for control_oid in control_oids) for test_oid in experiment["observation_refs"]):
                gap(f"{field}.control_indexes", "control does not cover the observed method and endpoint")
            control_sources = source_families(control_refs)
            test_sources = source_families(experiment["observation_refs"])
            if {row["id"] for row in control_sources["groups"]} & {
                    row["id"] for row in test_sources["groups"]}:
                gap(f"{field}.control_indexes", "test observation reused as its own control")
        if not any(control["kind"] == "owner_baseline" for control in selected_controls):
            gap(f"{field}.control_indexes", "a normal successful baseline is required")
        if experiment["claim_kind"] == "enumeration" and not any(
                control["kind"] == "negative_control" for control in selected_controls):
            gap(f"{field}.control_indexes", "enumeration needs a valid negative control under the same protocol")
        if experiment.get("confounders"):
            gap(field, "unresolved confounders remain")
        effective[eid] = experiment["assessment"] if len(gaps) == before else "inconclusive"

    link_states = []
    for index, link in enumerate(annotation.get("capability_links", [])):
        field = f"knowledge.capability_links[{index}]"
        state = "recorded"
        if link["compatibility"] != "matched" or link["unresolved_preconditions"]:
            state = "blocked" if link["compatibility"] == "mismatched" else "unknown"
            gap(field, "output-input compatibility or remaining preconditions need review")
        if not (link["producer_refs"] and link["consumer_refs"] and link["observation_refs"]
                and known(link["output"]) and known(link["required_input"])):
            state = "unknown"
            gap(field, "a reachable route or named token alone does not establish a usable capability or impact")
        link_observations = set(link["observation_refs"])
        if link["compatibility"] == "matched" and not all(
                link_observations & observation_roots(link[side]) for side in ("producer_refs", "consumer_refs")):
            state = "unknown"
            gap(field, "matched output-input connection lacks original observations for both producer and consumer")
        link_states.append({"index": index, "status": state, "claims_verified": False})

    lifecycle = annotation.get("lifecycle")
    lifecycle_view = None
    if lifecycle is not None:
        field = "knowledge.lifecycle"
        before = len(gaps)
        state = lifecycle["state"]
        linked = []
        for eid in lifecycle["experiment_ids"]:
            if eid not in effective:
                gap(f"{field}.experiment_ids", "experiment ID does not resolve within the block", "knowledge_invalid")
            else:
                linked.extend(experiment for experiment in experiments if experiment["id"] == eid)
        if state in {"unknown", "retest_pending"}:
            gap(field, "lifecycle remains unknown or awaits retest")
        if state in {"closed_for_conditions", "retested_for_conditions"}:
            if not (complete(lifecycle["context"]) and lifecycle["basis_refs"] and annotation.get("reopen_when")):
                gap(field, "conditional closure needs source basis, explicit conditions, and reopen_when")
            current = [experiment for experiment in linked if experiment["context"] == lifecycle["context"]
                       and effective[experiment["id"]] == "refutes"]
            if not current:
                gap(field, "no valid refuting experiment under the declared current conditions")
            if state == "retested_for_conditions":
                originals = [experiment for experiment in linked if effective[experiment["id"]] == "supports"]
                if not originals or not current:
                    gap(field, "retest needs both original reproduction and current negative result with normal baselines")
                version_pairs = [(original, now) for original in originals for now in current
                                 if original["context"]["target_version"] != now["context"]["target_version"]]
                if originals and current and not version_pairs:
                    gap(field, "no changed target version between original reproduction and retest")
                matched_pairs = [(original, now) for original, now in version_pairs if any(
                    trigger(old_oid) is not None and trigger(old_oid) == trigger(new_oid)
                    for old_oid in original["observation_refs"] for new_oid in now["observation_refs"])]
                if originals and current and not matched_pairs:
                    gap(field, "one version-changing original/retest pair must preserve an observed trigger and valid actor")
                declared = set(lifecycle.get("changed_variables", []))
                if matched_pairs and not any(
                        {key for key in CONTEXT_FIELDS if original["context"].get(key) != now["context"].get(key)}
                        <= declared for original, now in matched_pairs):
                    gap(field, "retest must declare all changed context dimensions, including credential changes")
        lifecycle_view = {"declared_state": state,
                          "effective_state": state if len(gaps) == before else "unknown",
                          "claims_verified": False}
    return {"status": "review_required" if gaps else "structured", "evidence": False,
            "claims_verified": False, "experiments": [
                {"id": experiment["id"], "effective_assessment": effective[experiment["id"]]}
                for experiment in experiments], "capability_links": link_states,
            "lifecycle": lifecycle_view, "source_families": source_families(refs),
            "review_gaps": gaps,
            "meaning": "mechanical consistency of authored metadata; source semantics and findings still require review"}


def _knowledge(corpus, block_refs=()):
    """Build normalized navigation from live source closure, never from a prior sidecar."""
    selected, issues = corpus.block_closure(block_refs or corpus.blocks)
    # The view returns artifact provenance, not original content. Verify bytes
    # without materializing large originals or requiring binary files to be text.
    package, more = corpus.package(block_keys=selected, _expand_artifacts=False)
    issues.extend(more)
    manifest, _ = optimized_manifest(corpus)
    optimized = {f'{page["page_id"]}/{block["block_id"]}': block
                 for page in manifest["pages"] for block in page["blocks"]}
    document = {
        "schema_version": 1, "kind": "derived_wiki_knowledge", "evidence": False,
        "fixture": corpus.state.get("fixture", False), "run_id": corpus.run_id,
        "basis": {"state_revision": corpus.state["revision"],
                  "state_sha256": digest(corpus.read_bytes("state.json")),
                  "manifest_path": corpus.manifest_path,
                  "manifest_sha256": digest(corpus.read_bytes(corpus.manifest_path))},
        "status": "unavailable", "issues": [], "metadata_gaps": [],
        "blocks": {}, "conditions": {}, "sources": {}, "observations": {},
        "artifacts": {}, "page_checks": [],
    }
    if package is not None:
        checks = {check["page_id"]: check for check in package["page_checks"]}
        document["page_checks"] = [checks[key] for key in sorted(checks)]
        for row in package["records"]:
            document["sources"][row["id"]] = {
                "kind": "record", "revision": row["revision"], "record_kind": row.get("kind"),
                "location": {"path": "state.json", "collection": "records", "id": row["id"]},
                "relations": {key: copy.deepcopy(row[key]) for key in RELATION_FIELDS if row.get(key)},
                "observation_refs": row.get("observation_refs", []),
                "artifact_refs": row.get("artifact_refs", []),
            }
            history_refs = [{"revision": entry.get("revision"), "evidence_refs": entry["evidence_refs"]}
                            for entry in row.get("history", []) if entry.get("evidence_refs")]
            if history_refs:
                document["sources"][row["id"]]["history_evidence_refs"] = history_refs
        for row in package["entities"]:
            document["sources"][row["id"]] = {
                "kind": "entity", "revision": row["revision"], "entity_kind": row.get("kind"),
                "location": {"path": "state.json", "collection": "entities", "id": row["id"]},
                "relations": {key: copy.deepcopy(row[key]) for key in
                              ("source_refs", "owner_ref", "tenant_ref", "asset_ref") if row.get(key)},
            }
        for observation in package["observations"]:
            raw = observation["raw"] or {}
            subjects = raw.get("subject_refs", [])
            dimensions = {key: copy.deepcopy(raw[key]) for key in (
                "actor_ref", "object_ref", "object_refs", "entrypoint_ref", "action", "stage",
                "environment", "session_generation", "state") if key in raw}
            # Subject objects include response products. They are deliberately not
            # labeled as request objects, controls, ownership, or verified impact.
            dimensions["subject_object_refs"] = sorted(ref for ref in subjects
                if corpus.entities.get(ref, {}).get("kind") == "object")
            dimensions["entrypoint_refs"] = sorted(ref for ref in subjects
                if corpus.entities.get(ref, {}).get("kind") == "endpoint")
            request = raw.get("request") or {}
            if isinstance(request, dict) and "method" in request:
                dimensions["request_method"] = request["method"]
            document["observations"][observation["id"]] = {
                "revision": observation["revision"], "status": observation["status"],
                "provenance": observation["provenance"], "dimensions": dimensions,
            }
        for artifact in package["artifacts"]:
            aid = artifact["id"]
            meta = corpus.artifacts.get(aid, {})
            document["artifacts"][aid] = {
                "path": meta.get("path"), "sha256": meta.get("sha256"), "bytes": meta.get("bytes"),
                "status": artifact["status"],
            }
        for key in sorted(selected):
            block = corpus.blocks[key]
            page = corpus.pages[block["page_id"]]
            conditions = {**page.get("conditions", {}), **block.get("conditions", {})}
            condition_id = digest(encode(conditions).encode("utf-8"))
            document["conditions"][condition_id] = conditions
            entry = {
                "title": optimized[key].get("title", ""), "role": optimized[key].get("role", "explanation"),
                "text_ref": {"path": page["path"], "anchor": block["anchor"],
                             "content_hash": block["content_hash"]},
                "basis_state_revision": page["basis_state_revision"], "condition_ref": condition_id,
                "subject_refs": optimized[key].get("subject_refs", []),
                "source_refs": block.get("source_refs", []),
                "required_block_refs": block.get("required_block_refs", []),
                "knowledge": copy.deepcopy(block.get("knowledge", {})),
            }
            document["blocks"][key] = entry
            annotation = entry["knowledge"]
            if "knowledge" in block:
                # A neighboring block's evidence must not silently justify an annotation.
                block_package, block_issues = corpus.package(block_keys=[key], _expand_artifacts=False)
                issues.extend(block_issues)
                validation = validate_block_knowledge(corpus, key, block_package)
                issues.extend(validation)
                if not any(issue["code"].startswith("knowledge_") for issue in validation):
                    entry["reasoning"] = block_reasoning(corpus, key, block_package)
            if entry["role"] not in {"navigation", "history"}:
                missing = [facet for facet in KNOWLEDGE_FACETS
                           if not isinstance(annotation, dict) or not annotation.get(facet)]
                if missing:
                    document["metadata_gaps"].append({"block_ref": key, "missing_facets": missing,
                        "meaning": "not_structured; inspect source text before claiming evidence is missing"})
    for check in document["page_checks"]:
        issues.extend(check["issues"])
    unique = {encode(issue): issue for issue in issues}
    document["issues"] = [unique[key] for key in sorted(unique)]
    document["status"] = ("unavailable" if package is None or any(
        issue["code"] not in REVIEW_ISSUES for issue in issues)
        else "review_required" if issues else "ready")
    return document


def knowledge(root, run_id, block_refs=()):
    """Return a current, validated view; saved knowledge files are never authoritative."""
    corpus = _load(root, run_id)
    document = _knowledge(corpus, block_refs)
    if not corpus.stable():
        raise RetrievalError("Wiki corpus changed during knowledge read; retry on a stable snapshot")
    return document


def _load(root, run_id):
    try:
        corpus = Corpus(root, run_id)
        if corpus.load_issues:
            raise RetrievalError("Wiki manifest is unavailable; optimization requires a valid manifest")
        return corpus
    except (KeyError, TypeError, AttributeError, UnicodeError, json.JSONDecodeError) as exc:
        raise RetrievalError(f"Wiki corpus structure is invalid: {exc}") from exc


def _report(corpus):
    repeated = []
    for field in ("checked_candidates", "conditions", "discovery_scope", "source_refs"):
        copies = Counter(encode(page[field]) for page in corpus.pages.values() if field in page)
        repeated.append({
            "field": field,
            "bytes": sum(len(value.encode("utf-8")) * count for value, count in copies.items()),
            "repeated_bytes": sum(len(value.encode("utf-8")) * (count - 1)
                                  for value, count in copies.items()),
        })
    checks = [corpus.page_check(pid) for pid in corpus.pages]
    for aid in corpus.artifacts:
        corpus.artifact(aid)
    for oid in corpus.observations:
        corpus.observation(oid)
    _, block_issues = corpus.block_closure(corpus.blocks)
    issues = [issue for check in checks for issue in check["issues"]]
    issues.extend(block_issues)
    issues.extend(issue for item in corpus.art_cache.values() for issue in item["issues"])
    issues.extend(issue for item in corpus.obs_cache.values() for issue in item["issues"])
    issues = list({encode(issue): issue for issue in issues}.values())
    knowledge_view = _knowledge(corpus)
    issues.extend(knowledge_view["issues"])
    issues = list({encode(issue): issue for issue in issues}.values())
    manifest, changes = optimized_manifest(corpus)
    before_bytes = len(corpus.read_bytes(corpus.manifest_path))
    after_bytes = len((encode(manifest) + "\n").encode("utf-8"))
    inherited = []
    snapshots = []
    page_bytes = 0
    roles = Counter()
    for page in corpus.pages.values():
        raw = corpus.read_bytes(page["path"])
        page_bytes += len(raw)
        text = raw.decode("utf-8")
        preamble = text.split('<a id="', 1)[0]
        snapshots.extend(line.strip() for line in preamble.splitlines() if line.startswith(">"))
        for block in page["blocks"]:
            loaded = corpus.blocks[f'{page["page_id"]}/{block["block_id"]}']
            roles["navigation" if is_navigation(loaded) else block.get("role", "explanation")] += 1
            if "subject_refs" not in block:
                derived = derived_subjects(corpus, loaded)
                inherited.append({
                    "page_id": page["page_id"], "block_id": block["block_id"],
                    "page_subject_count": len(page.get("subject_refs", [])),
                    "derived_subject_refs": derived,
                    "unsupported_inherited_subject_refs": sorted(set(page.get("subject_refs", [])) - set(derived)),
                })
    snapshot_counts = Counter(snapshots)
    signatures = Counter(encode(candidate) for page in corpus.pages.values()
                         for candidate in page.get("checked_candidates", []))
    revisions = Counter(page.get("basis_state_revision") for page in corpus.pages.values())
    status = ("unavailable" if any(issue["code"] not in REVIEW_ISSUES for issue in issues)
              else "review_required" if issues else "ready")
    return {
        "run_id": corpus.run_id, "state_revision": corpus.state["revision"],
        "root": str(corpus.root), "manifest_path": corpus.manifest_path,
        "status": status, "issues": issues,
        "content": {
            "pages": len(corpus.pages), "blocks": len(corpus.blocks), "page_bytes": page_bytes,
            "block_roles": dict(roles),
            "missing_block_titles": sum(not block.get("title") for block in corpus.blocks.values()),
            "inherited_block_scopes": inherited,
            "snapshot_preambles": len(snapshots),
            "shared_snapshot_groups": [
                {"basis_state_revision": revision, "pages": count}
                for revision, count in revisions.items() if count > 1],
            "repeated_snapshot_bytes": sum(len(value.encode("utf-8")) * (count - 1)
                                           for value, count in snapshot_counts.items()),
        },
        "storage": {
            "manifest_bytes": before_bytes,
            "optimized_manifest_bytes": after_bytes,
            "manifest_bytes_saved": before_bytes - after_bytes,
            "repeated_page_metadata": repeated,
            "candidate_signatures": {
                "occurrences": sum(signatures.values()), "unique": len(signatures),
                "repeated_value_bytes": sum(len(value.encode("utf-8")) * (count - 1)
                                            for value, count in signatures.items()),
            },
        },
        "knowledge": {
            "schema_version": 1, "evidence": False, "status": knowledge_view["status"],
            "blocks": len(knowledge_view["blocks"]),
            "annotated_blocks": sum(bool(block["knowledge"]) for block in knowledge_view["blocks"].values()),
            "condition_sets": len(knowledge_view["conditions"]),
            "unique_observations": len(knowledge_view["observations"]),
            "source_entries": len(knowledge_view["sources"]),
            "metadata_gaps": knowledge_view["metadata_gaps"],
        },
        "proposed_changes": changes,
        "page_checks": checks,
    }


def audit(root, run_id):
    """Return storage/content findings without writing to the corpus."""
    corpus = _load(root, run_id)
    report = _report(corpus)
    if not corpus.stable():
        raise RetrievalError("Wiki corpus changed during audit; retry on a stable snapshot")
    return report


def _output_path(root, output_root):
    if not output_root:
        raise RetrievalError("output_root is required and must be a new, separate directory")
    output = Path(output_root).absolute()
    for parent in (output, *output.parents):
        if parent.is_symlink():
            raise RetrievalError("output_root and its parents must not be symbolic links")
    output = output.resolve()
    if output == root or output.is_relative_to(root) or root.is_relative_to(output):
        raise RetrievalError("output_root must be separate from the input corpus")
    if output.exists():
        raise RetrievalError("output_root already exists; refusing to overwrite any files")
    if not output.parent.is_dir():
        raise RetrievalError("output_root parent directory must already exist")
    return output


def optimize(root, run_id, output_root):
    """Preserve registered evidence/pages; enrich metadata and add a derived knowledge view."""
    corpus = _load(root, run_id)
    output = _output_path(corpus.root, output_root)
    report = _report(corpus)
    # New candidates and stale snapshots remain visibly stale in the derived copy.
    if any(issue["code"] not in REVIEW_ISSUES for issue in report["issues"]):
        raise RetrievalError("Wiki integrity or references are invalid; inspect wiki audit before optimizing")
    manifest, _ = optimized_manifest(corpus)
    registered = {"state.json", corpus.manifest_path}
    registered.update(page["path"] for page in corpus.pages.values())
    registered.update(artifact["path"] for artifact in corpus.artifacts.values())
    if Path(KNOWLEDGE_PATH) in {Path(path) for path in registered}:
        raise RetrievalError("Derived knowledge path conflicts with a registered source file")
    knowledge_view = _knowledge(corpus)
    # The persisted view describes the manifest actually written to the derived copy.
    knowledge_view["basis"]["manifest_sha256"] = digest((encode(manifest) + "\n").encode("utf-8"))
    files = {Path(KNOWLEDGE_PATH): (encode(knowledge_view) + "\n").encode("utf-8")}
    for relative in sorted(registered):
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise RetrievalError("Registered paths must be relative without parent traversal")
        files[path] = corpus.read_bytes(relative)
    files[Path(corpus.manifest_path)] = (encode(manifest) + "\n").encode("utf-8")
    if not corpus.stable():
        raise RetrievalError("Wiki corpus changed during optimization; retry on a stable snapshot")
    output.mkdir()
    try:
        for relative, data in files.items():
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
        derived = _load(output, run_id)
        for pid in derived.pages:
            check = derived.page_check(pid)
            if check["status"] == "unavailable":
                raise RetrievalError("Derived Wiki did not preserve page integrity")
    except BaseException:
        shutil.rmtree(output)
        raise
    report.update({
        "output_root": str(output), "files_written": len(files),
        "preserved_state_and_evidence": True, "preserved_page_bytes": True,
        "knowledge_path": KNOWLEDGE_PATH,
        "knowledge_bytes": len(files[Path(KNOWLEDGE_PATH)]),
    })
    return report
