"""Exact, attributable projections of stored observations; no generated evidence."""

import re


def pointer_value(value, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ValueError("JSON Pointer must be empty or begin with /")
    if not pointer:
        return value
    for part in pointer.split("/")[1:]:
        if re.search(r"~(?![01])", part):
            raise ValueError("invalid JSON Pointer escape")
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", key):
                raise ValueError("JSON Pointer array index must be nonnegative")
            index = int(key)
            if index >= len(value):
                raise ValueError("JSON Pointer is outside the array")
            value = value[index]
        elif isinstance(value, dict) and key in value:
            value = value[key]
        else:
            raise ValueError("JSON Pointer does not identify an existing value")
    return value


def json_excerpt(observation, pointer):
    if observation["status"] != "ready":
        raise ValueError("cannot extract from unavailable observation")
    return {"observation_ref": observation["id"],
            "artifact_ref": observation["provenance"]["artifact_id"],
            "source_sha256": observation["provenance"]["content_hash"],
            "selector": {"pointer": pointer}, "representation": "json_value",
            "value": pointer_value(observation["raw"], pointer),
            "evidence_role": "original_excerpt", "independent_observation": False}


def observation_excerpts(corpus, observation):
    result = []
    for selector in observation["index"].get("excerpt_selectors", []):
        if "pointer" in selector:
            result.append(json_excerpt(observation, selector["pointer"]))
        else:
            aid = observation["index"].get("source_artifact_id")
            if not aid:
                raise ValueError("byte excerpts require an imported source_path")
            row = corpus.artifact_window(aid, selector["offset"], selector["length"])
            if row["status"] != "ready":
                continue
            result.append({"observation_ref": observation["id"], "artifact_ref": aid,
                "source_sha256": row["provenance"]["sha256"],
                "selector": {"offset": row["range"]["offset"], "length": row["range"]["length"]},
                "range_sha256": row["range"]["sha256"], "encoding": row["encoding"],
                "value": row["content"], "representation": "source_bytes",
                "evidence_role": "original_excerpt", "independent_observation": False})
    return result


def validate_selectors(selectors):
    if not isinstance(selectors, list):
        raise ValueError("excerpt_selectors must be an array")
    for selector in selectors:
        if not isinstance(selector, dict):
            raise ValueError("an excerpt selector must be an object")
        if set(selector) == {"pointer"} and isinstance(selector["pointer"], str):
            continue
        if (set(selector) == {"offset", "length"} and type(selector["offset"]) is int
                and type(selector["length"]) is int and selector["offset"] >= 0 and selector["length"] > 0):
            continue
        raise ValueError("use either pointer or nonnegative offset and positive length")
