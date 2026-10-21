"""Lossless UTF-16 evidence representation for Unicode-only JSON transports."""

import json
import re


_SURROGATES = re.compile(r"[\ud800-\udfff]")


def escape_utf16(value: dict) -> dict:
    """Copy a result and mark surrogate-bearing strings as JSON string literals.

    Call only after hashing and pagination. RFC 6901 paths identify the values
    a consumer must JSON-decode to recover the original UTF-16 code units.
    """
    if not isinstance(value, dict):
        raise TypeError("Evidence result must be an object")
    if "utf16_escapes" in value:
        raise ValueError("utf16_escapes is reserved for transport metadata")
    paths = []

    def copy(item, path):
        if isinstance(item, str):
            if _SURROGATES.search(item):
                paths.append(path)
                return json.dumps(item, ensure_ascii=True)
            return item
        if isinstance(item, dict):
            result = {}
            for key, child in item.items():
                if not isinstance(key, str) or _SURROGATES.search(key):
                    raise ValueError("Evidence keys must be Unicode strings without surrogates")
                pointer = key.replace("~", "~0").replace("/", "~1")
                result[key] = copy(child, path + "/" + pointer)
            return result
        if isinstance(item, list):
            return [copy(child, path + "/" + str(index)) for index, child in enumerate(item)]
        return item

    result = copy(value, "")
    if paths:
        result["utf16_escapes"] = {"encoding": "json_string_literal", "paths": paths}
    return result
