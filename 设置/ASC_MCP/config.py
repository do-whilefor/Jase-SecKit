"""Locate a compatible ASC checkout and report adapter readiness."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


CONFIG_PATH = Path(__file__).resolve().with_name("config.json")
WORKER_PATH = Path(__file__).resolve().with_name("worker.py")


def _absolute_path(value, name):
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError(f"{name} must be an absolute path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute path")
    # Keep interpreter symlinks intact: resolving a venv's python symlink to
    # the system executable would silently discard its installed dependencies.
    return path


def resolve_settings(asc_root=None, asc_python=None):
    """Resolve explicit arguments, environment, local config, then defaults."""
    root = asc_root or os.environ.get("ASC_ROOT")
    python = asc_python or os.environ.get("ASC_PYTHON")
    saved = {}
    if (root is None or python is None) and CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot read {CONFIG_PATH}: {exc}") from exc
        if not isinstance(saved, dict):
            raise ValueError(f"{CONFIG_PATH} must contain a JSON object")
    root = _absolute_path(root or saved.get("asc_root") or CONFIG_PATH.parent.parent, "asc_root").resolve()
    python = _absolute_path(python or saved.get("asc_python") or sys.executable, "asc_python")
    if not (root / "main.py").is_file():
        raise ValueError(
            f"ASC source not found at {root} (missing main.py). "
            "Run configure.py --asc-root ABSOLUTE_ASC_PATH or pass --asc-root."
        )
    if not python.is_file():
        raise ValueError(f"Python executable does not exist: {python}")
    return root, python


def _run_check(command, root, label):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        return subprocess.run(
            command, cwd=root, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10, **options,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"{label}: {exc}") from exc


def _check_cli(root, python):
    """Check advertised CLI syntax without importing optional dependencies."""
    kinds = ("string", "type", "method", "field", "extends", "impl")
    placeholder = str(root / "__asc_mcp_check__.apk")
    probes = [
        ([], ("getmanifest", "getclass", "listclass", "findrefs")),
        (["getmanifest"], ()),
        (["getclass"], ("--threads",)),
        (["listclass"], ("--prefix", "--threads")),
        (["findrefs"], ("--threads", *kinds)),
    ]
    for kind in kinds:
        expected = ("--class", "--fuzzy-class") if kind in ("method", "field") else ()
        probes.append((["findrefs", placeholder, kind], expected))
    for args, expected in probes:
        command = [str(python), "-B", "-X", "utf8", str(root / "main.py"), *args, "--help"]
        label = " ".join(arg for arg in args if arg != placeholder) or "main"
        result = _run_check(command, root, f"ASC CLI check failed for {label}")
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()[:1000]
            raise RuntimeError(f"ASC CLI check failed for {label}: {detail}")
        missing = [token for token in expected if token not in result.stdout]
        if missing:
            raise RuntimeError(f"ASC CLI check failed for {label}: missing {', '.join(missing)}")
    return {"status": "cli-help-compatible", "checks": len(probes)}


def _check_worker(root, python):
    command = [str(python), "-B", "-X", "utf8", str(WORKER_PATH), "--asc-root", str(root), "--check"]
    result = _run_check(command, root, "ASC worker API check failed")
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[:1000]
        raise RuntimeError(f"ASC worker API check failed: {detail}")
    try:
        report = json.loads(result.stdout)
    except ValueError as exc:
        raise RuntimeError("ASC worker API check returned invalid JSON") from exc
    if not isinstance(report, dict) or report.get("status") != "worker-api-compatible" or report.get("contract_version") != 3:
        raise RuntimeError("ASC worker API check returned an unsupported contract")
    return report


def check_compatibility(asc_root, asc_python):
    """Check CLI syntax and worker API shape, without claiming runtime readiness."""
    root, python = resolve_settings(asc_root, asc_python)
    cli = _check_cli(root, python)
    worker = _check_worker(root, python)
    return {
        "asc_root": str(root), "asc_python": str(python),
        **cli, "worker_api": worker,
        "limitation": "CLI syntax and worker API shape only; query semantics, APK analysis and MCP handshake are not verified.",
    }


_DEPENDENCY_PROBE = r'''
import contextlib
import importlib
import importlib.metadata
import io
import json
import platform
import sys

dependencies = {}
for name in sys.argv[1:]:
    dependency = {"importable": False, "version": None}
    try:
        dependency["version"] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        pass
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            importlib.import_module(name)
        dependency["importable"] = True
    except Exception as exc:
        dependency["error"] = f"{type(exc).__name__}: {exc}"[:1000]
    dependencies[name] = dependency
print(json.dumps({"executable": sys.executable, "python_version": platform.python_version(), "dependencies": dependencies}))
'''


def _interpreter_report(python, root, dependencies):
    command = [str(python), "-B", "-X", "utf8", "-c", _DEPENDENCY_PROBE, *dependencies]
    try:
        result = _run_check(command, root, "Python dependency probe failed")
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip()[:1000] or "no diagnostic output")
        report = json.loads(result.stdout)
        if not isinstance(report, dict) or not isinstance(report.get("dependencies"), dict):
            raise ValueError("unexpected dependency probe response")
    except (RuntimeError, ValueError) as exc:
        return {"configured_executable": str(python), "status": "probe-failed", "error": str(exc)}
    return {"configured_executable": str(python), "status": "probed", **report}


def _source_identity(root):
    identity = {"path": str(root)}
    try:
        project = (root / "pyproject.toml").read_text(encoding="utf-8")
        section = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", project)
        version = re.search(r'''(?m)^version\s*=\s*["']([^"']+)["']''', section.group(1)) if section else None
        if version:
            identity["version"] = version.group(1)
    except OSError:
        pass
    try:
        result = _run_check(["git", "-C", str(root), "rev-parse", "HEAD"], root, "Git revision unavailable")
        if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", result.stdout.strip()):
            identity["git_revision"] = result.stdout.strip()
    except RuntimeError:
        pass
    return identity


def diagnose_environment(asc_root=None, asc_python=None):
    """Inspect both environments without installing packages or analyzing an APK."""
    root, python = resolve_settings(asc_root, asc_python)
    adapter_root = Path(__file__).resolve().parent
    adapter = _source_identity(adapter_root)
    # This identifies copied adapters too, without claiming an enclosing Git
    # checkout's project version is the adapter's own version.
    digest = hashlib.sha256()
    for name in ("config.py", "configure.py", "server.py", "worker.py", "runtime.py", "evidence.py", "requirements.txt"):
        path = adapter_root / name
        if path.is_file():
            digest.update(name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    adapter["source_sha256"] = digest.hexdigest()
    interpreters = {
        "mcp": _interpreter_report(Path(sys.executable), adapter_root, ("mcp",)),
        "asc": _interpreter_report(python, root, ("axml", "mutf8")),
    }
    compatibility = {}
    for name, check in (("cli_syntax", _check_cli), ("worker_api", _check_worker)):
        try:
            compatibility[name] = check(root, python)
        except RuntimeError as exc:
            compatibility[name] = {"status": "failed", "error": str(exc)}
    dependencies_available = all(
        report["status"] == "probed" and all(item["importable"] for item in report["dependencies"].values())
        for report in interpreters.values()
    )
    return {
        "adapter": adapter, "asc": _source_identity(root),
        "interpreters": interpreters, "compatibility": compatibility,
        "runtime_readiness": {
            "status": "unverified", "dependencies_available": dependencies_available,
            "apk_analysis": "not-run", "mcp_handshake": "not-run",
            "limitation": "Dependency imports and interface checks do not verify a real APK analysis or an MCP handshake.",
        },
    }
