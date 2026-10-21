#!/usr/bin/env python3
"""Claude Code session Wiki: local files, one writer, explicit cleanup."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from time import perf_counter
import uuid

sys.dont_write_bytecode = True

from telemetry import measure, count


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def base_directory(project_root=None):
    project = Path(project_root if project_root is not None else Path.cwd()).resolve(strict=True)
    if not project.is_dir():
        raise ValueError("project_root must be an existing directory")
    directory = project / ".webounty"
    if directory.is_symlink():
        raise ValueError("project .webounty directory cannot be a symlink")
    return directory


def root_for(session_id, project_root=None):
    if not session_id or not session_id.strip():
        raise ValueError("session_id must identify this conversation")
    return base_directory(project_root) / hashlib.sha256(session_id.encode()).hexdigest()


def ownership(root, run_id, session_id=None):
    root = Path(root).absolute()
    if root.is_symlink():
        raise ValueError("session root cannot be a symlink")
    marker = root / "session.json"
    if marker.is_symlink():
        raise ValueError("session marker cannot be a symlink")
    owner = json.loads(marker.read_text(encoding="utf-8"))
    if (owner.get("kind") != "webounty_session" or owner.get("run_id") != run_id
            or root != root_for(owner["session_id"], owner["project_root"])):
        raise ValueError("root/run_id does not identify a managed webounty session")
    if session_id is not None and owner["session_id"] != session_id:
        raise ValueError("session_id mismatch")
    return root, owner


def log(root, action, **metadata):
    folder = Path(root) / "logs"
    folder.mkdir(exist_ok=True)
    event = {"at": datetime.now(timezone.utc).isoformat(), "action": action, **metadata}
    with (folder / "operations.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def start(session_id, question, project_root=None, hard_constraints=()):
    if not question.strip():
        raise ValueError("question cannot be empty")
    project = Path(project_root if project_root is not None else Path.cwd()).resolve(strict=True)
    root = root_for(session_id, project)
    if root.exists():
        owner = json.loads((root / "session.json").read_text(encoding="utf-8"))
        ownership(root, owner["run_id"], session_id)
        from publication import reader
        with reader(root, owner["run_id"]):
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
        if state["run_id"] != owner["run_id"]:
            raise ValueError("state does not belong to this session")
        status = "reused"
    else:
        root.mkdir(mode=0o700, parents=True)
        for name in ("wiki/pages", "evidence", "logs"):
            (root / name).mkdir(parents=True)
        owner = {"kind": "webounty_session", "schema_version": 1, "project_root": str(project),
                 "session_id": session_id, "run_id": "WB-" + uuid.uuid4().hex}
        state = {"run_id": owner["run_id"], "session_id": session_id, "revision": 1,
                 "records": {"G-001": {"id": "G-001", "kind": "Goal", "revision": 1,
                                         "status": "active", "summary": question, "hard_constraints": list(hard_constraints),
                                         "subject_refs": [], "observation_refs": []}},
                 "entities": {}, "observations": {}, "artifacts": {}}
        (root / "session.json").write_text(dump(owner), encoding="utf-8")
        (root / "state.json").write_text(dump(state), encoding="utf-8")
        (root / "wiki/manifest.json").write_text(dump({"schema_version": 1,
                         "run_id": owner["run_id"], "pages": []}), encoding="utf-8")
        (root / "wiki/index.md").write_text("# 本会话 Wiki\n\n" + question + "\n", encoding="utf-8")
        status = "created"
    log(root, "start", status=status)
    return {"status": status, "root": str(root), "run_id": owner["run_id"],
            "session_id": session_id, "project_root": str(project), "state_revision": state["revision"],
            "goals": [r for r in state["records"].values() if r["kind"] == "Goal"],
            "retention": "current_session", "cleanup": "explicit_finish",
            "host_end_hook_installed": False}


def finish(root, run_id, session_id, export=None):
    root, owner = ownership(root, run_id, session_id)
    output = None
    if export:
        output = Path(export).absolute()
        if output.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(output.resolve()):
            raise ValueError("export must be outside the session root and its ancestors")
        shutil.copytree(root, output)
    shutil.rmtree(root)
    return {"status": "deleted", "session_id": owner["session_id"], "run_id": run_id,
            "export": str(output) if output else None}


def read_ids(corpus, identifiers, *, offset=None, length=None, pointer=None):
    if pointer is not None and (offset is not None or length is not None):
        raise ValueError("pointer and byte range reads are separate selectors")
    if pointer is not None and any(identifier not in corpus.observations for identifier in identifiers):
        raise ValueError("JSON Pointer reads address observation IDs")
    if (offset is None) != (length is None):
        raise ValueError("range reads require both --offset and --length")
    if offset is not None and any(identifier not in corpus.artifacts for identifier in identifiers):
        raise ValueError("range reads address artifact IDs from source_match or provenance")
    wanted = {"record_ids": [], "entity_ids": [], "observation_ids": [], "block_keys": []}
    artifact_ids = []
    for identifier in identifiers:
        if identifier in corpus.records:
            wanted["record_ids"].append(identifier)
        elif identifier in corpus.entities:
            wanted["entity_ids"].append(identifier)
        elif identifier in corpus.observations:
            wanted["observation_ids"].append(identifier)
        elif identifier in corpus.artifacts:
            artifact_ids.append(identifier)
        elif identifier in corpus.blocks:
            wanted["block_keys"].append(identifier)
        elif identifier in corpus.pages:
            wanted["block_keys"].extend(identifier + "/" + block["block_id"]
                                        for block in corpus.pages[identifier]["blocks"])
        else:
            raise ValueError("unknown ID: " + identifier)
    package, issues = corpus.package(**wanted, view="compact" if pointer is not None else "evidence")
    if package is not None:
        if pointer is not None:
            from excerpts import json_excerpt
            for row in package["observations"]:
                if row["id"] in identifiers and row["status"] == "ready":
                    row["excerpts"] = [json_excerpt(corpus.observation(row["id"]), pointer)]
        artifacts = {row["id"]: row for row in package["artifacts"]}
        for aid in artifact_ids:
            if offset is not None:
                row = corpus.artifact_window(aid, offset, length)
                issues.extend(row["issues"])
                artifacts[aid] = row
                continue
            artifact = corpus.artifact(aid)
            row = {key: value for key, value in artifact.items() if key != "data"}
            issues.extend(artifact["issues"])
            data = corpus.artifact_data(aid)
            if data is not None:
                try:
                    row["content"] = data.decode("utf-8")
                except UnicodeError:
                    issues.append({"code": "non_text_artifact", "artifact_id": aid})
            artifacts[aid] = row
        package["artifacts"] = list(artifacts.values())
    if not corpus.stable():
        return {"status": "unavailable", "issues": [{"code": "snapshot_changed"}]}
    return {"run_id": corpus.run_id, "state_revision": corpus.state["revision"],
            "status": "unavailable" if package is None else "review_required" if issues else "ready",
            "package": package, "issues": issues}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("start", help="Create or reuse this conversation's Wiki")
    cmd.add_argument("--session-id", required=True)
    cmd.add_argument("--question", required=True)
    cmd.add_argument("--constraint", action="append", default=[], help="Verbatim user constraint; repeatable")
    cmd.add_argument("--project-root", help="Project directory for .webounty; defaults to the current directory")
    for name in ("record", "context", "discover", "read", "compare", "audit", "finish", "wiki"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--root", required=True)
        cmd.add_argument("--run-id", required=True)
        if name in {"context", "discover", "read"}:
            cmd.add_argument("--current-conditions", type=json.loads, help="Current execution context as a JSON object")
        if name == "record":
            cmd.add_argument("--input", required=True, help="JSON batch file, or - for stdin")
        elif name == "context":
            cmd.add_argument("--query", default="")
            cmd.add_argument("--mode", choices=("combined", "lexical"), default="combined")
            cmd.add_argument("--question-ref", help="Existing question/goal/step record to check")
            cmd.add_argument("--anchor", action="append", default=[])
            cmd.add_argument("--budget-chars", type=int)
            cmd.add_argument("--max-candidates", type=int)
            cmd.add_argument("--cross-limit", type=int, default=0)
            cmd.add_argument("--method-id", action="append", default=[])
            cmd.add_argument("--method-intent", action="append", default=[])
            cmd.add_argument("--no-methods", action="store_true")
            cmd.add_argument("--view", choices=("compact", "evidence"), default="compact")
            cmd.add_argument("--cursor", help="Reuse a conversation reader cursor to return changes")
            cmd.add_argument("--refresh", action="store_true", help="Resend current context after compaction")
            cmd.add_argument("--context-epoch", help="Host context generation; a change resets this cursor")
        elif name == "discover":
            cmd.add_argument("--query", default="")
            cmd.add_argument("--anchor", action="append", default=[])
            cmd.add_argument("--changed", action="append", default=[])
        elif name == "read":
            cmd.add_argument("--id", action="append", required=True)
            cmd.add_argument("--offset", type=int, help="Byte offset in an original artifact")
            cmd.add_argument("--length", type=int, help="Number of original bytes to read")
            cmd.add_argument("--pointer", help="JSON Pointer within an original observation")
        elif name == "compare":
            cmd.add_argument("--left", required=True, help="First stored observation ID")
            cmd.add_argument("--right", required=True, help="Second stored observation ID")
            cmd.add_argument("--field", action="append", default=[],
                             help="Business field path, e.g. response.body.status; repeatable")
        elif name == "finish":
            cmd.add_argument("--session-id", required=True)
            cmd.add_argument("--export", help="Explicitly retain a snapshot in a new directory")
        elif name == "wiki":
            cmd.add_argument("action", choices=("audit", "knowledge"))
            cmd.add_argument("--block", action="append", default=[])
    cmd = sub.add_parser("methods")
    cmd.add_argument("--query", required=True)
    cmd.add_argument("--method-id", action="append", default=[])
    cmd.add_argument("--intent", action="append", default=[])
    return p


def dispatch(args, *, metrics=None):
    metrics = {} if metrics is None else metrics
    if args.command == "start":
        return start(args.session_id, args.question, args.project_root, args.constraint)
    if args.command == "methods":
        from methods import select_methods
        cards, issues = select_methods(args.query, args.method_id, intents=args.intent)
        return {"methods": cards, "issues": issues, "evidence": False}
    root, _ = ownership(args.root, args.run_id)
    if args.command == "finish":
        return finish(root, args.run_id, args.session_id, args.export)
    if args.command == "record":
        from store import publish
        from rag import Corpus
        from discovery import discover
        text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        result = publish(root, args.run_id, json.loads(text), metrics=metrics)
        try:
            with Corpus(root, args.run_id, lazy_pages=True, lazy_metadata=True, metrics=metrics) as corpus:
                with measure(metrics, "discovery"):
                    result["chain_discovery"] = discover(corpus, changed=result["changed_record_ids"])
                from change_impact import build_impact
                with measure(metrics, "change_impact"):
                    changed = (result["changed_record_ids"] + result["changed_entity_ids"]
                               + result["observation_ids"] + result["content_changed_page_ids"])
                    result["change_impact"] = build_impact(corpus, changed, discovery=result["chain_discovery"])
        except Exception as exc:
            result.setdefault("warnings", []).append({"code": "post_publish_analysis_failed", "detail": str(exc)})
        try:
            log(root, "record", state_revision=result["state_revision"], metrics=metrics)
        except Exception as exc:
            result.setdefault("warnings", []).append({"code": "record_log_failed", "detail": str(exc)})
        return result
    if args.command == "context":
        from rag import retrieve
        if args.no_methods and (args.method_id or args.method_intent):
            raise ValueError("--no-methods conflicts with explicit method requests")
        started = perf_counter()
        result = retrieve(root, args.run_id, args.query, args.anchor,
                          budget_chars=args.budget_chars, max_candidates=args.max_candidates,
                          include_methods=not args.no_methods, method_ids=args.method_id,
                          method_intents=args.method_intent, cross_limit=args.cross_limit,
                          view=args.view, cursor=args.cursor, refresh=args.refresh, metrics=metrics,
                          mode=args.mode, question_ref=args.question_ref, context_epoch=args.context_epoch,
                          current_conditions=args.current_conditions)
        log(root, "context", state_revision=result["state_revision"], anchors=args.anchor,
            elapsed_ms=round((perf_counter() - started) * 1000, 3),
            view=args.view, mode=args.mode, question_ref=args.question_ref, output_chars=result["budget"]["used_chars"], metrics=metrics)
        return result
    if args.command == "discover":
        from rag import Corpus
        from discovery import discover
        with Corpus(root, args.run_id, lazy_pages=True, lazy_metadata=True, metrics=metrics,
                    current_conditions=args.current_conditions) as corpus:
            with measure(metrics, "discovery"):
                result = discover(corpus, args.query, args.anchor, args.changed)
            if not corpus.stable():
                raise ValueError("session changed while reading; retrieve current state")
            log(root, "discover", state_revision=corpus.state["revision"], anchors=args.anchor,
                changed=args.changed, metrics=metrics)
            return {"run_id": args.run_id, "state_revision": corpus.state["revision"], **result}
    if args.command == "read":
        from rag import Corpus
        count(metrics, "read_calls")
        with Corpus(root, args.run_id, lazy_pages=True, lazy_metadata=True, metrics=metrics,
                    current_conditions=args.current_conditions) as corpus:
            result = read_ids(corpus, args.id, offset=args.offset, length=args.length, pointer=args.pointer)
        log(root, "read", ids=args.id, metrics=metrics)
        return result
    if args.command == "compare":
        from rag import Corpus
        from compare_observations import compare
        with Corpus(root, args.run_id, lazy_pages=True, lazy_metadata=True, metrics=metrics) as corpus:
            result = compare(corpus, args.left, args.right, fields=args.field)
            if not corpus.stable():
                raise ValueError("session changed while comparing; read current observations")
            log(root, "compare", state_revision=corpus.state["revision"],
                observation_ids=[args.left, args.right], fields=args.field, metrics=metrics)
            return {"run_id": args.run_id, "state_revision": corpus.state["revision"], **result}
    if args.command == "audit":
        from store import audit
        return audit(root, args.run_id)
    from wiki import audit, knowledge
    return audit(root, args.run_id) if args.action == "audit" else knowledge(root, args.run_id, args.block)


def main(argv=None):
    args = parser().parse_args(argv)
    metrics = {}
    try:
        result = dispatch(args, metrics=metrics)
    except (ValueError, OSError, KeyError) as exc:
        print(dump({"error": str(exc)}), file=sys.stderr)
        return 1
    with measure(metrics, "serialization"):
        output = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if hasattr(args, "root") and args.command != "finish":
        try:
            log(args.root, "response", command=args.command, state_revision=result.get("state_revision"),
                output_chars=len(output), metrics=metrics)
        except Exception as exc:
            if result.get("publication_status") != "committed":
                raise
            result.setdefault("warnings", []).append({"code": "response_log_failed", "detail": str(exc)})
            output = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
