#!/usr/bin/env python3
"""Check bundled Markdown links, heading anchors, and explicit resource paths offline."""

from collections import Counter
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]


def prose_lines(text):
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match:
            marker = match[1]
            if fence is None:
                fence = marker[0], len(marker)
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            continue
        if fence is None:
            yield number, line


def anchors(path):
    counts = Counter()
    result = set()
    for _, line in prose_lines(path.read_text(encoding="utf-8")):
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            title = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", match[1])
            slug = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
            duplicate = counts[slug]
            counts[slug] += 1
            result.add(slug + (f"-{duplicate}" if duplicate else ""))
    return result


def main():
    errors = []
    checked = 0
    cache = {}
    documents = [ROOT / "SKILL.md", *sorted((ROOT / "references").glob("*.md"))]
    for document in documents:
        if not document.is_file():
            errors.append(f"Missing document: {document.relative_to(ROOT)}")
            continue
        for number, line in prose_lines(document.read_text(encoding="utf-8")):
            for match in re.finditer(r"\[[^\]\n]*\]\(([^)\n]+)\)", line):
                raw = match[1].strip().split(' "', 1)[0].strip("<>")
                target = urlsplit(raw)
                if target.scheme or target.netloc:
                    continue
                path = (document.parent / unquote(target.path)).resolve() if target.path else document
                checked += 1
                prefix = f"{document.relative_to(ROOT)}:{number}"
                if not path.is_file():
                    errors.append(f"{prefix}: missing link target {raw}")
                elif target.fragment and path.suffix == ".md":
                    if path not in cache:
                        cache[path] = anchors(path)
                    if unquote(target.fragment) not in cache[path]:
                        errors.append(f"{prefix}: missing heading {raw}")
            for match in re.finditer(r"`((?:scripts|references)/[a-z0-9-]+\.(?:md|sh|js|py))`", line):
                checked += 1
                if not (ROOT / match[1]).is_file():
                    errors.append(f"{document.relative_to(ROOT)}:{number}: missing resource {match[1]}")
    for error in errors:
        print(error)
    print(f"References: {checked} checked, {len(errors)} errors")
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
