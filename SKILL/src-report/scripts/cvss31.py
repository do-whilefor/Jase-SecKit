#!/usr/bin/env python3
"""Calculate a supplied CVSS v3.1 Base vector without reading or executing PoCs.

Independent implementation of FIRST's specification, sections 5, 6, 7.1, 7.4
and Appendix A: https://www.first.org/cvss/v3.1/specification-document
A calculated score does not establish that the supplied metrics have evidence.
"""
from __future__ import annotations

import argparse
import json
import math


METRIC_ORDER = ("AV", "AC", "PR", "UI", "S", "C", "I", "A")
VALUES = {
    "AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2},
    "AC": {"L": 0.77, "H": 0.44},
    "PR": {"N": 0.85, "L": 0.62, "H": 0.27},
    "UI": {"N": 0.85, "R": 0.62},
    "S": {"U": None, "C": None},
    "C": {"H": 0.56, "L": 0.22, "N": 0.0},
    "I": {"H": 0.56, "L": 0.22, "N": 0.0},
    "A": {"H": 0.56, "L": 0.22, "N": 0.0},
}
CHANGED_PRIVILEGES = {"N": 0.85, "L": 0.68, "H": 0.5}


def _roundup(value: float) -> float:
    """FIRST Appendix A: nearest five decimals, then upward to one decimal."""
    integer = math.floor(value * 100000 + 0.5)
    if integer % 10000 == 0:
        return integer / 100000
    return (integer // 10000 + 1) / 10


def _severity(score: float) -> str:
    if score == 0:
        return "NONE"
    for ceiling, label in ((4, "LOW"), (7, "MEDIUM"), (9, "HIGH")):
        if score < ceiling:
            return label
    return "CRITICAL"


def _parse(vector: str) -> dict[str, str]:
    if not isinstance(vector, str) or not vector.strip():
        raise ValueError("A non-empty CVSS v3.1 Base vector is required")
    parts = [part.strip() for part in vector.strip().upper().split("/")]
    if parts[0].startswith("CVSS:"):
        if parts.pop(0) != "CVSS:3.1":
            raise ValueError("Only CVSS:3.1 Base vectors are supported")
    metrics = {}
    for part in parts:
        fields = part.split(":")
        if len(fields) != 2 or not all(fields):
            raise ValueError(f"Invalid metric {part!r}; expected KEY:VALUE")
        key, value = fields
        if key not in VALUES:
            raise ValueError(f"Unsupported Base metric {key!r}")
        if key in metrics:
            raise ValueError(f"Duplicate metric {key}")
        if value not in VALUES[key]:
            raise ValueError(f"Invalid value {value!r} for {key}")
        metrics[key] = value
    missing = [key for key in METRIC_ORDER if key not in metrics]
    if missing:
        raise ValueError("Missing Base metrics: " + ", ".join(missing))
    return {key: metrics[key] for key in METRIC_ORDER}


def calculate(vector: str) -> dict:
    """Return Base score, normalized vector, severity and calculation details.

    The prefix may be omitted on input. Case and metric order are normalized.
    Unsupported versions, non-Base metrics and malformed vectors raise ValueError.
    """
    metrics = _parse(vector)
    factors = {key: VALUES[key][value] for key, value in metrics.items() if key != "S"}
    changed = metrics["S"] == "C"
    if changed:
        factors["PR"] = CHANGED_PRIVILEGES[metrics["PR"]]
    isc_base = 1 - (1 - factors["C"]) * (1 - factors["I"]) * (1 - factors["A"])
    if changed:
        # Base uses exponent 15; Environmental's different formula is not used.
        impact = 7.52 * (isc_base - 0.029) - 3.25 * (isc_base - 0.02) ** 15
    else:
        impact = 6.42 * isc_base
    exploitability = 8.22 * factors["AV"] * factors["AC"] * factors["PR"] * factors["UI"]
    uncapped_base = (impact + exploitability) * (1.08 if changed else 1)
    base_score = 0.0 if impact <= 0 else _roundup(min(uncapped_base, 10.0))
    return {
        "version": "3.1",
        "metric_group": "Base",
        "vector": "CVSS:3.1/" + "/".join(f"{key}:{value}" for key, value in metrics.items()),
        "metrics": metrics,
        "base_score": base_score,
        "severity": _severity(base_score),
        "calculation": {
            "factors": factors,
            "isc_base": isc_base,
            "impact": impact,
            "exploitability": exploitability,
            "uncapped_base": uncapped_base,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vector", help="CVSS v3.1 Base vector; quote it as one argument")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()
    try:
        result = calculate(args.vector)
    except ValueError as error:
        parser.error(str(error))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"CVSS v3.1 Base: {result['base_score']:.1f} ({result['severity']})")
        print(result["vector"])
        details = result["calculation"]
        print(f"Impact: {details['impact']:.6f}; Exploitability: {details['exploitability']:.6f}")
        print("Calculated from supplied metrics; evidence and platform rating require review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
