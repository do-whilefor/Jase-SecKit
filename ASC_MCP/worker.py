"""Isolated JSON analysis bridge to an ASC checkout with verified capabilities."""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import importlib
import inspect
import json
import mmap
from pathlib import Path
import re
import sys


CONTRACT_VERSION = 3
KINDS = ("string", "type", "method", "field", "extends", "impl")
REFERENCE_SOURCES = {
    "string": (["const_string", "const_string_jumbo"],
               ["static_encoded_values", "annotations", "call_site_arguments"]),
    "type": (["direct_type_operands"],
             ["signatures", "field_types", "catch_types", "annotation_types", "method_type_operands"]),
    "method": (["direct_invokes", "polymorphic_method_operand"],
               ["method_handle_targets", "call_site_targets"]),
    "field": (["direct_field_operands"], ["method_handle_targets"]),
    "extends": (["direct_superclass_declarations"], ["transitive_inheritance"]),
    "impl": (["direct_interface_declarations"], ["transitive_implementation"]),
}


def load_api(root):
    """Reject missing, relocated, or incompatible internal entry points early."""
    root = Path(root).resolve()
    if not (root / "droidasc").is_dir():
        raise ValueError(f"ASC source package not found under {root}")
    sys.path.insert(0, str(root))
    requirements = {
        "loader": ("droidasc.asc_client.apk.loader", {
            "_parse_cd_dex_entries": (1, {}),
            "_inflate_dex": (2, {}),
            "get_dex_inventory": (1, {}),
        }),
        "container": ("droidasc.asc_client.dex_container", {
            "get_logical_dex_layout": (2, {}),
            "normalize_dex041_logical": (2, {}),
        }),
        "reader": ("droidasc.asc_client.apk.dex_reader", {
            "list_dex_classes": (1, {"prefix": None, "prefix_bytes": None}),
        }),
        "names": ("droidasc.asc_client.class_names", {
            "normalize_class_name": (1, {}),
            "normalize_class_prefix": (1, {}),
        }),
        "dex": ("droidasc.asc_core.utils.tinydex", {
            "DEX.parse": (2, {}), "DEX.get_type": (2, {}),
            "DEX.get_class": (2, {}),
            "encode_mutf8": (1, {}),
        }),
        "refs": ("droidasc.asc_core.findrefs.findrefs_manager", {
            "FindRefManager": (1, {}),
            "FindRefManager.find_ref": (3, {}),
        }),
        "formatter": ("droidasc.asc_client.asc_handler", {
            "AscHandler": (0, {}),
            "AscHandler.getclass_report": (3, {}),
            "AscHandler._format_method": (3, {"include_descriptor": True}),
            "AscHandler._format_matched_name": (4, {"include_descriptor": True}),
        }),
    }
    api, checked = {}, []
    for key, (module_name, members) in requirements.items():
        try:
            module = importlib.import_module(module_name)
            if not Path(module.__file__).resolve().is_relative_to(root):
                raise ValueError("module resolved outside the selected checkout")
            for member_name, (positional_count, keywords) in members.items():
                member = module
                for part in member_name.split("."):
                    member = getattr(member, part)
                signature = inspect.signature(member)
                # Mirror the actual calls below, including positional arguments.
                signature.bind(*([None] * positional_count), **keywords)
                checked.append(f"{module_name}.{member_name}")
            api[key] = module
        except (ImportError, AttributeError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Incompatible ASC worker API in {module_name}: {exc}. "
                "Select a supported ASC checkout or update the standalone adapter."
            ) from exc
    capabilities = {
        "loader": ("LOADER_COVERAGE_VERSION", 3),
        "container": ("CONTAINER_VALIDATION_VERSION", 3),
        "refs": ("FindRefManager.EVIDENCE_VERSION", 3),
        "formatter": ("ASC_DECOMPILE_REPORT_VERSION", 2),
    }
    verified = {}
    for key, (name, required) in capabilities.items():
        value = api[key]
        for part in name.split("."):
            value = getattr(value, part, None)
        if value != required:
            raise RuntimeError(
                f"Incompatible ASC evidence capability {name}: expected {required}, got {value!r}. "
                "Select a checkout containing the ASC MCP reliability fixes."
            )
        verified[name] = value
    project = root / "pyproject.toml"
    source = project.read_text(encoding="utf-8") if project.is_file() else ""
    project_section = re.search(r"(?ms)^\[project\]\s*$(.*?)(?=^\[|\Z)", source)
    version = re.search(r'^version\s*=\s*[\"\']([^\"\']+)', project_section[1], re.M) if project_section else None
    report = {
        "status": "worker-api-compatible", "contract_version": CONTRACT_VERSION,
        "asc_root": str(root), "asc_version": version[1] if version else "unknown",
        "api": checked,
        "capabilities": verified,
        "limitation": "Internal entry points and signatures checked; no APK analysis or MCP handshake performed.",
    }
    return api, report


def make_query(request, api):
    kind, query = request["kind"], request["query"]
    if kind not in KINDS or not isinstance(query, str) or not query.strip() or "\0" in query:
        raise ValueError("A supported kind and a non-empty query without null bytes are required")
    class_name = request.get("class_name")
    fuzzy, regex = request.get("fuzzy_class", False), request.get("regex", False)
    if type(fuzzy) is not bool or type(regex) is not bool:
        raise ValueError("fuzzy_class and regex must be booleans")
    if class_name is not None and (not isinstance(class_name, str) or not class_name.strip() or "\0" in class_name):
        raise ValueError("class_name must be a non-empty string without null bytes")
    if (class_name is not None or fuzzy) and kind not in ("method", "field"):
        raise ValueError("Class filters apply only to method and field searches")
    if fuzzy and class_name is None:
        raise ValueError("fuzzy_class requires class_name")
    exact_member = class_name is not None and not fuzzy
    if regex and (kind in ("extends", "impl") or exact_member):
        raise ValueError("Regex is unsupported for inheritance or exact-class member queries")
    if kind in ("extends", "impl"):
        return {kind: api["names"].normalize_class_name(query)}
    if kind == "type" and not regex:
        query = query.replace(".", "/")
    if not exact_member:
        query = query if regex else re.escape(query)
        try:
            re.compile(api["dex"].encode_mutf8(query))
        except re.error as exc:
            raise ValueError(f"Invalid MUTF-8 byte regex: {exc}") from exc
    if kind in ("string", "type"):
        return {kind: query}
    owner = None
    if class_name is not None:
        owner = [re.escape(class_name.replace(".", "/")) if fuzzy else api["names"].normalize_class_name(class_name), not fuzzy]
    return {kind: {"class": owner, kind: query}}


def scan_dex(name, data, request, api):
    dex = api["dex"].DEX.parse(memoryview(data), name)
    kind = request["kind"]
    query = make_query(request, api)
    target = query.get(kind)
    manager = api["refs"].FindRefManager(dex)
    matched = manager.find_ref(query, True)
    if kind in ("extends", "impl"):
        return [{
            "dex": name, "caller": None,
            "class_name": dex.get_type(index).descriptor,
            "matched": {"kind": kind, "value": target}, "occurrence": 0,
            "dex_byte_offset": None, "method_code_unit_offset": None,
        } for index in matched]
    methods = query[kind]
    if len(matched) != len(methods):
        raise RuntimeError("Incompatible ASC result contract: target and caller counts differ")
    formatter = api["formatter"].AscHandler()
    occurrences, rows = defaultdict(int), []
    offsets = manager.code_scanner.mark_offsets if manager.code_scanner is not None else []
    if len(offsets) != len(matched):
        raise RuntimeError("Incompatible ASC result contract: missing reference instruction offsets")
    for index, callers, insn_offset in zip(matched, methods, offsets):
        if callers is None:
            continue
        for mid in callers if isinstance(callers, list) else [callers]:
            key = (mid, index)
            rows.append({
                "dex": name,
                "caller": formatter._format_method(dex, mid, include_descriptor=True),
                "class_name": dex.methods[mid].cls.fullname,
                "matched": {"kind": kind, "value": formatter._format_matched_name(dex, kind, index, include_descriptor=True)},
                "occurrence": occurrences[key],
                "dex_byte_offset": insn_offset,
                "method_code_unit_offset": (insn_offset - manager.insn_locator.method_bounds[mid]) // 2,
            })
            occurrences[key] += 1
    return rows


def _may_contain_selector(physical_name, selector):
    # Physical ZIP names may themselves contain '!'. Include every candidate
    # so a physical/logical identity collision is still rejected after reading.
    return physical_name == selector or re.fullmatch(
        re.escape(physical_name) + r"!classes[1-9][0-9]*\.dex", selector
    ) is not None


def analyze(request, api):
    path = Path(request["apk_path"])
    if not path.is_absolute() or not path.is_file():
        raise ValueError("apk_path must name an existing absolute file")
    threads = request.get("threads", 4)
    if type(threads) is not int or not 1 <= threads <= 16:
        raise ValueError("threads must be an integer between 1 and 16")
    operation = request.get("operation", "references")
    if operation not in ("references", "classes", "decompile"):
        raise ValueError("Unsupported analysis operation")
    prefix, prefix_bytes, class_name, selector = None, None, None, None
    if operation == "references":
        make_query(request, api)
    elif operation == "classes":
        prefix = request.get("prefix")
        if prefix is not None:
            if not isinstance(prefix, str) or not prefix.strip() or "\0" in prefix:
                raise ValueError("prefix must be a non-empty string without null bytes")
            prefix = api["names"].normalize_class_prefix(prefix)
            prefix_bytes = prefix.encode("ascii") if prefix.isascii() else None
    else:
        class_name = request.get("class_name")
        if not isinstance(class_name, str) or not class_name.strip() or "\0" in class_name:
            raise ValueError("class_name must be a non-empty string without null bytes")
        class_name = api["names"].normalize_class_name(class_name)
        selector = request.get("dex")
        if selector is not None and (not isinstance(selector, str) or not selector.strip() or "\0" in selector):
            raise ValueError("dex must be a DEX identity returned by class/reference lookup")
    with path.open("rb") as fp, mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        inventory = api["loader"].get_dex_inventory(mm)
        entries = api["loader"]._parse_cd_dex_entries(mm)
        if selector is not None:
            entries = [entry for entry in entries if _may_contain_selector(entry[0], selector)]
            selected = {entry[0] for entry in entries}
            inventory = [dict(row, selected=False, reason="dex_selector")
                         if row["selected"] and row["name"] not in selected else row
                         for row in inventory]

        def scan_entry(entry):
            data = api["loader"]._inflate_dex(mm, entry)
            rows, sources, candidates = [], [], []
            layout = api["container"].get_logical_dex_layout(entry[0], data)
            for index, (name, header_offset) in enumerate(layout):
                source = {"dex": name, "physical_dex": entry[0], "logical_dex_index": index}
                sources.append(source)
                if selector is not None and name != selector:
                    continue
                dex_data = api["container"].normalize_dex041_logical(data, header_offset)
                if operation == "references":
                    rows.extend({**row, **source} for row in scan_dex(name, dex_data, request, api))
                elif operation == "classes":
                    rows.extend({**source, "class_name": descriptor}
                                for descriptor in api["reader"].list_dex_classes(
                                    dex_data, prefix=prefix, prefix_bytes=prefix_bytes))
                elif selector is None or name == selector:
                    dex = api["dex"].DEX.parse(memoryview(dex_data), name)
                    if dex.get_class(class_name) is not None:
                        candidates.append(({**source, "class_name": class_name}, dex_data))
            return rows, sources, candidates

        if len(entries) > 1 and threads > 1:
            with ThreadPoolExecutor(max_workers=min(threads, len(entries))) as pool:
                results = list(pool.map(scan_entry, entries))
        else:
            results = [scan_entry(entry) for entry in entries]
    sources = [source for _, group, _ in results for source in group]
    names = [source["dex"] for source in sources]
    if len(set(names)) != len(names):
        raise ValueError("Ambiguous logical DEX identities in APK; rename colliding entries before analysis")
    coverage = {
        "scope": "static_dex_" + operation, "status": "complete",
        "physical_dex_entries": len(entries), "dex_entries": inventory,
        "logical_dex_scanned": names if selector is None else [name for name in names if name == selector],
        "logical_dex_headers_validated": names,
        "requested_dex": selector,
        "selection": "all_root_dex" if selector is None else "dex_selector",
        "limitations": [
            ("All root DEX entries are selected." if selector is None else
             "Only physical entries that can contain the requested DEX are selected; other root DEX entries are not validated."),
            "Nested DEX, embedded archives, and native code are not analyzed.",
            "References cover ASC-supported bytecode instructions; inheritance matches are direct only.",
            "An empty result does not prove absence of behavior, reflection, dynamically loaded code, or unsupported references.",
        ],
    }
    if operation == "decompile":
        if selector is not None and selector not in names:
            raise ValueError(f"DEX identity not found: {selector}")
        candidates = [candidate for _, _, group in results for candidate in group]
        if not candidates:
            raise ValueError(f"Class {class_name} not found in the selected DEX scope")
        if len(candidates) != 1:
            choices = ", ".join(source["dex"] for source, _ in candidates[:20])
            raise ValueError(f"Ambiguous class {class_name}; pass dex from class/reference results. Matches: {choices}")
        source, data = candidates[0]
        # Resolve the exact source before importing optional decompiler dependencies.
        report = api["formatter"].AscHandler().getclass_report(data, class_name)
        return {**report, "source": source, "coverage": coverage}
    rows = [row for items, _, _ in results for row in items]
    if operation == "references":
        rows.sort(key=lambda row: (row["dex"], row["caller"] or row["class_name"], row["matched"]["value"], row["occurrence"]))
        coverage["string_matching"] = "per_item_content_bytes"
        supported, excluded = REFERENCE_SOURCES[request["kind"]]
        coverage["supported_reference_sources"] = supported
        coverage["excluded_reference_sources"] = excluded
    return {"items": rows, "coverage": coverage}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asc-root", required=True, help="Absolute path to the selected ASC checkout.")
    parser.add_argument("--check", action="store_true", help="Check lightweight internal API signatures without analyzing an APK.")
    args = parser.parse_args(argv)
    if not Path(args.asc_root).is_absolute():
        parser.error("--asc-root must be absolute")
    try:
        with redirect_stdout(sys.stderr):
            api, report = load_api(args.asc_root)
            result = report if args.check else analyze(json.load(sys.stdin), api)
        json.dump(result, sys.stdout, ensure_ascii=True, separators=(",", ":"))
        sys.stdout.write("\n")
    except Exception as exc:
        print(f"ASC analysis worker failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
