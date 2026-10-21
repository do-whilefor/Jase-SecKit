"""Public behavior after source changes, context loss and selective evidence reads."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from conditions import check
from discovery import discover
from excerpts import pointer_value
from rag import Corpus, encode, retrieve
from session import dispatch, parser, read_ids, start
from store import publish, _verified_compatibility
from search_index import query_terms, rank


class ReviewFixesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.session = start("review-fixes", "检查报表授权", self.project,
                             hard_constraints=["只读取指定样例，不发送网络请求"])
        self.root, self.run = Path(self.session["root"]), self.session["run_id"]

    def add(self, records=(), observations=(), **extras):
        return publish(self.root, self.run, {"records": list(records), "observations": list(observations), **extras})

    def context(self, anchors=("Q",), **options):
        return retrieve(self.root, self.run, "", anchors, view="compact", **options)

    def invoke(self, command, *arguments):
        return dispatch(parser().parse_args([command, "--root", str(self.root),
                                            "--run-id", self.run, *arguments]))

    def pair(self, tenant="lab-a"):
        spec = {"type": "ticket", "constraints": {"tenant": tenant}}
        self.add([
            {"id": "P", "kind": "Capability", "status": "observed", "summary": "Provide ticket",
             "conditions": {"tenant": tenant}, "observation_refs": ["OP"], "capability": {"provides": [spec]}},
            {"id": "Q", "kind": "Question", "status": "open", "summary": "Use ticket",
             "conditions": {"tenant": tenant}, "observation_refs": ["OQ"], "capability": {"needs": [spec]}},
        ], [{"id": "OP", "content": {"response": {"ticket": "sample-ticket"}}},
            {"id": "OQ", "content": {"response": {"status": 403}}}])

    def test_unknown_values_do_not_complete_a_question(self):
        self.pair("unknown")
        result = self.context(question_ref="Q")
        self.assertEqual(result["question_context"]["requirements"]["status"], "unresolved")
        edge = result["chain_discovery"]["candidates"][0]
        self.assertEqual(edge["compatibility"], "unknown")
        self.assertTrue(edge["unknown_conditions"])
        for value in ("unknown", " UNKNOWN ", "未记录", "未知", "", "unspecified", "not_recorded"):
            with self.subTest(value=value):
                conflicts, unknown = check({"tenant": value}, {"tenant": value})
                self.assertFalse(conflicts)
                self.assertTrue(unknown)
                spec = {"type": "ticket", "constraints": {"tenant": value}}
                with self.assertRaises(ValueError):
                    _verified_compatibility(spec, spec, {"tenant": value}, {})
        self.assertEqual(check({"tenant": "lab-a"}, {"tenant": "lab-a"}), ([], []))
        self.assertTrue(check({"tenant": "lab-a"}, {"tenant": "lab-b"})[0])

    def test_source_revision_is_visible_from_every_read_entry(self):
        self.add([
            {"id": "F", "kind": "Fact", "status": "observed", "summary": "Feature enabled", "observation_refs": ["O1"]},
            {"id": "Q", "kind": "Fact", "status": "verified", "summary": "Feature usable",
             "source_refs": [{"id": "F", "revision": 1}]},
        ], [{"id": "O1", "content": {"feature": "enabled"}}])
        changed = self.add([{"id": "F", "summary": "Feature disabled", "observation_refs": ["O2"]}],
                           [{"id": "O2", "content": {"feature": "disabled"}}])
        self.assertIn("Q", changed["needs_review_record_ids"])
        direct = self.invoke("read", "--id", "Q")
        self.assertEqual(direct["status"], "review_required")
        self.assertIn("stale_source", {row["code"] for row in direct["issues"]})
        record = next(row for row in direct["package"]["records"] if row["id"] == "Q")
        self.assertEqual(record["status"], "verified")
        self.assertEqual(record["basis_status"], "needs_review")
        lexical = self.context(mode="lexical")
        self.assertIn("stale_source", {row["code"] for row in lexical["gaps"]})
        question = self.context(question_ref="Q")["question_context"]
        self.assertIn("stale_source", {row["code"] for row in question["source_issues"]})
        with self.assertRaisesRegex(ValueError, "unresolved source"):
            self.add([{"id": "Q", "reviewed": True, "change_reason": "Review without rebinding"}])
        self.add([{"id": "Q", "source_refs": [{"id": "F", "revision": 2}], "reviewed": True,
                   "summary": "Feature is unavailable under the current conditions", "status": "observed",
                   "change_reason": "Re-read the new observation and narrowed the claim"}])
        direct = self.invoke("read", "--id", "Q")
        self.assertNotIn("stale_source", {row["code"] for row in direct["issues"]})
        self.assertNotIn("basis_review_required", {row["code"] for row in direct["issues"]})

    def test_epoch_restores_bodies_and_constraints_are_always_available(self):
        self.pair()
        first = self.context(cursor="main", context_epoch="before")
        second = self.context(cursor="main", context_epoch="before")
        self.assertFalse(second["records"])
        self.assertEqual(second["task_core"]["goals"][0]["hard_constraints"],
                         ["只读取指定样例，不发送网络请求"])
        restored = self.context(cursor="main", context_epoch="after")
        self.assertTrue(restored["records"])
        self.assertEqual(restored["delta"]["reset_reason"], "context_epoch_changed")
        self.assertEqual(restored["task_core"], first["task_core"])
        self.assertEqual(self.context(cursor="other", context_epoch="after")["delta"]["reset_reason"], "new_cursor")

    def test_delta_budget_does_not_charge_retained_source_body_again(self):
        self.add([
            {"id": "F", "kind": "Fact", "status": "observed", "summary": "Original explanation " * 1000,
             "observation_refs": ["O"]},
            {"id": "Q", "kind": "Question", "status": "open", "summary": "Current question", "source_refs": ["F"]},
            {"id": "G-001", "source_refs": ["F"]},
        ], [{"id": "O", "content": {"result": "synthetic"}}])
        first = self.context(cursor="main", mode="lexical")
        delta = self.context(cursor="main", mode="lexical")
        budget = delta["budget"]["used_chars"] + 500
        self.assertGreater(first["budget"]["used_chars"], budget)
        limited = self.context(cursor="main", mode="lexical", budget_chars=budget)
        self.assertNotEqual(limited["status"], "unavailable")
        self.assertTrue(limited["delta"]["cursor_advanced"])
        self.assertLessEqual(len(encode(limited)), budget)
        self.assertFalse(limited["records"])
        # A new host epoch cannot rely on the retained body.
        restored = self.context(cursor="main", mode="lexical", budget_chars=budget, context_epoch="new")
        self.assertEqual(restored["status"], "unavailable")
        self.assertFalse(restored["delta"]["cursor_advanced"])

    def test_function_words_do_not_expand_all_observations(self):
        self.add(observations=[{"id": f"O-{i}", "subject_refs": ["E"], "content": {
            "response": {"body": f"The ordinary response for item {i} is present."}}} for i in range(120)],
            entities=[{"id": "E", "kind": "Endpoint", "summary": "Synthetic endpoint"}])
        result = retrieve(self.root, self.run, "What is the result for zqvnosuchidentifier?",
                          mode="lexical", view="compact")
        self.assertFalse(result["observations"])
        self.assertIn("no_hit", {row["code"] for row in result["gaps"]})
        # Literal requests can still search the indexed original word.
        literal = retrieve(self.root, self.run, 'Find "the"', mode="lexical", view="compact")
        self.assertEqual(len(literal["observations"]), 120)

    def test_explicit_paths_and_negations_survive_query_filtering(self):
        self.assertIn("is", query_terms("What is returned by /is?"))
        self.assertIn("not", query_terms("Which endpoint does not require a token?"))
        self.assertIn("the", query_terms('Find "the"'))

    def test_generated_page_locates_its_record_without_counting_twice(self):
        self.add([{"id": "F", "kind": "Fact", "summary": "Diagnostic needle", "observation_refs": ["O"]}],
                 [{"id": "O", "content": {"response": 403}}])
        with Corpus(self.root, self.run) as corpus:
            ranked, _ = rank(corpus, "Diagnostic needle", [])
            self.assertIn(("record", "F"), ranked)
            self.assertNotIn(("block", "WK-F/B-F"), ranked)
            exact, _ = rank(corpus, "", ["WK-F/B-F"])
            self.assertEqual(exact[0], ("block", "WK-F/B-F"))

    def test_snapshot_change_during_task_core_does_not_advance_cursor(self):
        self.pair()
        from context_views import task_core
        def changed(corpus, result):
            core = task_core(corpus, result)
            state = self.root / "state.json"
            state.write_text(state.read_text() + "\n")
            return core
        with patch("context_views.task_core", side_effect=changed):
            result = self.context(cursor="fresh")
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["delta"]["cursor_advanced"])
        self.assertFalse(result["records"])
        self.assertNotIn("task_core", result)
        self.assertFalse(list((self.root / "cache").glob("context-*.json")))

    def test_current_conditions_apply_to_read_and_candidate_requirements(self):
        self.pair()
        matching = self.context(question_ref="Q", current_conditions={"tenant": "lab-a"})
        self.assertEqual(matching["question_context"]["requirements"]["status"], "candidate_complete")
        changed = self.context(question_ref="Q", current_conditions={"tenant": "lab-b"})
        self.assertEqual(changed["question_context"]["requirements"]["status"], "unresolved")
        self.assertIn("current_condition_conflict", {row["code"] for row in changed["gaps"]})
        read = self.invoke("read", "--id", "P", "--current-conditions", '{"tenant":"lab-b"}')
        self.assertIn("current_condition_conflict", {row["code"] for row in read["issues"]})
        edges = self.invoke("discover", "--anchor", "Q", "--current-conditions", '{"tenant":"lab-b"}')
        self.assertFalse(edges["candidates"][0]["producer_usable"])
        # Query-scoped checks do not silently alter stored claims.
        with Corpus(self.root, self.run) as corpus:
            self.assertEqual(corpus.records["P"]["status"], "observed")

    def test_selected_json_values_survive_compact_and_pointer_reads(self):
        self.add([{"id": "Q", "kind": "Question", "summary": "Explain denial", "observation_refs": ["O"]}],
                 [{"id": "O", "excerpt_selectors": [{"pointer": "/response/body/error"}],
                   "content": {"actor_ref": "sample-role", "request": {"method": "POST", "url": "/login"},
                               "response": {"status": 403, "body": {"error": "CSRF token mismatch; old session_id",
                                                                       "allowed": False, "detail": "verbose " * 1000}}}}])
        result = self.context(mode="lexical")
        obs = result["observations"][0]
        self.assertEqual(obs["excerpts"][0]["value"], "CSRF token mismatch; old session_id")
        self.assertFalse(obs["excerpts"][0]["independent_observation"])
        self.assertNotIn("verbose", encode(result))
        read = self.invoke("read", "--id", "O", "--pointer", "/response/body/allowed")
        self.assertIs(read["package"]["observations"][0]["excerpts"][0]["value"], False)
        self.assertNotIn("verbose", encode(read))
        (self.root / "evidence/O.jsonl").write_text("{}\n")
        read = self.invoke("read", "--id", "O", "--pointer", "/response/body/error")
        self.assertFalse(read["package"]["observations"][0].get("excerpts"))
        self.assertNotEqual(read["status"], "ready")

    def test_exact_byte_excerpt_and_invalid_selector_before_publication(self):
        source = self.project / "raw.txt"
        original = "前提：仅租户A。\nCSRF token mismatch\n后续未验证。".encode()
        source.write_bytes(original)
        offset = original.index(b"CSRF")
        self.add([{"id": "Q", "kind": "Question", "observation_refs": ["O"]}],
                 [{"id": "O", "source_path": str(source), "content": {"result": "stored original"},
                   "excerpt_selectors": [{"offset": offset, "length": len(b"CSRF token mismatch")}]}])
        result = self.context(mode="lexical")
        excerpt = result["observations"][0]["excerpts"][0]
        self.assertEqual(excerpt["value"], "CSRF token mismatch")
        self.assertEqual(excerpt["selector"]["offset"], offset)
        self.assertEqual(excerpt["representation"], "source_bytes")
        before = (self.root / "state.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "existing value"):
            self.add(observations=[{"id": "BAD", "content": {"response": {}},
                                    "excerpt_selectors": [{"pointer": "/response/missing"}]}])
        self.assertEqual((self.root / "state.json").read_bytes(), before)
        self.assertFalse((self.root / "evidence/BAD.jsonl").exists())

    def test_json_pointer_preserves_types_escaping_and_array_boundaries(self):
        raw = {"a/b": {"~key": [None, False, 0, ""]}}
        for index, value in enumerate([None, False, 0, ""]):
            self.assertEqual(pointer_value(raw, f"/a~1b/~0key/{index}"), value)
        for pointer in ("/a~1b/~0key/-1", "/a~1b/~0key/04", "/a~1b/~0key/5", "/bad~2"):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                pointer_value(raw, pointer)


if __name__ == "__main__":
    unittest.main()
