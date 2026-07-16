#!/usr/bin/env python3
"""Static consistency checks for the security-hunt Claude Code Skill.

The validator uses only the Python standard library so it can run on a clean
Python 3 installation. It reports all discovered errors in one pass.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALLOWED_STATUSES = {
    "candidate",
    "testing",
    "unrated",
    "impact_testing",
    "confirmed",
    "not_reproduced",
    "blocked",
}

STALE_PHRASES = {
    "the corresponding trust boundary is crossed",
    "security controls and the final execution point disagree",
    "a controllable input or business object from the report",
    "combined with a host/origin/reverse-proxy trust-boundary mismatch",
}

TITLE_NOISE = (
    re.compile(r"\bMedium\s+Open\b", re.I),
    re.compile(r"\bMedium\s+Won't\s+Fix\b", re.I),
    re.compile(r"Miscon\s+guration", re.I),
)


@dataclass(frozen=True)
class Profile:
    path: Path
    name: str
    profile_id: str
    group: str
    reference: str
    combinations: tuple[str, ...]


def error(errors: list[str], path: Path | str, message: str) -> None:
    errors.append(f"{path}: {message}")


def frontmatter(path: Path, errors: list[str]) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        error(errors, path.relative_to(ROOT), "missing opening frontmatter delimiter")
        return {}

    try:
        end = lines.index("---", 1)
    except ValueError:
        error(errors, path.relative_to(ROOT), "missing closing frontmatter delimiter")
        return {}

    data: dict[str, str] = {}
    current_key: str | None = None
    for raw in lines[1:end]:
        if re.match(r"^[A-Za-z0-9_-]+:\s*", raw):
            key, value = raw.split(":", 1)
            current_key = key.strip()
            data[current_key] = value.strip()
        elif raw.startswith("  ") and current_key:
            data[current_key] = (data[current_key] + " " + raw.strip()).strip()
        elif raw.strip():
            error(errors, path.relative_to(ROOT), f"unrecognized frontmatter line: {raw!r}")
    return data


def markdown_fences(path: Path, errors: list[str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    fence = None
    start = 0
    for number, line in enumerate(lines, 1):
        match = re.match(r"^\s*(```+|~~~+)", line)
        if not match:
            continue
        token = match.group(1)
        if fence is None:
            fence = token[0]
            start = number
        elif token[0] == fence:
            fence = None
    if fence is not None:
        error(errors, path.relative_to(ROOT), f"unclosed Markdown fence opened near line {start}")


def section_bullets(text: str, heading: str) -> tuple[str, ...]:
    marker = f"## {heading}"
    if marker not in text:
        return ()
    tail = text.split(marker, 1)[1]
    tail = re.split(r"\n##\s+", tail, maxsplit=1)[0]
    return tuple(re.findall(r"^- `([^`]+)`:", tail, flags=re.M))


def load_profiles(errors: list[str]) -> dict[str, Profile]:
    profiles: dict[str, Profile] = {}
    ids: dict[str, Path] = {}

    for path in sorted((ROOT / "profiles").glob("*.md")):
        meta = frontmatter(path, errors)
        missing = [key for key in ("id", "group", "reference") if not meta.get(key)]
        if missing:
            error(errors, path.relative_to(ROOT), f"missing frontmatter key(s): {', '.join(missing)}")
            continue

        name = path.stem
        profile_id = meta["id"]
        group = meta["group"]
        reference = meta["reference"]
        text = path.read_text(encoding="utf-8")
        combinations = section_bullets(text, "Combination Paths")

        if profile_id in ids:
            error(errors, path.relative_to(ROOT), f"duplicate id {profile_id!r}; first used by {ids[profile_id].relative_to(ROOT)}")
        ids[profile_id] = path

        ref_path = (path.parent / reference).resolve()
        try:
            ref_path.relative_to(ROOT)
        except ValueError:
            error(errors, path.relative_to(ROOT), f"reference escapes Skill root: {reference}")
        if not ref_path.is_file():
            error(errors, path.relative_to(ROOT), f"reference does not exist: {reference}")

        profiles[name] = Profile(path, name, profile_id, group, reference, combinations)

    return profiles


def validate_skill_frontmatter(errors: list[str]) -> None:
    path = ROOT / "SKILL.md"
    meta = frontmatter(path, errors)
    for key in ("name", "description", "allowed-tools"):
        if not meta.get(key):
            error(errors, path.relative_to(ROOT), f"missing required key {key!r}")
    if meta.get("name") != "security-hunt":
        error(errors, path.relative_to(ROOT), "name must be 'security-hunt'")
    if "$ARGUMENTS" not in path.read_text(encoding="utf-8"):
        error(errors, path.relative_to(ROOT), "missing $ARGUMENTS placeholder")


def validate_module_routes(profiles: dict[str, Profile], errors: list[str]) -> None:
    routed: dict[str, Path] = {}
    for module in sorted((ROOT / "modules").glob("*.md")):
        text = module.read_text(encoding="utf-8")
        names = re.findall(r"^\|[^\n]*\| `([^`]+)` \|[^\n]*\|$", text, flags=re.M)
        if not names:
            error(errors, module.relative_to(ROOT), "no Profile routes found")
        for name in names:
            if name not in profiles:
                error(errors, module.relative_to(ROOT), f"route points to missing Profile {name!r}")
                continue
            if name in routed:
                error(errors, module.relative_to(ROOT), f"Profile {name!r} is also routed by {routed[name].relative_to(ROOT)}")
            routed[name] = module
            if profiles[name].group != module.stem:
                error(
                    errors,
                    module.relative_to(ROOT),
                    f"Profile {name!r} has group {profiles[name].group!r}, expected {module.stem!r}",
                )

    for name, profile in profiles.items():
        if name not in routed:
            error(errors, profile.path.relative_to(ROOT), "Profile is not present in any module routing table")


def validate_combinations(profiles: dict[str, Profile], errors: list[str]) -> None:
    for profile in profiles.values():
        if not profile.combinations:
            error(errors, profile.path.relative_to(ROOT), "missing or empty Combination Paths section")
        for target in profile.combinations:
            if target not in profiles:
                error(errors, profile.path.relative_to(ROOT), f"combination path points to missing Profile {target!r}")


def validate_reference_coverage(profiles: dict[str, Profile], errors: list[str]) -> None:
    referenced = {(profile.path.parent / profile.reference).resolve() for profile in profiles.values()}
    actual = set((ROOT / "references").glob("*.md"))

    for path in sorted(actual - referenced):
        error(errors, path.relative_to(ROOT), "Reference is not linked by any Profile")

    for path in sorted(referenced - actual):
        error(errors, path.relative_to(ROOT), "linked Reference is missing")

    for path in sorted(actual):
        lines = path.read_text(encoding="utf-8").splitlines()
        headings = [i for i, line in enumerate(lines) if line.startswith("### ")]
        for index, start in enumerate(headings):
            end = headings[index + 1] if index + 1 < len(headings) else len(lines)
            block = "\n".join(lines[start:end])
            if "- Source:" not in block and "- Source URL:" not in block:
                error(errors, path.relative_to(ROOT), f"case at line {start + 1} has no Source or Source URL field")


def validate_text(errors: list[str]) -> None:
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in {".md", ".yaml", ".json"}:
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)

        if re.search(r"status:\s*not_vulnerable\b", text):
            error(errors, rel, "uses deprecated status 'not_vulnerable'")
        if "severity_status:" in text:
            error(errors, rel, "contains deprecated severity_status field")

        lower = text.lower()
        for phrase in STALE_PHRASES:
            if phrase in lower:
                error(errors, rel, f"contains stale template phrase: {phrase!r}")

        for pattern in TITLE_NOISE:
            if pattern.search(text):
                error(errors, rel, f"contains unclean title text matching {pattern.pattern!r}")

        for number, line in enumerate(text.splitlines(), 1):
            if len(line) > 400:
                error(errors, rel, f"line {number} is {len(line)} characters; split it for model readability")

        if path.suffix == ".md":
            markdown_fences(path, errors)


def validate_status_model(errors: list[str]) -> None:
    framework = (ROOT / "framework" / "verify-evidence.md").read_text(encoding="utf-8")
    for status in sorted(ALLOWED_STATUSES):
        if f"`{status}`" not in framework:
            error(errors, "framework/verify-evidence.md", f"status {status!r} is not documented")

    template = (ROOT / "framework" / "blackboard-template.yaml").read_text(encoding="utf-8")
    if "gate: prohibited" not in template:
        error(errors, "framework/blackboard-template.yaml", "severity gate must default to prohibited")
    if "evidence_dir:" not in template:
        error(errors, "framework/blackboard-template.yaml", "missing evidence_dir field")


def validate_readme_count(profiles: dict[str, Profile], errors: list[str]) -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"across\s+(\d+)\s+modules\s+and\s+(\d+)\s+Profiles", text)
    if not match:
        error(errors, "README.md", "missing module/Profile count statement")
        return
    module_count, profile_count = map(int, match.groups())
    actual_modules = len(list((ROOT / "modules").glob("*.md")))
    if module_count != actual_modules or profile_count != len(profiles):
        error(
            errors,
            "README.md",
            f"count says {module_count} modules/{profile_count} Profiles; actual is {actual_modules}/{len(profiles)}",
        )


def validate_evals(profiles: dict[str, Profile], errors: list[str]) -> None:
    path = ROOT / "evals" / "evals.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        error(errors, path.relative_to(ROOT), f"cannot read valid JSON: {exc}")
        return

    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        error(errors, path.relative_to(ROOT), "must contain a non-empty 'cases' array")
        return

    seen: set[str] = set()
    for index, case in enumerate(cases, 1):
        if not isinstance(case, dict):
            error(errors, path.relative_to(ROOT), f"case {index} is not an object")
            continue
        case_id = case.get("id")
        profile = case.get("expected_profile")
        module = case.get("expected_module")
        prompt = case.get("prompt")
        if not all(isinstance(value, str) and value.strip() for value in (case_id, profile, module, prompt)):
            error(errors, path.relative_to(ROOT), f"case {index} is missing id, prompt, expected_module, or expected_profile")
            continue
        if case_id in seen:
            error(errors, path.relative_to(ROOT), f"duplicate eval id {case_id!r}")
        seen.add(case_id)
        if profile not in profiles:
            error(errors, path.relative_to(ROOT), f"case {case_id!r} points to missing Profile {profile!r}")
        elif profiles[profile].group != module:
            error(
                errors,
                path.relative_to(ROOT),
                f"case {case_id!r} expects module {module!r}, but Profile group is {profiles[profile].group!r}",
            )


def main() -> int:
    errors: list[str] = []

    validate_skill_frontmatter(errors)
    profiles = load_profiles(errors)
    validate_module_routes(profiles, errors)
    validate_combinations(profiles, errors)
    validate_reference_coverage(profiles, errors)
    validate_text(errors)
    validate_status_model(errors)
    validate_readme_count(profiles, errors)
    validate_evals(profiles, errors)

    if errors:
        print(f"FAIL: {len(errors)} issue(s) found")
        for item in errors:
            print(f"- {item}")
        return 1

    print(
        "PASS: "
        f"{len(list((ROOT / 'modules').glob('*.md')))} modules, "
        f"{len(profiles)} Profiles, "
        f"{len(list((ROOT / 'references').glob('*.md')))} References, "
        "routes and structural checks are consistent."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
