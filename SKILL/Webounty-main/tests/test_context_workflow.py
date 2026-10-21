"""Public context/read behavior across local conversation turns."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import session
from rag import Corpus, encode


class ContextWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        override = patch.object(session, "base_directory", return_value=self.base / "sessions")
        override.start()
        self.addCleanup(override.stop)
        self.opened = session.start("local-context", "Inspect the report workflow")
        self.common = ["--root", self.opened["root"], "--run-id", self.opened["run_id"]]

    def invoke(self, command, *args, batch=None):
        argv = [command, *self.common, *args]
        if batch is not None:
            path = self.base / "batch.json"
            path.write_text(json.dumps(batch), encoding="utf-8")
            argv.extend(["--input", str(path)])
        return session.dispatch(session.parser().parse_args(argv))

    def context(self, *args):
        return self.invoke("context", "--query", "", "--anchor", "F-REPORT", "--no-methods", *args)

    def test_compact_delta_counterevidence_refresh_and_original_read(self):
        original = self.base / "response.txt"
        payload = "Synthetic report row\n" * 1500
        original.write_bytes(payload.encode("utf-8"))
        self.invoke("record", batch={
            "observations": [{"id": "O-REPORT", "summary": "The report response",
                "content": {"response": {"status": 200, "body": payload}}, "source_path": str(original)}],
            "records": [{"id": "F-REPORT", "kind": "Fact", "status": "observed",
                "summary": "A report was returned under the recorded identity",
                "conditions": {"tenant": "training-a"}, "observation_refs": ["O-REPORT"]}]})
        compact = self.context("--cursor", "main")
        evidence = self.context("--view", "evidence")
        self.assertLess(len(encode(compact)), len(encode(evidence)))
        self.assertNotIn(payload, encode(compact))
        self.assertEqual(next(row for row in compact["records"] if row["id"] == "F-REPORT")["conditions"],
                         {"tenant": "training-a"})
        again = self.context("--cursor", "main")
        self.assertFalse(again["records"])
        self.assertTrue(any(row["id"] == "F-REPORT" for row in again["unchanged_refs"]))
        self.invoke("record", batch={"records": [{"id": "F-CORRECTION", "kind": "Finding",
            "status": "candidate", "summary": "Report ownership needs a separate check",
            "contradicts": ["F-REPORT"]}]})
        changed = self.context("--cursor", "main")
        self.assertIn("F-CORRECTION", {row["id"] for row in changed["records"]})
        refreshed = self.context("--cursor", "main", "--refresh")
        self.assertTrue({"F-REPORT", "F-CORRECTION"}.issubset({row["id"] for row in refreshed["records"]}))
        raw = self.invoke("read", "--id", "O-REPORT")["package"]["observations"][0]
        self.assertEqual(raw["raw"]["response"]["body"], payload)
        source_id = raw["index"]["source_artifact_id"]
        source = self.invoke("read", "--id", source_id)["package"]["artifacts"][0]
        self.assertEqual(source["content"], payload)

    def test_original_read_preserves_source_line_endings(self):
        for label, newline in (("LF", "\n"), ("CRLF", "\r\n")):
            with self.subTest(newline=label):
                payload = newline.join(("First report row", "第二行", ""))
                original = self.base / f"response-{label}.txt"
                original.write_bytes(payload.encode("utf-8"))
                observation_id = f"O-{label}"
                self.invoke("record", batch={"observations": [{
                    "id": observation_id, "source_path": str(original),
                    "content": {"response": {"body": payload}},
                }]})
                raw = self.invoke("read", "--id", observation_id)["package"]["observations"][0]
                self.assertEqual(raw["raw"]["response"]["body"], payload)
                source_id = raw["index"]["source_artifact_id"]
                source = self.invoke("read", "--id", source_id)["package"]["artifacts"][0]
                self.assertEqual(source["content"], payload)

    def test_unrelated_unknown_payloads_stay_searchable_without_default_context_flood(self):
        self.invoke("record", batch={
            "observations": [{"id": "O-OTHER", "content": {"response": "rare-other-term " * 1000}}],
            "records": [{"id": "F-REPORT", "kind": "Step", "status": "planned", "summary": "Inspect report"}]})
        result = self.context()
        self.assertNotIn("O-OTHER", {row["id"] for row in result["observations"]})
        self.assertTrue(any(row["code"] == "unclassified_outside_query" for row in result["gaps"]))
        found = self.invoke("context", "--query", "rare-other-term", "--no-methods")
        self.assertIn("O-OTHER", {row["id"] for row in found["observations"]})

    def test_exact_page_read_loads_only_its_current_page(self):
        self.invoke("record", batch={"records": [
            {"id": "F-REPORT", "kind": "Step", "status": "planned", "summary": "Inspect report"},
            {"id": "S-OTHER", "kind": "Step", "status": "planned", "summary": "Other topic"}]})
        corpus = Corpus(self.opened["root"], self.opened["run_id"], lazy_pages=True)
        page = next(pid for pid, row in corpus.pages.items() if row.get("auto_record_ref") == "F-REPORT")
        self.assertFalse(corpus.loaded_pages)
        result = session.read_ids(corpus, [page])
        self.assertEqual(corpus.loaded_pages, {page})
        self.assertTrue(result["package"]["blocks"][0]["text"])


if __name__ == "__main__":
    unittest.main()
