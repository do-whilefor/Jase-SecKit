#!/usr/bin/env python3
"""Read-only, offline evidence registration for src-report (Python 3.10+)."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
from typing import Iterable


IGNORED_NAMES = frozenset({".git", "__pycache__"})
MIME_OVERRIDES = {
    ".md": "text/markdown", ".txt": "text/plain", ".http": "message/http",
    ".har": "application/json", ".json": "application/json",
    ".yaml": "application/yaml", ".yml": "application/yaml",
    ".log": "text/plain", ".pcap": "application/vnd.tcpdump.pcap",
    ".pcapng": "application/x-pcapng",
}
CODE_SUFFIXES = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".h", ".cpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".sh", ".ps1", ".bat", ".cmd",
    ".sql", ".html", ".htm", ".xml", ".css",
})
ARCHIVE_SUFFIXES = frozenset({".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar"})


def _is_link_or_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _absolute_path(value: str | os.PathLike[str]) -> Path:
    """Use the normalized path thereafter, so '..' cannot change later checks."""
    return Path(os.path.abspath(os.fspath(value)))


def _check_path_components(path: Path, *, allow_missing: bool = False) -> None:
    """Do not resolve through symbolic links or Windows reparse points."""
    for component in reversed((path, *path.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if allow_missing:
                continue
            raise ValueError(f"Path does not exist: {component}") from None
        if _is_link_or_reparse(info):
            raise ValueError(f"Symbolic link/reparse point is not allowed: {component}")


def _material_root(value: str | os.PathLike[str]) -> Path:
    root = _absolute_path(value)
    _check_path_components(root)
    if not root.is_dir():
        raise ValueError(f"Materials root is not a directory: {root}")
    return root.resolve(strict=True)


def _normalize_excludes(excludes: Iterable[str] | None) -> set[str]:
    result: set[str] = set()
    for value in excludes or ():
        # CLI paths are relative; accept either path separator on every platform.
        text = os.fspath(value).replace("\\", "/")
        candidate = PurePosixPath(text)
        if (not text or candidate.is_absolute() or ":" in text
                or ".." in candidate.parts or str(candidate) == "."):
            raise ValueError(f"Exclude must be a nonempty relative path without '..': {value}")
        result.add(candidate.as_posix().rstrip("/"))
    return result


def _excluded(relative: str, excludes: set[str]) -> bool:
    if any(part in IGNORED_NAMES for part in PurePosixPath(relative).parts):
        return True
    # Compare exclusions like the host filesystem (case-insensitive on Windows).
    normalized = os.path.normcase(relative)
    return any(
        normalized == os.path.normcase(item)
        or normalized.startswith(os.path.normcase(item + "/"))
        for item in excludes
    )


def _classify(path: str) -> tuple[str, str]:
    """Filename/MIME labels are hints only, never claims about file contents."""
    suffix = PurePosixPath(path).suffix.lower()
    mime = MIME_OVERRIDES.get(suffix) or mimetypes.guess_type(path)[0] or "application/octet-stream"
    if suffix in ARCHIVE_SUFFIXES:
        return "archive", mime
    if suffix in {".http", ".har", ".pcap", ".pcapng"}:
        return "http", mime
    if suffix in CODE_SUFFIXES:
        return "code", mime
    if suffix in {".md", ".txt", ".log"}:
        return "note", mime
    if suffix in {".json", ".yaml", ".yml", ".csv", ".tsv"}:
        return "data", mime
    for kind in ("image", "audio", "video"):
        if mime.startswith(kind + "/"):
            return kind, mime
    if suffix in {".pdf", ".doc", ".docx", ".odt", ".rtf"}:
        return "document", mime
    if mime.startswith("text/"):
        return "note", mime
    return "binary", mime


def _fingerprint(info: os.stat_result) -> tuple[int, int, int, int, int]:
    # Windows lstat/fstat may expose different ctime semantics after renames.
    # Identity, byte count, and modification time remain comparable there.
    change_time = info.st_ctime_ns if os.name != "nt" else 0
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, change_time


def _hash_file(path: Path, before: os.stat_result) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _fingerprint(before) != _fingerprint(opened):
            raise OSError("File changed or was replaced before reading")
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            while block := handle.read(1024 * 1024):
                size += len(block)
                digest.update(block)
            after = os.fstat(handle.fileno())
        current = path.lstat()
        if (_is_link_or_reparse(current) or _fingerprint(opened) != _fingerprint(after)
                or _fingerprint(after) != _fingerprint(current) or size != after.st_size):
            raise OSError("File changed or was replaced while reading; retry with stable inputs")
        return digest.hexdigest(), size
    finally:
        if descriptor != -1:
            os.close(descriptor)


def index_materials(
    root: str | os.PathLike[str], excludes: Iterable[str] | None = None
) -> dict:
    """Register original bytes without executing, unpacking, or modifying them.

    IDs derive from content, not names. Duplicate paths are retained. Unreadable
    or unsupported entries are recorded in warnings instead of disappearing.
    Call with inputs that are not concurrently edited or moved.
    """
    material_root = _material_root(root)
    excluded = _normalize_excludes(excludes)
    by_hash: dict[str, dict] = {}
    warnings: list[dict[str, str]] = []

    def warn(relative: str, reason: str) -> None:
        warnings.append({"path": relative, "reason": reason})

    def visit(directory: Path) -> None:
        relative_directory = directory.relative_to(material_root).as_posix()
        try:
            _check_path_components(directory)
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except (OSError, ValueError) as exc:
            warn(relative_directory, f"Cannot enumerate directory: {exc}")
            return
        for entry in entries:
            path = directory / entry.name
            relative = path.relative_to(material_root).as_posix()
            if _excluded(relative, excluded):
                continue
            try:
                info = path.lstat()
                if _is_link_or_reparse(info):
                    warn(relative, "Skipped symbolic link/reparse point/junction; target not read")
                elif stat.S_ISDIR(info.st_mode):
                    visit(path)
                elif stat.S_ISREG(info.st_mode):
                    _check_path_components(path)
                    digest, size = _hash_file(path, info)
                    if digest not in by_hash:
                        by_hash[digest] = {"sha256": digest, "size_bytes": size, "paths": []}
                    by_hash[digest]["paths"].append(relative)
                else:
                    warn(relative, "Skipped non-regular file; contents not read")
            except (OSError, ValueError) as exc:
                warn(relative, f"Cannot read file or directory: {exc}")

    visit(material_root)
    digests = sorted(by_hash)
    prefixes = [digest[:16] for digest in digests]
    use_full_hash = len(prefixes) != len(set(prefixes))
    materials = []
    for digest in digests:
        record = by_hash[digest]
        paths = sorted(record["paths"])
        kind, mime = _classify(paths[0])
        materials.append({
            "evidence_id": "E-" + (digest if use_full_hash else digest[:16]),
            "sha256": digest, "size_bytes": record["size_bytes"],
            "kind": kind, "mime_type": mime, "paths": paths,
        })
    if not materials:
        warn(".", "No readable eligible regular files were found; manifest is empty")
    return {
        "schema_version": "1.0", "materials_root": str(material_root),
        "materials": materials,
        "warnings": sorted(warnings, key=lambda item: (item["path"], item["reason"])),
    }


def _output_path(value: str | os.PathLike[str], root: Path) -> Path:
    output = _absolute_path(value)
    _check_path_components(output, allow_missing=True)
    canonical = output.resolve(strict=False)
    # relative_to handles path component boundaries, unlike string prefixes.
    try:
        canonical.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("Output must be outside the materials root; originals are read-only")
    if canonical.exists() and not canonical.is_file():
        raise ValueError(f"Output is not a regular file: {canonical}")
    return canonical


def write_manifest(manifest: dict, output: str | os.PathLike[str]) -> Path:
    """Atomically create/update an external manifest; never overwrite originals."""
    root = _material_root(manifest["materials_root"])
    destination = _output_path(output, root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = _output_path(destination, root)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", prefix=".manifest-",
            suffix=".tmp", dir=destination.parent, delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # Recheck before replacement to catch an output swapped for a link.
        _output_path(destination, root)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("materials_dir", help="Read-only source materials directory")
    parser.add_argument("--output", required=True, help="Manifest path outside the materials directory")
    parser.add_argument("--exclude", action="append", default=[], metavar="RELPATH",
                        help="Exclude a relative file or subtree (repeatable; no glob patterns)")
    args = parser.parse_args(argv)
    try:
        root = _material_root(args.materials_dir)
        output = _output_path(args.output, root)  # Reject unsafe output before reading materials.
        manifest = index_materials(root, args.exclude)
        destination = write_manifest(manifest, output)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Registered {len(manifest['materials'])} unique material(s): {destination}")
    for warning in manifest["warnings"]:
        print(f"warning: {warning['path']}: {warning['reason']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
