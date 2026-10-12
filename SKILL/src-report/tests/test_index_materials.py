"""Behavior tests for stable, read-only evidence registration."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "index_materials.py"
SPEC = importlib.util.spec_from_file_location("index_materials", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
indexer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(indexer)


class IndexMaterialsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "materials"
        self.root.mkdir()

    def write(self, path, content):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return destination

    def run_cli(self, output, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.root), "--output", str(output), *args],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_duplicate_rename_order_and_byte_change(self):
        payload = b"GET /authorized-demo HTTP/1.1\r\n\r\n"
        original = self.write("z-request.http", payload)
        duplicate = self.write("nested/duplicate.txt", payload)
        self.write("a-note.md", b"Observed only in a local fixture")
        first = indexer.index_materials(self.root)
        expected_hash = hashlib.sha256(payload).hexdigest()
        record = next(item for item in first["materials"] if item["sha256"] == expected_hash)
        self.assertEqual(record["paths"], ["nested/duplicate.txt", "z-request.http"])
        self.assertEqual(record["evidence_id"], "E-" + expected_hash[:16])
        self.assertEqual(record["size_bytes"], len(payload))
        self.assertEqual(len(first["materials"]), 2)
        self.assertEqual(first["warnings"], [])

        original.rename(self.root / "b-renamed.http")
        duplicate.rename(self.root / "c-second.http")
        second = indexer.index_materials(self.root)
        self.assertEqual([item["evidence_id"] for item in first["materials"]],
                         [item["evidence_id"] for item in second["materials"]])
        changed = self.root / "b-renamed.http"
        changed.write_bytes(payload + b"changed")
        third = indexer.index_materials(self.root)
        self.assertEqual(len(third["materials"]), 3)
        self.assertIn(record["evidence_id"], [item["evidence_id"] for item in third["materials"]])
        self.assertEqual((self.root / "c-second.http").read_bytes(), payload)

    def test_cli_writes_utf8_updates_atomically_and_excludes_paths(self):
        self.write("截图说明.md", "截图不证明归属".encode("utf-8"))
        self.write(".git/config", b"ignore")
        self.write("nested/__pycache__/cache.pyc", b"ignore")
        self.write("omit/secret.txt", b"ignore")
        output = self.base / "case" / "manifest.json"
        result = self.run_cli(output, "--exclude", "omit")
        self.assertEqual(result.returncode, 0, result.stderr)
        content = output.read_text(encoding="utf-8")
        manifest = json.loads(content)
        self.assertIn("截图说明.md", content)
        self.assertEqual(manifest["schema_version"], "1.0")
        self.assertEqual(manifest["materials_root"], str(self.root))
        self.assertEqual(len(manifest["materials"]), 1)
        repeat = self.run_cli(output, "--exclude", "omit")
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertEqual(output.read_text(encoding="utf-8"), content)
        self.assertEqual(sorted(path.name for path in output.parent.iterdir()), ["manifest.json"])

    def test_output_within_root_is_rejected_before_reading(self):
        source = self.write("original.txt", b"original")
        for output in (source, self.root / "new/manifest.json", self.root / "sub/../manifest.json"):
            with self.subTest(output=output):
                result = self.run_cli(output)
                self.assertEqual(result.returncode, 2)
                self.assertIn("outside the materials root", result.stderr)
        self.assertEqual(source.read_bytes(), b"original")
        self.assertFalse((self.root / "new").exists())

    def test_missing_root_and_invalid_exclusions_are_errors(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            indexer.index_materials(self.root / "absent")
        for excluded in ("../outside", "/outside", "C:\\outside", ".", ""):
            with self.subTest(excluded=excluded), self.assertRaises(ValueError):
                indexer.index_materials(self.root, [excluded])

    def test_empty_input_is_valid_with_warning(self):
        manifest = indexer.index_materials(self.root)
        self.assertEqual(manifest["materials"], [])
        self.assertEqual(manifest["warnings"][0]["path"], ".")
        self.assertIn("empty", manifest["warnings"][0]["reason"])

    def test_read_failures_are_visible_in_manifest(self):
        self.write("unreadable.txt", b"some bytes")
        with mock.patch.object(indexer, "_hash_file", side_effect=PermissionError("denied")):
            manifest = indexer.index_materials(self.root)
        self.assertEqual(manifest["materials"], [])
        warning = next(item for item in manifest["warnings"] if item["path"] == "unreadable.txt")
        self.assertIn("denied", warning["reason"])

    def test_hash_prefix_collision_uses_full_hash_for_every_record(self):
        self.write("one.txt", b"one")
        self.write("two.txt", b"two")
        self.write("three.txt", b"three")
        hashes = {
            "one.txt": "0" * 16 + "1" * 48,
            "two.txt": "0" * 16 + "2" * 48,
            "three.txt": "f" * 64,
        }
        with mock.patch.object(indexer, "_hash_file", side_effect=lambda path, info: (hashes[path.name], info.st_size)):
            manifest = indexer.index_materials(self.root)
        self.assertEqual([item["sha256"] for item in manifest["materials"]], sorted(hashes.values()))
        for record in manifest["materials"]:
            self.assertEqual(record["evidence_id"], "E-" + record["sha256"])

    def create_symlink_or_skip(self, target, link, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symbolic links unavailable on this platform: {exc}")

    def test_symlink_files_and_directories_never_read_outside(self):
        outside = self.base / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_bytes(b"must never be read")
        self.write("local.txt", b"local")
        self.create_symlink_or_skip(secret, self.root / "linked.txt")
        self.create_symlink_or_skip(outside, self.root / "linked-dir", directory=True)
        actual_hash = indexer._hash_file
        paths_read = []

        def record_read(path, info):
            paths_read.append(path)
            return actual_hash(path, info)

        with mock.patch.object(indexer, "_hash_file", side_effect=record_read):
            manifest = indexer.index_materials(self.root)
        self.assertEqual(paths_read, [self.root / "local.txt"])
        self.assertEqual(len(manifest["materials"]), 1)
        self.assertEqual([item["path"] for item in manifest["warnings"]], ["linked-dir", "linked.txt"])

    def test_symlink_output_parent_and_root_are_rejected(self):
        link = self.base / "alias"
        self.create_symlink_or_skip(self.root, link, directory=True)
        with self.assertRaisesRegex(ValueError, "link/reparse"):
            indexer.index_materials(link)
        result = self.run_cli(link / "manifest.json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("link/reparse", result.stderr)
        self.assertFalse((self.root / "manifest.json").exists())

    def test_modified_while_reading_is_not_registered(self):
        path = self.write("moving.txt", b"unchanged")
        before = path.stat()
        path.write_bytes(b"changed-and-larger")
        with self.assertRaisesRegex(OSError, "changed or was replaced"):
            indexer._hash_file(path, before)

    def test_code_is_not_executed_and_archives_are_not_unpacked(self):
        marker = self.base / "must-not-exist.txt"
        program = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
        self.write("poc.py", program.encode("utf-8"))
        archive = self.root / "evidence.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("nested/hidden.txt", "must not be extracted")
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        manifest = indexer.index_materials(self.root)
        self.assertFalse(marker.exists())
        self.assertEqual({path.name: path.read_bytes() for path in self.root.iterdir()}, before)
        self.assertEqual({item["kind"] for item in manifest["materials"]}, {"code", "archive"})
        self.assertEqual(len(manifest["materials"]), 2)

    def test_output_sibling_with_root_name_prefix_is_allowed(self):
        self.write("note.txt", b"observation")
        output = self.base / "materials-report" / "manifest.json"
        result = self.run_cli(output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.is_file())

    def test_windows_reparse_attribute_is_treated_as_link(self):
        info = mock.Mock(st_mode=0o100644, st_file_attributes=0x400)
        self.assertTrue(indexer._is_link_or_reparse(info))


if __name__ == "__main__":
    unittest.main()
