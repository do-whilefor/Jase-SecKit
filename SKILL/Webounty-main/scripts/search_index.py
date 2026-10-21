"""Lexical retrieval over run content with a rebuildable local term projection."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from math import log1p
import re
import unicodedata

from lexical_proximity import pairs, lexical_length
from query_expansion import expand_query, query_parts
from ranking_context import condition_signal, mirror_owner


RANKING_VERSION = "local-3"


_TOKENS = re.compile(r"[a-z0-9_]+(?:[-/.][a-z0-9_]+)*|[\u3400-\u9fff]+", re.I)
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_PARTS = re.compile(r"[a-z0-9]+")
_BOUNDARY_TOKENS = re.compile(r"[\w-]+|[^\w-]", re.UNICODE)
_ANCHOR_TAG = re.compile(r'<a\s+id="[^"]+"\s*></a>', re.I)
_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.M)
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\(([^\n)]*)\)")

_BOOKKEEPING = frozenset({
    "id", "observation_id", "run_id", "revision", "kind", "fixture",
    "basis_status", "status", "classification", "provenance", "issues", "index",
    "content_hash", "sha256", "hash", "bytes", "line", "artifact_id",
    "sealed", "observed_at", "created_at", "updated_at", "timestamp",
    "history", "requires", "contradicted_by", "corrected_by",
    "correction_refs", "superseded_by", "contradicts", "supporting_fact_ids",
    "contradicting_fact_ids", "source_refs", "evidence_refs", "step_refs",
    "observation_refs", "artifact_refs", "subject_refs", "owner_ref",
    "tenant_ref", "asset_ref", "actor_ref", "request_object_refs",
})
_WEIGHTS = {
    "title": 3.0, "aliases": 2.5, "summary": 2.0,
    "questions": 2.0, "keywords": 2.2, "body": 1.0, "knowledge": 0.5, "page": 0.25,
    "navigation": 0.8, "source": 1.0, "reopen_when": 2.0, "requirements": 1.5,
}


def _text(value, *, keys=False):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join((str(k) + " " if keys else "") + _text(v, keys=keys)
                        for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return " ".join(_text(v, keys=keys) for v in value)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _terms(value):
    """Preserve endpoint/identifier tokens and add components and Chinese bigrams."""
    for match in _TOKENS.finditer(unicodedata.normalize("NFKC", value)):
        original = match.group()
        token = original.casefold()
        if "\u3400" <= token[0] <= "\u9fff":
            if len(token) == 1:
                yield token
            else:
                yield from (token[i:i + 2] for i in range(len(token) - 1))
        else:
            yield token
            if "/" in token or "." in token or "-" in token or "_" in token:
                yield from _PARTS.findall(token)
            components = _CAMEL.split(original)
            if len(components) > 1:
                for component in components:
                    yield from _PARTS.findall(component.casefold())


# Only query expansion drops ordinary function words. Original evidence remains
# fully indexed; single-token and explicitly quoted searches preserve literals.
_QUERY_NOISE = frozenset("a an the is are was were be been being of for to from with in on at by as and or this that these those it its what which who when where why how did does do can could would should please find show tell me about 是否 什么 如何 可以 这个 这些 请问".split())


def query_terms(query, tokenize=_terms):
    terms = set(tokenize(query))
    if len(terms) <= 1:
        return terms
    literal = {term for text, protected in query_parts(query) if protected
               for term in tokenize(text)}
    return (terms - _QUERY_NOISE) | literal


def _refs(value):
    if isinstance(value, (str, dict)):
        value = [value]
    return {v if isinstance(v, str) else v["id"] for v in value}


class _Matcher:
    """Aho-Corasick over tokens or characters; queries never loop over corpus IDs."""

    def __init__(self, patterns):
        self.edges, self.failure, self.output = [{}], [0], [[]]
        for sequence, value in patterns:
            node = 0
            for part in sequence:
                child = self.edges[node].get(part)
                if child is None:
                    child = len(self.edges)
                    self.edges[node][part] = child
                    self.edges.append({})
                    self.failure.append(0)
                    self.output.append([])
                node = child
            if node:
                self.output[node].append(value)
        pending = deque(self.edges[0].values())
        while pending:
            node = pending.popleft()
            for part, child in self.edges[node].items():
                pending.append(child)
                fallback = self.failure[node]
                while fallback and part not in self.edges[fallback]:
                    fallback = self.failure[fallback]
                self.failure[child] = self.edges[fallback].get(part, 0)
                self.output[child].extend(self.output[self.failure[child]])

    def find(self, sequence):
        node = 0
        for offset, part in enumerate(sequence):
            while node and part not in self.edges[node]:
                node = self.failure[node]
            node = self.edges[node].get(part, 0)
            for value in self.output[node]:
                yield offset, value


def _boundary(char):
    return bool(char) and (char.isalnum() or char in "_-")


def _knowledge_text(annotation):
    """Only authored discriminators are searchable; IDs and declared states are not.

    This extraction is not validation. The caller must admit its block's own
    source package before adding the text to the lexical index.
    """
    if not isinstance(annotation, dict):
        return ""
    parts = []

    def take(row, fields):
        if not isinstance(row, dict):
            return
        for field in fields:
            value = row.get(field)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(item for item in value if isinstance(item, str))

    take(annotation, ("limitations", "reopen_when", "next_discriminator"))
    take(annotation.get("boundary"), ("action", "relationship", "expectation"))
    for group, fields in (
        ("controls", ("note",)),
        ("experiments", ("expected", "falsifier", "confounders")),
        ("capability_links", ("output", "required_input", "unresolved_preconditions")),
    ):
        children = annotation.get(group, [])
        if isinstance(children, list):
            for child in children:
                take(child, fields)
    return " ".join(parts)


def _record_text(value):
    """Search authored reasoning, not identifiers buried in structured links.

    Conditions and actual response/result payloads retain their business keys;
    this filter is never applied to raw observations.
    """
    if isinstance(value, dict):
        parts = []
        for key, child in value.items():
            if key in {"conditions", "constraints", "request", "response", "actual_result", "result"}:
                parts.append(_text(child, keys=True))
            elif (key not in _BOOKKEEPING and key not in {"steps", "assessment", "provide_index", "need_index"}
                  and not key.startswith("_") and not key.endswith(("_ref", "_refs", "_ids"))):
                parts.append(_record_text(child))
        return " ".join(parts)
    if isinstance(value, (list, tuple)):
        return " ".join(_record_text(child) for child in value)
    return _text(value)


def _fields(kind, row, corpus):
    if kind == "block":
        if hasattr(corpus, "ensure_page"):
            corpus.ensure_page(row["page_id"])
        page = corpus.pages[row["page_id"]]
        body = _MARKDOWN_LINK.sub(r"\1", _ANCHOR_TAG.sub("", row["text"]))
        owner = mirror_owner(corpus, row["page_id"] + "/" + row["block_id"])
        if owner is not None:
            # Generated Markdown includes revision history. Search the current
            # authoritative claim, so an old summary cannot revive its owner.
            body = _record_text(corpus.records[owner[1]])
        heading = _HEADING.search(body)
        retrieval = row.get("retrieval", {})
        result = {name: _text(row.get(name, retrieval.get(name, "")))
                  for name in ("title", "aliases", "summary", "questions", "keywords")}
        result["title"] = result["title"] or (heading.group(1) if heading else "")
        result["body"] = body
        page_retrieval = page.get("retrieval", {})
        result["page"] = _text([page.get("title", ""), page.get("aliases", []),
                               page.get("summary", page_retrieval.get("summary", "")),
                               page.get("keywords", page_retrieval.get("keywords", []))])
        paths = getattr(corpus, "navigation_paths", {})
        result["navigation"] = _text(paths.get(row["page_id"], []))
        result["questions"] += " " + _text(page.get("questions", page_retrieval.get("questions", "")))
        knowledge = _knowledge_text(row.get("knowledge"))
        if knowledge:
            # No package calls for unannotated legacy content. Corpus owns any
            # source/knowledge caches within its snapshot; this index keeps none.
            package, issues = corpus.package(
                block_keys=[row["page_id"] + "/" + row["block_id"]], _expand_artifacts=False)
            if package is not None and all(issue.get("code") in {
                    "reasoning_review_required", "current_condition_conflict", "current_condition_unknown"}
                    for issue in issues):
                # Missing premises remain relevant prose, never proof. Invalid
                # references, shapes or underlying sources cannot affect ranking.
                result["knowledge"] = knowledge
        return result
    result = {name: _text(row.get(name, ""))
              for name in ("title", "aliases", "summary", "questions", "keywords")}
    if kind == "record":
        result["reopen_when"] = _text(row.get("reopen_when", ""))
        result["requirements"] = _text([row.get("blockers", []), row.get("unresolved_preconditions", []),
                                         row.get("capability", {}).get("needs", [])], keys=True)
    body = {key: value for key, value in row.items()
            if key not in _BOOKKEEPING and key not in result
            and not key.startswith("_") and not key.endswith(("_refs", "_ref"))}
    payload = ""
    if kind == "observation":
        raw = corpus.observation(row["id"]).get("raw")
        if raw:
            # Only the observation envelope is metadata. Payload keys, HTTP status,
            # null values and trailing response content remain searchable evidence.
            payload = _text({key: value for key, value in raw.items()
                             if key not in _BOOKKEEPING
                             and not key.startswith("_") and not key.endswith(("_refs", "_ref"))}, keys=True)
    result["body"] = (_record_text(body) if kind == "record" else _text(body)) + " " + payload
    return result


def _role(block):
    role = block.get("role", "explanation")
    if role in {"navigation", "index", "sources", "history"}:
        return role
    # Legacy manifests sometimes label navigation as explanation. Inspect its
    # structure: link lists and link tables have no standalone evidence prose.
    if _MARKDOWN_LINK.search(block.get("text", "")):
        body = _ANCHOR_TAG.sub("", block["text"])
        body = _HEADING.sub("", body)
        lines = body.splitlines()
        headers = {i - 1 for i, line in enumerate(lines)
                   if "|" in line and "-" in line
                   and not any(char.isalnum() for char in line)}
        prose = [line for i, line in enumerate(lines)
                 if i not in headers and any(char.isalnum() for char in line)]
        links = 0
        for line in prose:
            targets = [match.group(2) for match in _MARKDOWN_LINK.finditer(line)]
            local_links = targets and all(target.startswith("#") or ".md" in target for target in targets)
            remainder = _MARKDOWN_LINK.sub("", line)
            if local_links and (line.strip().startswith("|") or
                                not any(char.isalnum() for char in remainder)):
                links += 1
        if prose and links == len(prose):
            return "navigation"
        if links >= 2 and links > len(prose) / 2:
            return "related"
    return role


def rank(corpus, query, anchors, *, with_exact=False, with_reasons=False):
    """Return ranked references; lexical candidates never establish evidence validity."""
    # Source windows belong to this query, including empty/anchor-only requests.
    corpus.retrieval_source_matches = {}
    anchor_list = list(anchors)
    exact_inputs = [original.casefold() for original in [query] + anchor_list]
    # A necessary substring condition, not a match: keep boundary/ambiguity
    # checks below. This avoids building thousands of irrelevant trie branches.
    prefixes = {value[i:i + 2] for value in exact_inputs for i in range(len(value))}
    initial_chars = {char for value in exact_inputs for char in value}

    def may_occur(value):
        return value[:2] in (initial_chars if len(value) == 1 else prefixes)

    metadata = getattr(corpus, "metadata", None)
    aliases, identifiers = defaultdict(set), defaultdict(set)
    if metadata is not None:
        from metadata_cache import Documents
        documents = Documents(corpus)
        for category, value, alias_kind, kind, rid in metadata.union("search_name", prefixes | initial_chars):
            if category == "id":
                identifiers[value].add((kind, rid))
            else:
                aliases[(alias_kind, value)].add((kind, rid))
    else:
        documents = {}
        for kind, group in (("record", corpus.records), ("entity", corpus.entities),
                            ("observation", corpus.observations), ("block", corpus.blocks)):
            for rid, row in group.items():
                key = kind, rid
                documents[key] = row
                ids = [rid]
                if kind == "block":
                    ids.extend((row["block_id"], row["page_id"]))
                else:
                    alias_kind = row.get("kind", kind).casefold()
                    for alias in [row.get("title", "")] + row.get("aliases", []):
                        alias = alias.casefold()
                        if alias and may_occur(alias):
                            aliases[(alias_kind, alias)].add(key)
                for identifier in ids:
                    identifier = identifier.casefold()
                    if may_occur(identifier):
                        identifiers[identifier].add(key)

    original_terms = query_terms(query)
    expanded = expand_query(query, _terms, original_terms)
    term_weights = {**expanded, **dict.fromkeys(original_terms, 1.0)}
    query_pairs = pairs(query, original_terms)
    terms = set(term_weights) | query_pairs.keys()
    if terms and hasattr(corpus, "root"):
        from retrieval_index import lexical_projection
        postings, field_lengths, averages, roles, unavailable = lexical_projection(
            corpus, documents, terms, _fields, _terms, _role, original_terms=original_terms)
    elif metadata is not None and not terms:
        postings, field_lengths, averages, roles, unavailable = {}, {}, {}, {}, set()
    else:
        postings, field_lengths, averages, roles, unavailable = _memory_projection(corpus, documents, terms)
    scores = defaultdict(float)
    matching_terms, expanded_hits = defaultdict(set), defaultdict(set)
    signal_reasons = defaultdict(list)
    for term in sorted(term_weights):
        found = postings.get(term, {})
        idf = log1p((len(documents) - len(found) + 0.5) / (len(found) + 0.5))
        for key, fields in found.items():
            weighted_tf = sum(_WEIGHTS[field] * count /
                              (0.25 + 0.75 * field_lengths[key][field] / averages[field])
                              for field, count in fields.items())
            scores[key] += term_weights[term] * idf * weighted_tf * 2.2 / (1.2 + weighted_tf)
            (matching_terms if term in original_terms else expanded_hits)[key].add(term)
    pair_hits = defaultdict(float)
    for term, requested_strength in query_pairs.items():
        for key, fields in postings.get(term, {}).items():
            pair_hits[key] += min(requested_strength, max(fields.values()))
    pair_total = sum(query_pairs.values())
    for key in scores:
        coverage = len(matching_terms[key]) / len(original_terms) if original_terms else 0
        proximity = pair_hits[key] / pair_total if pair_total else 0
        scores[key] *= 1 + 0.2 * coverage + 0.35 * proximity
        if expanded_hits[key]:
            signal_reasons[key].append({"kind": "query_expansion", "matched_terms": sorted(expanded_hits[key])})
        if proximity:
            signal_reasons[key].append({"kind": "ordered_proximity", "coverage": round(proximity, 6)})
        signal = condition_signal(corpus, key, documents[key])
        if signal is not None:
            scores[key] *= signal["multiplier"]
            signal_reasons[key].append({"kind": "execution_conditions", **signal})

    # IDs use word/hyphen tokens plus literal separators. This recognizes nested
    # block references and overlapping IDs while retaining the previous boundaries.
    id_matcher = _Matcher((_BOUNDARY_TOKENS.findall(identifier), identifier)
                          for identifier in identifiers)
    by_alias = defaultdict(set)
    for (_, alias), options in aliases.items():
        by_alias[alias].update(options)
    alias_matcher = _Matcher((alias, alias) for alias in by_alias)
    issues, exact, explicit_anchors = [], set(), set()
    for original in [query] + anchor_list:
        value = original.casefold()
        matched = set()
        chunks = list(_BOUNDARY_TOKENS.finditer(value))
        literal_matches, scoped_parts = [], set()
        for end, identifier in id_matcher.find(chunk.group() for chunk in chunks):
            finish = chunks[end].end()
            start = finish - len(identifier)
            if (not start or not _boundary(value[start - 1])) and (
                    finish == len(value) or not _boundary(value[finish])):
                literal_matches.append((start, finish, identifier))
                for kind, rid in identifiers[identifier]:
                    if kind == "block" and rid.casefold() == identifier:
                        block = corpus.blocks[rid]
                        scoped_parts.add((start, start + len(block["page_id"].casefold())))
                        scoped_parts.add((finish - len(block["block_id"].casefold()), finish))
        for start, finish, identifier in literal_matches:
            options = identifiers[identifier]
            # PAGE/BLOCK names one block. Its PAGE prefix and BLOCK suffix
            # must not also select siblings or same-named blocks on other pages.
            # A separately written PAGE or BLOCK remains an independent match.
            if (start, finish) in scoped_parts:
                matched.update(key for key in options if key[0] != "block")
            else:
                matched.update(options)
        qualified = re.fullmatch(r"([a-z_]+):(.+)", value, re.I)
        options_by_alias = {}
        if qualified:
            options = aliases.get((qualified[1], qualified[2]), set())
            if options:
                options_by_alias[original] = options
        else:
            for end, alias in alias_matcher.find(value):
                start, finish = end + 1 - len(alias), end + 1
                # Chinese names may occur inside natural prose; Latin aliases
                # must not turn administrator into an exact match for admin.
                if alias[0].isascii() and _boundary(alias[0]) and start and _boundary(value[start - 1]):
                    continue
                if alias[-1].isascii() and _boundary(alias[-1]) and finish < len(value) and _boundary(value[finish]):
                    continue
                options_by_alias[alias] = by_alias[alias]
        for alias, options in sorted(options_by_alias.items()):
            matched.update(options)
            if len(options) > 1:
                issues.append({"code": "ambiguous_alias", "alias": alias,
                               "candidate_refs": sorted(rid for _, rid in options)})
        if original in anchor_list and not matched:
            issues.append({"code": "unknown_anchor", "anchor": original})
        exact.update(matched)
        if original in anchor_list:
            explicit_anchors.update(matched)

    priorities = {key: 3 for key in exact}
    relation_reasons = {}
    # Bring explicit corrections to a lexical hit forward without claiming that
    # either statement is true. A directly requested ID/alias still comes first.
    best_score = max(scores.values(), default=0)
    focus = exact | {key for key, score in scores.items() if score == best_score}
    # Lower-ranked claims also need their competing records, but must not
    # promote unrelated corrections ahead of the query's strongest matches.
    correction_links = defaultdict(set)
    all_hits = scores.keys() | exact
    all_record_hits = {rid for kind, rid in all_hits if kind == "record"}
    for kind, rid in all_hits:
        if kind == "block":
            all_record_hits.update(_refs(corpus.blocks[rid].get("source_refs", [])))
    for rid in sorted(all_record_hits & corpus.records.keys()):
        for field in ("corrected_by", "superseded_by", "correction_refs", "contradicted_by", "contradicts"):
            correction_links[rid].update(_refs(corpus.records[rid].get(field, [])))
        if metadata is not None:
            correction_links[rid].update(metadata.links("contradiction")[rid])
    if metadata is None:
        for rid, row in corpus.records.items():
            for target in all_record_hits & _refs(row.get("contradicts", [])):
                correction_links[target].add(rid)
    hit_records = {rid for kind, rid in focus if kind == "record"}
    for kind, rid in focus:
        if kind == "block":
            hit_records.update(_refs(corpus.blocks[rid].get("source_refs", [])))
    correction_targets = set()
    correction_rows = ((rid, corpus.records[rid]) for rid in hit_records) if metadata is not None else corpus.records.items()
    for rid, row in correction_rows:
        if rid in hit_records:
            for field in ("corrected_by", "superseded_by", "correction_refs", "contradicted_by"):
                correction_targets.update(_refs(row.get(field, [])))
        if hit_records.intersection(_refs(row.get("contradicts", []))):
            correction_targets.add(rid)
    if metadata is not None:
        correction_targets.update(metadata.union("contradiction", hit_records))
    for rid in sorted(rid for rid in correction_targets if rid in corpus.records):
        if corpus.records[rid].get("status", "").casefold() in {"refuted", "withdrawn", "superseded", "corrected"}:
            continue
        key = "record", rid
        if key not in exact:
            priorities[key] = 2
            relation_reasons[key] = "counterevidence_relation"
    subjects = set()
    for kind, rid in exact:
        if kind == "entity":
            subjects.add(rid)
        elif kind in {"record", "observation"}:
            subjects.update(_refs(documents[(kind, rid)].get("subject_refs", [])))
    exact_ids = {rid for _, rid in exact}
    if metadata is not None:
        block_ids = {rid for kind, rid in scores.keys() | exact if kind == "block"}
        block_ids.update(metadata.union("source_block", exact_ids))
        block_ids.update(metadata.union("subject_block", subjects))
        block_rows = ((bid, corpus.blocks[bid]) for bid in sorted(block_ids))
    else:
        block_rows = corpus.blocks.items()
    mirrors = {}
    for bid, block in block_rows:
        key = "block", bid
        role = roles.get(key, _role(block) if metadata is not None and not terms else block.get("role", "explanation"))
        if key in scores and key not in exact:
            scores[key] *= 0.25 if role in {"history", "related"} else 0.08 if role in {"navigation", "index", "sources"} else 1
        if key in exact or role in {"navigation", "index", "sources", "history", "related"}:
            continue
        if key in unavailable or block.get("_issues") or getattr(corpus, "page_issues", {}).get(block["page_id"]):
            continue
        # Generated pages mirror a record, not a second independent judgment.
        # Let their searchable prose locate that record without summing copies.
        owner = mirror_owner(corpus, bid, exact)
        if owner is not None and (key in scores or key in priorities):
            mirrors[key] = owner
            if scores.get(key, 0) > scores.get(owner, 0):
                signal_reasons[owner] = list(signal_reasons[key])
            scores[owner] = max(scores.get(owner, 0), scores.get(key, 0))
            signal_reasons[owner].append({"kind": "record_mirror", "block_ref": bid})
            scores.pop(key, None)
            priorities.pop(key, None)
            continue
        page = corpus.pages[block["page_id"]]
        direct = bool(exact_ids & _refs(block.get("source_refs", [])))
        scoped = bool(subjects & _refs(block.get("subject_refs", page.get("subject_refs", []))))
        if direct or scoped:
            priorities[key] = 2 if direct else 1
            relation_reasons[key] = "source_relation" if direct else "subject_relation"
    ranked = sorted(scores.keys() | priorities.keys(),
                    key=lambda key: (-priorities.get(key, 0), -scores.get(key, 0), key[0] != "record", key))
    corpus.retrieval_mirrors = mirrors
    ordered = [key for key in ranked if key in exact]
    seen = set(ordered)
    for key in ranked:
        if key not in seen:
            ordered.append(key)
            seen.add(key)
        parents = ([key[1]] if key[0] == "record" else
                   _refs(corpus.blocks[key[1]].get("source_refs", [])) if key[0] == "block" else [])
        for rid in sorted({rid for parent in parents for rid in correction_links[parent]}):
            related = ("record", rid)
            if rid not in corpus.records or related in seen or related in exact:
                continue
            ordered.append(related)
            seen.add(related)
            relation_reasons.setdefault(related, "counterevidence_relation")
    ranked = ordered
    result = (ranked, issues, exact) if with_exact else (ranked, issues)
    if with_reasons:
        reasons = {}
        for key in ranked:
            items = []
            if key in explicit_anchors:
                items.append({"kind": "exact_anchor"})
            elif key in exact:
                items.append({"kind": "exact_query"})
            if key in relation_reasons:
                items.append({"kind": relation_reasons[key]})
            if key in scores:
                items.append({"kind": "lexical", "score": round(scores[key], 6)})
            items.extend(signal_reasons[key])
            reasons[key] = items
        return (*result, reasons)
    return result


def _memory_projection(corpus, documents, terms):
    """Transient path for in-memory callers and explicit-ID reads without text queries."""
    postings = defaultdict(dict)
    field_lengths, field_totals, field_counts = {}, Counter(), Counter()
    field_cache, roles, unavailable = {}, {}, set()
    for key, row in documents.items():
        if key[0] == "block":
            roles[key] = _role(row)
            if row.get("_issues") or getattr(corpus, "page_issues", {}).get(row["page_id"]):
                unavailable.add(key)
                continue
        if not terms:
            continue
        lengths = field_lengths[key] = {}
        for field, value in _fields(key[0], row, corpus).items():
            if not value:
                continue
            if value not in field_cache:
                counts = Counter(_terms(value))
                counts.update(pairs(value))
                field_cache[value] = (lexical_length(counts), {term: counts[term] for term in counts.keys() & terms})
            length, matches = field_cache[value]
            if not length:
                continue
            lengths[field] = length
            field_totals[field] += length
            field_counts[field] += 1
            for term, count in matches.items():
                postings[term].setdefault(key, {})[field] = count
    averages = {field: total / field_counts[field] for field, total in field_totals.items()}
    return postings, field_lengths, averages, roles, unavailable
