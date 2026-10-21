#!/usr/bin/env python3
"""Compare two sealed observations locally; differences are not verdicts."""

from __future__ import annotations

import hashlib
import json

from rag import RetrievalError


_MISSING = object()
_CONDITIONS = (
    "conditions", "environment", "target_version", "credential_generation",
    "session_generation", "stage", "signal_kind",
)
_IDENTITY = (
    "actor_ref", "tenant_ref", "owner_ref", "object_ref", "request_object_refs",
    "subject_refs",
)


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _equal(left, right):
    if left is _MISSING or right is _MISSING:
        return None if left is right else False
    # JSON booleans and numbers, and scalar/container types, remain distinct.
    return type(left) is type(right) and _encoded(left) == _encoded(right)


def _pointer(parent, part):
    return parent + "/" + str(part).replace("~", "~0").replace("/", "~1")


def _changed(left, right, path=""):
    """Exact changed locations as JSON Pointers, without copying field values."""
    if left is _MISSING and right is _MISSING or _equal(left, right):
        return []
    if isinstance(left, dict) and isinstance(right, dict):
        return [change for key in sorted(left.keys() | right.keys())
                for change in _changed(left.get(key, _MISSING), right.get(key, _MISSING),
                                       _pointer(path, key))]
    if isinstance(left, list) and isinstance(right, list):
        return [change for index in range(max(len(left), len(right)))
                for change in _changed(left[index] if index < len(left) else _MISSING,
                                       right[index] if index < len(right) else _MISSING,
                                       _pointer(path, index))]
    return [path]


def _summary(value):
    if value is _MISSING:
        return {"present": False}
    names = {dict: "object", list: "array", str: "string", bool: "boolean",
             int: "integer", float: "number", type(None): "null"}
    data = value.encode("utf-8") if isinstance(value, str) else _encoded(value)
    return {"present": True, "type": names[type(value)], "byte_length": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "encoding": "utf-8" if isinstance(value, str) else "canonical-json"}


def _view(value, *, whole_body=False):
    if value is _MISSING:
        return {"present": False}
    if whole_body or isinstance(value, (dict, list)):
        return {**_summary(value), "value_omitted": True}
    return {"present": True, "value": value}


def _pair(left, right, *, whole_body=False):
    return {"left": _view(left, whole_body=whole_body),
            "right": _view(right, whole_body=whole_body), "equal": _equal(left, right)}


def _lookup(raw, path):
    value = raw
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part, _MISSING)
        elif isinstance(value, list) and part.isascii() and part.isdigit():
            index = int(part)
            value = value[index] if index < len(value) else _MISSING
        else:
            return _MISSING
    return value


def _section(left, right, keys):
    a = {key: left[key] for key in keys if key in left}
    b = {key: right[key] for key in keys if key in right}
    return {"left": a, "right": b, "changed_paths": _changed(a, b)}


def _source(observation):
    result = {"observation_id": observation["id"], "revision": observation["revision"],
              "status": observation["status"], "provenance": observation["provenance"],
              "issues": observation["issues"]}
    if observation["index"].get("source_artifact_id"):
        result["source_artifact_id"] = observation["index"]["source_artifact_id"]
    return result


def compare(corpus, left_id, right_id, fields=()):
    """Return a JSON-serializable comparison, using Corpus's evidence checks.

    fields contains explicit dot paths into the stored raw observation. Missing
    evidence returns unavailable; invalid IDs/schema/paths raise RetrievalError.
    This function neither sends requests nor publishes an interpretation.
    """
    for oid in (left_id, right_id):
        if not isinstance(oid, str) or oid not in corpus.observations:
            raise RetrievalError(f"未知观察 ID: {oid!r}")
    if isinstance(fields, (str, bytes)):
        raise RetrievalError("fields 必须是点路径列表，不能是单个字符串")
    try:
        selected = list(fields)
    except TypeError as exc:
        raise RetrievalError("fields 必须是点路径列表") from exc
    if any(not isinstance(path, str) or not path or any(not part for part in path.split("."))
           for path in selected):
        raise RetrievalError("字段路径必须是非空点路径，例如 response.body.status")
    selected = list(dict.fromkeys(selected))

    left, right = corpus.observation(left_id), corpus.observation(right_id)
    result = {"run_id": corpus.run_id, "status": "ready", "assessment": "comparison_only",
              "observation_refs": [left_id, right_id],
              "sources": {"left": _source(left), "right": _source(right)}}
    if left["status"] != "ready" or right["status"] != "ready":
        result.update(status="unavailable", gaps=[{
            "code": "source_unavailable",
            "detail": "观察或关联原件未通过封存校验；不比较其内容。",
        }])
        return result
    a, b = left["raw"], right["raw"]
    for raw in (a, b):
        if not isinstance(raw, dict) or any(key in raw and not isinstance(raw[key], dict)
                                            for key in ("request", "response")):
            raise RetrievalError("观察须为 JSON 对象，已记录的 request / response 须为对象")

    request_a, request_b = a.get("request", _MISSING), b.get("request", _MISSING)
    response_a, response_b = a.get("response", {}), b.get("response", {})
    body_a, body_b = response_a.get("body", _MISSING), response_b.get("body", _MISSING)
    body_equal = _equal(body_a, body_b)
    result.update(
        conditions=_section(a, b, _CONDITIONS), identity=_section(a, b, _IDENTITY),
        request={"left": _summary(request_a), "right": _summary(request_b),
                 "equal": _equal(request_a, request_b),
                 "method": _pair(_lookup(a, "request.method"), _lookup(b, "request.method")),
                 "changed_paths": _changed(request_a, request_b, "/request")},
        response={"left_present": "response" in a, "right_present": "response" in b,
                  "status": _pair(response_a.get("status", _MISSING), response_b.get("status", _MISSING)),
                  "body": {"left": _summary(body_a), "right": _summary(body_b), "equal": body_equal,
                           "changed_paths": _changed(body_a, body_b, "/response/body")},
                  "metadata_changed_paths": _changed(
                      {k: v for k, v in response_a.items() if k != "body"},
                      {k: v for k, v in response_b.items() if k != "body"}, "/response")},
        selected_fields=[{"path": path, **_pair(_lookup(a, path), _lookup(b, path),
                                                whole_body=path == "response.body")}
                         for path in selected],
    )
    excluded = {*_CONDITIONS, *_IDENTITY, "request", "response", "observation_id", "run_id", "source_artifact"}
    result["other_changed_paths"] = _changed({k: v for k, v in a.items() if k not in excluded},
                                            {k: v for k, v in b.items() if k not in excluded})
    gaps = [{"code": "controls_not_established",
             "detail": "两个观察 ID 本身不证明正负对照、身份有效性或单变量设计；需结合实际实验记录核对。"},
            {"code": "business_outcome_not_established",
             "detail": "字段差异不自动证明权限违反、业务操作成功或修复；需适用规则及实际业务结果。"}]
    for side, raw in (("left", a), ("right", b)):
        missing = [key for key in ("actor_ref", "environment", "session_generation")
                   if key not in raw or raw[key] is None or raw[key] == ""]
        if missing:
            gaps.append({"code": "missing_context", "side": side, "fields": missing})
        missing_http = [path for path in ("request", "response.status", "response.body")
                        if _lookup(raw, path) is _MISSING]
        if missing_http:
            gaps.append({"code": "missing_http_observation", "side": side, "fields": missing_http})
    if not selected:
        gaps.append({"code": "business_fields_not_selected",
                     "detail": "尚未选择用于判别业务结果的实际字段。"})
    for entry in result["selected_fields"]:
        missing = [side for side in ("left", "right") if not entry[side]["present"]]
        if missing:
            gaps.append({"code": "selected_field_missing", "path": entry["path"], "sides": missing})
    result["gaps"] = gaps
    result["notes"] = [
        "这是只读差异视图，不设置漏洞、反证或修复结论。HTTP 状态码、长度及单次耗时差异均不足以判定。",
        "缺字段与 JSON null 区分；字段未记录时不推断身份、租户或业务语义。",
    ]
    if body_equal:
        result["notes"].append("两侧已记录的 body 内容相同；仍需核对观察器和对照有效性。")
    return result
