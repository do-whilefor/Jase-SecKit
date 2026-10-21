"""Shared semantics for declared conditions, never inferred target state."""

UNKNOWN = frozenset({"", "unknown", "unspecified", "not_recorded", "未知", "未记录"})


def known(value):
    return isinstance(value, str) and value.strip().casefold() not in UNKNOWN


def check(supplied, required):
    conflicts, unknown = [], []
    for key in sorted(supplied.keys() | required.keys()):
        left, right = supplied.get(key), required.get(key)
        if not known(left) or not known(right):
            unknown.append({"constraint": key, "provided": left, "required": right,
                            "reason": "condition_unknown"})
        elif left != right:
            conflicts.append({"constraint": key, "provided": left, "required": right})
    if not supplied and not required:
        unknown.append({"reason": "no_constraints_declared"})
    return conflicts, unknown
