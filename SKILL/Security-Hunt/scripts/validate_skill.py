#!/usr/bin/env python3
"""Validate the security-hunt Claude Code Skill as one consistency graph.

The validator uses only the Python standard library. It checks syntax,
cross-file identity, routing fixtures, state vocabulary, terminal-result gates,
and structural consistency, then reports all safely checkable issues in one pass.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

FINDING_STATUSES = {"lead", "technical_hit", "impact_verified", "closed"}
RATINGS = {"unrated", "info", "P3", "P2", "P1"}
TERMINAL_RESULTS = {
    "VULN_FOUND",
    "NOT_REPRODUCED",
    "LOW_ROI",
    "NEED_INPUT",
}
TERMINAL_STATES = {
    "VULN_FOUND": {"impact_verified"},
    "NOT_REPRODUCED": {"closed"},
    "LOW_ROI": {"impact_verified"},
    "NEED_INPUT": {"lead", "technical_hit"},
}
TERMINAL_RATINGS = {
    "VULN_FOUND": {"P1", "P2", "P3"},
    "NOT_REPRODUCED": {"unrated"},
    "LOW_ROI": {"info"},
    "NEED_INPUT": {"unrated"},
}
TERMINAL_PRECEDENCE = [
    "VULN_FOUND",
    "NEED_INPUT",
    "LOW_ROI",
    "NOT_REPRODUCED",
]
REQUIRED_PROFILE_SECTIONS = (
    "Baseline",
    "Validation Order",
    "Variant Axes",
    "Combination Paths",
)
STALE_PHRASES = {
    "reported focus",
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
FRONTMATTER_KEY = re.compile(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$")
PROFILE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SAFE_PREAPPROVED_TOOLS = ("Read", "Grep", "Glob")
REQUIRED_FILES = (
    "SKILL.md",
    "README.md",
    "framework/verify-evidence.md",
    "framework/blackboard-template.yaml",
    "evals/evals.json",
)
REQUIRED_DIRECTORIES = ("modules", "profiles", "references", "framework", "evals")


@dataclass(frozen=True)
class Profile:
    path: Path
    name: str
    title: str
    profile_id: str
    group: str
    reference: str
    combinations: tuple[str, ...]


def relative(path: Path) -> str:
    """Return a stable Skill-relative path for diagnostics."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def error(errors: list[str], path: Path | str, message: str) -> None:
    label = relative(path) if isinstance(path, Path) else path
    errors.append(f"{label}: {message}")


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def frontmatter(path: Path, errors: list[str]) -> dict[str, str]:
    """Parse the small YAML subset used by this Skill's frontmatter."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        error(errors, path, "missing opening frontmatter delimiter")
        return {}

    try:
        end = lines.index("---", 1)
    except ValueError:
        error(errors, path, "missing closing frontmatter delimiter")
        return {}

    data: dict[str, str] = {}
    index = 1
    while index < end:
        raw = lines[index]
        if not raw.strip():
            index += 1
            continue

        match = FRONTMATTER_KEY.match(raw)
        if not match:
            error(errors, path, f"unrecognized frontmatter line: {raw!r}")
            index += 1
            continue

        key = match.group(1)
        value = (match.group(2) or "").strip()
        if key in data:
            error(errors, path, f"duplicate frontmatter key {key!r}")

        if value in {">", ">-", "|", "|-"}:
            folded = value.startswith(">")
            block: list[str] = []
            index += 1
            while index < end:
                continuation = lines[index]
                if continuation and not continuation.startswith((" ", "\t")):
                    break
                block.append(continuation.strip())
                index += 1
            if not any(block):
                error(errors, path, f"frontmatter block scalar {key!r} is empty")
            data[key] = " ".join(part for part in block if part) if folded else "\n".join(block)
            continue

        data[key] = unquote(value)
        index += 1

    return data


def first_heading(text: str, level: int) -> str:
    match = re.search(rf"^{'#' * level}\s+(.+?)\s*$", text, flags=re.M)
    return match.group(1) if match else ""


def markdown_fences(path: Path, errors: list[str]) -> None:
    opening_char: str | None = None
    opening_length = 0
    opening_line = 0

    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if opening_char is None:
            match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
            if not match:
                continue
            token = match.group(1)
            opening_char = token[0]
            opening_length = len(token)
            opening_line = number
            continue

        closing = re.match(
            rf"^ {{0,3}}({re.escape(opening_char)}{{{opening_length},}})[ ]*$",
            line,
        )
        if closing:
            opening_char = None
            opening_length = 0

    if opening_char is not None:
        error(errors, path, f"unclosed Markdown fence opened near line {opening_line}")


def section_bullets(text: str, heading: str) -> tuple[str, ...]:
    marker = f"## {heading}"
    if marker not in text:
        return ()
    tail = text.split(marker, 1)[1]
    tail = re.split(r"\n##\s+", tail, maxsplit=1)[0]
    return tuple(re.findall(r"^- `([^`]+)`:", tail, flags=re.M))


def has_bulleted_field(block: str, field: str) -> bool:
    """Return whether a case field has an immediate non-empty list item."""
    pattern = rf"^- {re.escape(field)}:\s*$\n  - \S"
    return re.search(pattern, block, flags=re.M) is not None


def load_profiles(errors: list[str]) -> dict[str, Profile]:
    profiles: dict[str, Profile] = {}
    ids: dict[str, Path] = {}

    for path in sorted((ROOT / "profiles").glob("*.md")):
        meta = frontmatter(path, errors)
        missing = [key for key in ("id", "group", "reference") if not meta.get(key)]
        if missing:
            error(errors, path, f"missing frontmatter key(s): {', '.join(missing)}")
            continue

        text = path.read_text(encoding="utf-8")
        name = path.stem
        title = first_heading(text, 1)
        profile_id = meta["id"]
        group = meta["group"]
        reference = meta["reference"]
        combinations = section_bullets(text, "Combination Paths")

        if not title:
            error(errors, path, "missing level-one title")
        if not PROFILE_ID.fullmatch(profile_id):
            error(errors, path, f"invalid Profile id {profile_id!r}")
        if profile_id in ids:
            error(errors, path, f"duplicate id {profile_id!r}; first used by {relative(ids[profile_id])}")
        ids[profile_id] = path

        expected_reference = f"../references/{name}.md"
        if reference != expected_reference:
            error(errors, path, f"reference must be {expected_reference!r}, found {reference!r}")

        ref_path = (path.parent / reference).resolve()
        try:
            ref_path.relative_to(ROOT)
        except ValueError:
            error(errors, path, f"reference escapes Skill root: {reference}")
        if not ref_path.is_file():
            error(errors, path, f"reference does not exist: {reference}")

        headings = set(re.findall(r"^##\s+(.+?)\s*$", text, flags=re.M))
        for heading in REQUIRED_PROFILE_SECTIONS:
            if heading not in headings:
                error(errors, path, f"missing required section {heading!r}")
        if "**Use for:**" not in text:
            error(errors, path, "missing '**Use for:**' routing trigger")
        if "**Misalignment to find:**" not in text:
            error(errors, path, "missing '**Misalignment to find:**' boundary statement")
        if len(combinations) != len(set(combinations)):
            error(errors, path, "Combination Paths contains duplicate targets")

        profiles[name] = Profile(
            path=path,
            name=name,
            title=title,
            profile_id=profile_id,
            group=group,
            reference=reference,
            combinations=combinations,
        )

    return profiles


def validate_skill_frontmatter(errors: list[str]) -> None:
    path = ROOT / "SKILL.md"
    meta = frontmatter(path, errors)
    for key in ("name", "description", "argument-hint", "allowed-tools"):
        if not meta.get(key):
            error(errors, path, f"missing required key {key!r}")
    if meta.get("name") != "security-hunt":
        error(errors, path, "name must be 'security-hunt'")
    if meta.get("disable-model-invocation") != "true":
        error(errors, path, "authorized testing workflow must require explicit invocation")
    allowed_tools = tuple(meta.get("allowed-tools", "").split())
    if allowed_tools != SAFE_PREAPPROVED_TOOLS:
        error(
            errors,
            path,
            "allowed-tools must preapprove only " + " ".join(SAFE_PREAPPROVED_TOOLS),
        )
    if meta.get("description", "").startswith((">", "|")):
        error(errors, path, "description block scalar was not parsed correctly")

    text = path.read_text(encoding="utf-8")
    if "$ARGUMENTS" not in text:
        error(errors, path, "missing $ARGUMENTS placeholder")
    if "${CLAUDE_SKILL_DIR}" not in text:
        error(errors, path, "supporting resources must use ${CLAUDE_SKILL_DIR}")


def validate_module_routes(profiles: dict[str, Profile], errors: list[str]) -> None:
    routed: dict[str, Path] = {}
    modules = sorted((ROOT / "modules").glob("*.md"))
    for module in modules:
        text = module.read_text(encoding="utf-8")
        names = re.findall(r"^\|[^\n]*\| `([^`]+)` \|[^\n]*\|$", text, flags=re.M)
        if not names:
            error(errors, module, "no Profile routes found")
        if len(names) != len(set(names)):
            error(errors, module, "routing table contains duplicate Profiles")

        for name in names:
            if name not in profiles:
                error(errors, module, f"route points to missing Profile {name!r}")
                continue
            if name in routed:
                error(errors, module, f"Profile {name!r} is also routed by {relative(routed[name])}")
            routed[name] = module
            if profiles[name].group != module.stem:
                error(
                    errors,
                    module,
                    f"Profile {name!r} has group {profiles[name].group!r}, expected {module.stem!r}",
                )

    for name, profile in profiles.items():
        if name not in routed:
            error(errors, profile.path, "Profile is not present in any module routing table")


def validate_combinations(profiles: dict[str, Profile], errors: list[str]) -> None:
    for profile in profiles.values():
        if not profile.combinations:
            error(errors, profile.path, "missing or empty Combination Paths section")
        for target in profile.combinations:
            if target == profile.name:
                error(errors, profile.path, "Combination Paths must not point to itself")
            elif target not in profiles:
                error(errors, profile.path, f"combination path points to missing Profile {target!r}")


def validate_references(profiles: dict[str, Profile], errors: list[str]) -> None:
    by_reference = {
        (profile.path.parent / profile.reference).resolve(): profile
        for profile in profiles.values()
    }
    actual = set((ROOT / "references").glob("*.md"))

    for path in sorted(actual - set(by_reference)):
        error(errors, path, "Reference is not linked by any Profile")
    for path in sorted(set(by_reference) - actual):
        error(errors, path, "linked Reference is missing")

    for path in sorted(actual):
        text = path.read_text(encoding="utf-8")
        profile = by_reference.get(path)
        if "## Use Rule" not in text:
            error(errors, path, "missing Use Rule section")
        if profile:
            expected_title = f"{profile.title} · Reference"
            if first_heading(text, 1) != expected_title:
                error(errors, path, f"title must be {expected_title!r}")

            identity = re.search(
                r"^Load after selecting the `([^`]+)` Profile and forming a current-target hypothesis\.$",
                text,
                flags=re.M,
            )
            if not identity:
                error(errors, path, "missing canonical Profile identity declaration")
            elif identity.group(1) != profile.profile_id:
                error(
                    errors,
                    path,
                    f"declares Profile id {identity.group(1)!r}; expected {profile.profile_id!r}",
                )

        lines = text.splitlines()
        headings = [index for index, line in enumerate(lines) if line.startswith("### ")]
        for position, start in enumerate(headings):
            end = headings[position + 1] if position + 1 < len(headings) else len(lines)
            block = "\n".join(lines[start:end])
            has_source = re.search(r"^- Source:\s+\S", block, flags=re.M) is not None
            has_source_url = re.search(r"^- Source URL:\s+\S", block, flags=re.M) is not None
            has_source_locator = (
                re.search(r"^- Source locator:\s+\S", block, flags=re.M) is not None
            )
            declares_reported_boundary = "- Reported boundary:" in block
            has_reported_boundary = has_bulleted_field(block, "Reported boundary")
            if not has_source and not has_source_url:
                error(errors, path, f"source block at line {start + 1} has no Source or Source URL")
            if "- Source URL:" in block and not has_source_url:
                error(errors, path, f"source block at line {start + 1} has an empty Source URL")
            if declares_reported_boundary and not has_reported_boundary:
                error(
                    errors,
                    path,
                    f"reported boundary at line {start + 1} has no non-empty list item",
                )
            if declares_reported_boundary and not has_source_url:
                error(
                    errors,
                    path,
                    f"reported boundary at line {start + 1} requires a Source URL for provenance",
                )
            if declares_reported_boundary and not has_source_locator:
                error(errors, path, f"reported boundary at line {start + 1} has no Source locator")
            if declares_reported_boundary and not has_bulleted_field(block, "Impact closure"):
                error(errors, path, f"reported boundary at line {start + 1} has no Impact closure")
            if declares_reported_boundary and "- Source topic:" in block:
                error(
                    errors,
                    path,
                    f"source block at line {start + 1} mixes Source topic and Reported boundary",
                )
            if not has_bulleted_field(block, "Transferable test ideas"):
                error(errors, path, f"source block at line {start + 1} has no Transferable test ideas")
            if not has_bulleted_field(block, "Defensive anchor"):
                error(errors, path, f"source block at line {start + 1} has no Defensive anchor")

        for source_url in re.findall(r"^- Source URL:\s*(\S+)\s*$", text, flags=re.M):
            parsed = urlparse(source_url)
            if parsed.scheme != "https" or not parsed.netloc:
                error(errors, path, f"invalid or non-HTTPS Source URL {source_url!r}")


def validate_structured_vocabulary(path: Path, text: str, errors: list[str]) -> None:
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^\s*(?:-\s+)?finding_status:\s*([A-Za-z0-9_]+)", line)
        if match and match.group(1) not in FINDING_STATUSES:
            error(errors, path, f"line {number} uses unknown finding_status {match.group(1)!r}")

        match = re.match(r"^\s*(?:-\s+)?rating:\s*([A-Za-z0-9_]+)", line)
        if match and match.group(1) not in RATINGS:
            error(errors, path, f"line {number} uses unknown rating {match.group(1)!r}")

        if re.match(r"^\s*(?:-\s+)?status:\s*", line):
            error(errors, path, f"line {number} uses legacy 'status'; use finding_status")
        if re.match(r"^\s*(?:-\s+)?severity(?:_status)?:\s*", line):
            error(errors, path, f"line {number} uses legacy severity field; use rating")


def validate_text(errors: list[str]) -> bool:
    """Validate bytes and text; return whether structural reads are safe."""
    checked_suffixes = {".md", ".yaml", ".json", ".py"}
    all_decodable = True
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in checked_suffixes:
            continue
        try:
            raw = path.read_bytes()
        except OSError as exc:
            error(errors, path, f"cannot read file: {exc}")
            all_decodable = False
            continue
        if b"\r" in raw:
            error(errors, path, "contains CR or CRLF line endings; use LF")
        if raw and not raw.endswith(b"\n"):
            error(errors, path, "missing final newline")
        elif raw.endswith(b"\n\n"):
            error(errors, path, "contains trailing blank lines")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            error(errors, path, f"invalid UTF-8 at byte {exc.start}")
            all_decodable = False
            continue

        if "\ufffd" in text:
            error(errors, path, "contains a Unicode replacement character")
        if "\t" in text:
            error(errors, path, "contains a tab; use spaces for stable rendering")

        if path.suffix != ".py":
            lower = text.lower()
            for phrase in STALE_PHRASES:
                if phrase in lower:
                    error(errors, path, f"contains stale template phrase: {phrase!r}")
            for pattern in TITLE_NOISE:
                if pattern.search(text):
                    error(errors, path, f"contains unclean title text matching {pattern.pattern!r}")

        for number, line in enumerate(text.splitlines(), 1):
            if line.rstrip() != line:
                error(errors, path, f"line {number} has trailing whitespace")
            if len(line) > 180:
                error(errors, path, f"line {number} is {len(line)} characters; split it for model readability")

        validate_structured_vocabulary(path, text, errors)
        if path.suffix == ".md":
            markdown_fences(path, errors)
        elif path.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                error(errors, path, f"invalid JSON: {exc}")

    return all_decodable


def validate_layout(errors: list[str]) -> bool:
    """Report missing core package paths before semantic parsers open them."""
    complete = True
    for relative_path in REQUIRED_FILES:
        path = ROOT / relative_path
        if not path.is_file():
            error(errors, path, "missing required file")
            complete = False
    for relative_path in REQUIRED_DIRECTORIES:
        path = ROOT / relative_path
        if not path.is_dir():
            error(errors, path, "missing required directory")
            complete = False
    return complete


def validate_python(errors: list[str]) -> None:
    for path in sorted(ROOT.rglob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            error(errors, path, f"Python syntax error at line {exc.lineno}: {exc.msg}")


def validate_state_model(errors: list[str]) -> None:
    framework_path = ROOT / "framework" / "verify-evidence.md"
    framework = framework_path.read_text(encoding="utf-8")
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    template_path = ROOT / "framework" / "blackboard-template.yaml"
    template = template_path.read_text(encoding="utf-8")

    for value in sorted(FINDING_STATUSES | RATINGS | TERMINAL_RESULTS):
        if f"`{value}`" not in framework:
            error(errors, framework_path, f"canonical value {value!r} is not documented")

    start_marker = "### 3.3 Terminal Result"
    end_marker = "## 4. Technical Evidence Gate"
    if start_marker not in framework:
        error(errors, framework_path, f"missing section {start_marker!r}")
        terminal_section = ""
    else:
        terminal_section = framework.split(start_marker, 1)[1]
    if end_marker not in terminal_section:
        error(errors, framework_path, f"missing section {end_marker!r}")
    else:
        terminal_section = terminal_section.split(end_marker, 1)[0]

    row_matches = re.findall(
        r"^\| `([A-Z_]+)` \| (.+?) \| (.+?) \| (.+?) \|$",
        terminal_section,
        flags=re.M,
    )
    rows: dict[str, tuple[str, str, str]] = {}
    for terminal, status_cell, rating_cell, gate_cell in row_matches:
        if terminal in rows:
            error(errors, framework_path, f"duplicate terminal mapping row for {terminal}")
            continue
        rows[terminal] = (status_cell, rating_cell, gate_cell)

    for terminal in sorted(TERMINAL_RESULTS):
        if terminal not in rows:
            error(errors, framework_path, f"terminal result {terminal!r} has no mapping row")
        if f"`{terminal}`" not in skill:
            error(errors, ROOT / "SKILL.md", f"terminal result {terminal!r} is missing")

    for terminal, row in rows.items():
        if terminal not in TERMINAL_RESULTS:
            error(errors, framework_path, f"unknown terminal mapping row {terminal!r}")
            continue
        status_cell, rating_cell, gate_cell = row
        states = set(re.findall(r"`([^`]+)`", status_cell))
        ratings = set(re.findall(r"`([^`]+)`", rating_cell))
        if states != TERMINAL_STATES[terminal]:
            error(
                errors,
                framework_path,
                f"{terminal} finding_status must be "
                f"{sorted(TERMINAL_STATES[terminal])}, found {sorted(states)}",
            )
        if ratings != TERMINAL_RATINGS[terminal]:
            error(
                errors,
                framework_path,
                f"{terminal} rating must be "
                f"{sorted(TERMINAL_RATINGS[terminal])}, found {sorted(ratings)}",
            )
        if not gate_cell.strip():
            error(errors, framework_path, f"{terminal} has an empty additional gate")

    precedence = re.findall(
        r"^\d+\..*?`(VULN_FOUND|NEED_INPUT|LOW_ROI|NOT_REPRODUCED)`",
        terminal_section,
        flags=re.M,
    )
    if precedence != TERMINAL_PRECEDENCE:
        error(
            errors,
            framework_path,
            "task terminal precedence must be " + " > ".join(TERMINAL_PRECEDENCE),
        )

    required_template_fragments = (
        "finding_status: lead",
        "rating: unrated",
        "impact_claims:",
        "changed_dimension:",
        "reopen_when:",
        "terminal_result: null",
    )
    for fragment in required_template_fragments:
        if fragment not in template:
            error(errors, template_path, f"missing canonical field/default {fragment!r}")
    if "state/blackboard.md" not in framework or "state/blackboard.md" not in template:
        error(errors, template_path, "canonical target path must be state/blackboard.md")


def validate_readme_count(profiles: dict[str, Profile], errors: list[str]) -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"across\s+(\d+)\s+modules\s+and\s+(\d+)\s+Profiles", text)
    if not match:
        error(errors, path, "missing module/Profile count statement")
        return

    module_count, profile_count = map(int, match.groups())
    actual_modules = len(list((ROOT / "modules").glob("*.md")))
    if module_count != actual_modules or profile_count != len(profiles):
        error(
            errors,
            path,
            f"count says {module_count} modules/{profile_count} Profiles; "
            f"actual is {actual_modules}/{len(profiles)}",
        )


def validate_evals(profiles: dict[str, Profile], errors: list[str]) -> None:
    path = ROOT / "evals" / "evals.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        error(errors, path, f"cannot read valid JSON: {exc}")
        return

    if not isinstance(payload, dict) or payload.get("schema_version") != 3:
        error(errors, path, "schema_version must be 3")

    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        error(errors, path, "must contain a non-empty 'cases' array")
        return

    seen_ids: set[str] = set()
    seen_prompts: set[str] = set()
    covered_profiles: set[str] = set()

    for index, case in enumerate(cases, 1):
        if not isinstance(case, dict):
            error(errors, path, f"case {index} is not an object")
            continue

        case_id = case.get("id")
        profile_name = case.get("expected_profile")
        module = case.get("expected_module")
        prompt = case.get("prompt")
        reason = case.get("reason")
        required = (case_id, profile_name, module, prompt, reason)
        if not all(isinstance(value, str) and value.strip() for value in required):
            error(
                errors,
                path,
                f"case {index} is missing id, prompt, reason, expected_module, or expected_profile",
            )
            continue

        if not PROFILE_ID.fullmatch(case_id):
            error(errors, path, f"case id {case_id!r} is not hyphen-case")
        if case_id in seen_ids:
            error(errors, path, f"duplicate eval id {case_id!r}")
        if prompt in seen_prompts:
            error(errors, path, f"duplicate eval prompt in case {case_id!r}")
        seen_ids.add(case_id)
        seen_prompts.add(prompt)

        profile = profiles.get(profile_name)
        if profile is None:
            error(errors, path, f"case {case_id!r} points to missing Profile {profile_name!r}")
            continue
        covered_profiles.add(profile_name)
        if profile.group != module:
            error(
                errors,
                path,
                f"case {case_id!r} expects module {module!r}, "
                f"but Profile group is {profile.group!r}",
            )

        if "expected_adjacent_profiles" in case:
            error(
                errors,
                path,
                f"case {case_id!r} uses legacy expected_adjacent_profiles; "
                "use required_adjacent_profiles only for an explicit second boundary",
            )

        adjacent = case.get("required_adjacent_profiles", [])
        if not isinstance(adjacent, list) or not all(isinstance(item, str) for item in adjacent):
            error(errors, path, f"case {case_id!r} has invalid required_adjacent_profiles")
            continue
        if len(adjacent) != len(set(adjacent)):
            error(errors, path, f"case {case_id!r} repeats an adjacent Profile")
        for name in adjacent:
            if name not in profiles:
                error(errors, path, f"case {case_id!r} points to missing adjacent Profile {name!r}")
            elif name not in profile.combinations:
                error(
                    errors,
                    path,
                    f"case {case_id!r} expects adjacent Profile {name!r}, "
                    "but it is not a Combination Path of the primary Profile",
                )

    missing_coverage = sorted(set(profiles) - covered_profiles)
    if missing_coverage:
        error(errors, path, f"Profiles without a routing fixture: {', '.join(missing_coverage)}")


def main() -> int:
    errors: list[str] = []
    profiles: dict[str, Profile] = {}

    text_is_decodable = validate_text(errors)
    layout_is_complete = validate_layout(errors)
    if text_is_decodable and layout_is_complete:
        validate_skill_frontmatter(errors)
        profiles = load_profiles(errors)
        validate_module_routes(profiles, errors)
        validate_combinations(profiles, errors)
        validate_references(profiles, errors)
        validate_python(errors)
        validate_state_model(errors)
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
        "canonical state gates, routing fixture coverage, and structural checks are consistent."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
