"""Recoverable multi-file publication without changing the session layout.

Only authoritative files enter the journal. Derived caches may be rebuilt after
commit. The OS lock expires with the process; retained backups make rollback
repeatable even when recovery itself is interrupted.
"""

from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading

from evidence_io import BUFFER_BYTES, FileCopy, scan


DIRECTORY = ".publication"
_owners = threading.local()


def _owned(root):
    return str(root) in getattr(_owners, "roots", ())


def _directory(root):
    path = root / DIRECTORY
    if path.is_symlink() or path.resolve() != path:
        raise ValueError("publication directory must stay inside the session")
    return path


def _target(root, relative):
    if (not isinstance(relative, str) or relative not in {
            "state.json", "manifest.json", "wiki/manifest.json", "wiki/index.md"}
            and not re.fullmatch(r"(?:wiki/pages/[\w][\w.-]*\.md|evidence/[\w][\w.-]*\.(?:jsonl|source))", relative)):
        raise ValueError("invalid publication target")
    target = root / relative
    if target.resolve() != target or not target.is_relative_to(root):
        raise ValueError("publication target cannot follow a symlink")
    return target


def _sync_directory(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _write(path, data):
    with path.open("wb") as stream:
        if isinstance(data, FileCopy):
            data.write_to(stream)
            checksum = data.metadata["sha256"]
        else:
            stream.write(data)
            checksum = hashlib.sha256(data).hexdigest()
        stream.flush()
        os.fsync(stream.fileno())
    return checksum


def _copy(source, target):
    checksum = hashlib.sha256()
    with source.open("rb") as incoming, target.open("wb") as outgoing:
        for data in iter(lambda: incoming.read(BUFFER_BYTES), b""):
            checksum.update(data)
            outgoing.write(data)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    return checksum.hexdigest()


def _marker(folder, name, value):
    temporary = folder / (name + ".tmp")
    _write(temporary, json.dumps(value, ensure_ascii=False).encode("utf-8"))
    os.replace(temporary, folder / name)
    _sync_directory(folder)


@contextmanager
def _lock(root):
    path = root / ".publication.lock"
    if path.is_symlink() or path.resolve() != path:
        raise ValueError("publication lock cannot follow a symlink")
    with path.open("a+b") as stream:
        if not path.stat().st_size:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise ValueError("publication in progress; retry after the writer finishes") from exc
            raise
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _cleanup(root):
    folder = _directory(root)
    if folder.exists():
        # Resolve and check the fixed session-local target before recursive removal.
        if folder.parent != root or not folder.resolve().is_relative_to(root):
            raise ValueError("invalid publication cleanup directory")
        # Call only before installation or after a terminal marker. Retire the
        # journal first so interrupted recursive cleanup can never undo a commit.
        (folder / "journal.json").unlink(missing_ok=True)
        _sync_directory(folder)
        shutil.rmtree(folder)
        _sync_directory(root)


def _journal(root, run_id):
    folder = _directory(root)
    value = json.loads((folder / "journal.json").read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or value.get("version") != 1
            or value.get("run_id") != run_id or not isinstance(value.get("files"), list)):
        raise ValueError("invalid publication journal or run_id")
    seen = set()
    for row in value["files"]:
        if not isinstance(row, dict) or not {"path", "before", "after"} <= row.keys():
            raise ValueError("invalid publication journal entry")
        path = row.get("path")
        _target(root, path)
        if (path in seen or not isinstance(row["after"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["after"])):
            raise ValueError("invalid publication journal entry")
        if row.get("before") is not None and (not isinstance(row["before"], str)
                                              or not re.fullmatch(r"[0-9a-f]{64}", row["before"])):
            raise ValueError("invalid publication backup signature")
        seen.add(path)
    return value


def _terminal(folder, run_id=None):
    terminal = None
    for name in ("committed", "rolled_back"):
        try:
            value = json.loads((folder / name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        if (not isinstance(value, dict) or not isinstance(value.get("run_id"), str)
                or not value["run_id"] or run_id is not None and value["run_id"] != run_id
                or terminal is not None):
            raise ValueError("invalid publication terminal marker")
        terminal = name
    return terminal


def _recover_locked(root, run_id):
    folder = _directory(root)
    if not folder.exists():
        return
    if not (folder / "journal.json").exists():
        try:
            _cleanup(root)  # Staging or terminal cleanup; no pending installation.
        except OSError:
            pass
        return
    journal = _journal(root, run_id)
    if _terminal(folder, run_id) is None:
        for index, row in enumerate(journal["files"]):
            target = _target(root, row["path"])
            present = scan(target)["sha256"] if target.exists() else None
            if present not in {row.get("before"), row["after"]}:
                raise ValueError("publication target changed outside the transaction: " + row["path"])
            if present == row.get("before"):
                continue
            if row.get("before") is None:
                target.unlink()
            else:
                temporary = folder / "restore.tmp"
                if _copy(folder / f"{index}.old", temporary) != row["before"]:
                    raise ValueError("publication backup hash mismatch")
                os.replace(temporary, target)
            _sync_directory(target.parent)
        _marker(folder, "rolled_back", {"run_id": run_id})
    # A cleanup failure must not turn a committed batch into an apparent failure.
    try:
        _cleanup(root)
    except OSError:
        pass


def recover(root, run_id):
    """Recover an abandoned batch, but never roll back another active writer."""
    root = Path(root).resolve(strict=True)
    if _owned(root) or not _directory(root).exists():
        return
    with _lock(root):
        _recover_locked(root, run_id)


@contextmanager
def reader(root, run_id):
    """Protect a short direct read that has no later snapshot verification."""
    root = Path(root).resolve(strict=True)
    with _lock(root):
        _recover_locked(root, run_id)
        yield


def pending(root):
    root = Path(root)
    if _owned(root):
        return False
    folder = _directory(root)
    if not (folder / "journal.json").exists():
        return False
    try:
        return _terminal(folder) is None
    except (OSError, ValueError):
        return True


@contextmanager
def writer(root, run_id):
    root = Path(root).resolve(strict=True)
    if _owned(root):
        raise ValueError("nested publication is not supported")
    with _lock(root):
        roots = getattr(_owners, "roots", set())
        _owners.roots = roots
        roots.add(str(root))
        try:
            _recover_locked(root, run_id)
            if _directory(root).exists():
                raise ValueError("previous publication cleanup is incomplete")
            yield
        finally:
            roots.remove(str(root))


def install(root, run_id, files, immutable, *, stable):
    """Install a validated batch and return any warnings after its commit point."""
    root = Path(root).resolve(strict=True)
    if not _owned(root):
        raise ValueError("publication requires the writer lock")
    folder = _directory(root)
    folder.mkdir()
    rows = []
    warnings = []
    try:
        for index, (relative, data) in enumerate(files.items()):
            target = _target(root, relative)
            if relative in immutable and target.exists():
                raise ValueError("refusing to replace immutable evidence " + relative)
            before = _copy(target, folder / f"{index}.old") if target.exists() else None
            after = _write(folder / f"{index}.new", data)
            rows.append({"path": relative, "before": before, "after": after})
        if not stable():
            raise ValueError("session changed while preparing publication")
        _marker(folder, "journal.json", {"version": 1, "run_id": run_id, "files": rows})
        _sync_directory(root)
        for index, row in enumerate(rows):
            target = _target(root, row["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            if row["before"] is None:
                # Link a complete staged file without overwriting an existing file.
                os.link(folder / f"{index}.new", target)
            else:
                os.replace(folder / f"{index}.new", target)
            _sync_directory(target.parent)
        _marker(folder, "committed", {"run_id": run_id})
    except BaseException as exc:
        if _terminal(folder, run_id) != "committed" or not isinstance(exc, Exception):
            _recover_locked(root, run_id)
            raise
        # The marker replacement is the commit point, even if its subsequent
        # directory flush fails. Never invite a retry of immutable observations.
        warnings.append({"code": "publication_durability_uncertain", "detail": str(exc)})
    try:
        _cleanup(root)
    except OSError as exc:
        warnings.append({"code": "publication_cleanup_pending", "detail": str(exc)})
    return warnings
