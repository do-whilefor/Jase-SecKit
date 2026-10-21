"""Behavioral tests for honest, session-wide capability expression review."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capability_hints
from capability_hints import build_type_reviews
from discovery import discover


def spec(kind, *, aliases=(), description="", **constraints):
    return {"type": kind, "aliases": list(aliases), "description": description,
            "constraints": constraints}


def record(rid, *, provides=(), needs=(), summary="", **extra):
    return {"id": rid, "kind": "Capability", "status": "verified", "summary": summary,
            "capability": {"provides": list(provides), "needs": list(needs)}, **extra}


def corpus(*rows):
    return {row["id"]: row for row in rows}


class CorpusFixture:
    def __init__(self, records):
        self.records = records
        self.pages, self.blocks, self.observations = {}, {}, {}


class CapabilityHintsTests(unittest.TestCase):
    def test_distinct_credentials_are_reviewed_without_becoming_a_match(self):
        records = corpus(record("earlier", provides=[spec("login credential")]),
                         record("current", needs=[spec("download credential")]))
        original = deepcopy(records)
        reviews = build_type_reviews(records, ["current"])
        self.assertEqual(len(reviews), 1)
        review = reviews[0]
        self.assertEqual(review["id"], "type-review:current:0")
        self.assertEqual(review["record_refs"], ["current", "earlier"])
        self.assertEqual(review["assessment"], "review_required")
        self.assertFalse(review["evidence"])
        suggestion = review["suggestions"][0]
        self.assertEqual(suggestion["matched_terms"], ["credential"])
        self.assertEqual(suggestion["record_refs"], ["earlier", "current"])
        self.assertEqual(suggestion["assessment"], "review_required")
        self.assertFalse(suggestion["evidence"])
        self.assertEqual(discover(CorpusFixture(records), anchors=["current"])["candidates"], [])
        self.assertEqual(records, original)

    def test_exact_type_and_alias_matches_use_discovery_normalization(self):
        for provide, need in [
            (spec("EXPORT_job-id"), spec("export job id")),
            (spec("ＪＯＢ＿ＩＤ"), spec("job id")),
            (spec("job id", aliases=["任务标识"]), spec("任务标识")),
            (spec("job id"), spec("任务标识", aliases=["JOB-ID"])),
            (spec("export handle", aliases=["shared id"]),
             spec("job reference", aliases=["SHARED_ID"])),
        ]:
            with self.subTest(provide=provide, need=need):
                records = corpus(record("a", provides=[provide]), record("b", needs=[need]))
                self.assertEqual(build_type_reviews(records, ["b"]), [])

    def test_explicit_alias_resolves_review_without_changing_its_stable_id_beforehand(self):
        records = corpus(record("a", provides=[spec("export reference")]),
                         record("b", needs=[spec("download reference")]))
        initial = build_type_reviews(records, ["b"])[0]
        records["a"]["summary"] = "Additional description for an export reference"
        records["a"]["revision"] = 2
        self.assertEqual(build_type_reviews(records, ["b"])[0]["id"], initial["id"])
        records["a"]["capability"]["provides"][0]["aliases"].append("download reference")
        self.assertEqual(build_type_reviews(records, ["b"]), [])

    def test_matching_unusable_corrected_or_conflicting_sources_are_not_type_gaps(self):
        for state in ({"status": "refuted"}, {"status": "needs_review"},
                      {"corrected_by": ["correction"]}, {"evidence_refs": ["missing"]},
                      {"observation_refs": ["unavailable"]}, {}):
            with self.subTest(state=state):
                records = corpus(record("a", provides=[spec("credential", tenant="other")], **state),
                                 record("b", needs=[spec("credential", tenant="current")]))
                self.assertEqual(build_type_reviews(records, ["b"]), [])

    def test_refuted_exact_match_allows_review_of_a_different_type_without_an_edge(self):
        records = corpus(
            record("B", provides=[spec("download-grant")], status="refuted",
                   corrected_by=["revocation"]),
            record("revocation", contradicts=["B"]),
            record("C", needs=[spec("download-grant")]),
            record("D", provides=[spec("short-lived-pass", description="download grant")]),
        )
        original = deepcopy(records)
        candidates = discover(CorpusFixture(records), anchors=["C"])["candidates"]
        original_candidates = deepcopy(candidates)
        self.assertEqual([edge["producer_ref"] for edge in candidates], ["B"])
        self.assertFalse(candidates[0]["producer_usable"])
        review = build_type_reviews(records, ["C"], candidates=candidates)[0]
        self.assertEqual(review["reason"], "all_complete_matches_unusable_review_alternatives")
        self.assertIn("not a missing-type finding", review["message"])
        self.assertEqual(review["assessment"], "review_required")
        self.assertFalse(review["evidence"])
        self.assertEqual([item["producer_ref"] for item in review["suggestions"]], ["D"])
        self.assertEqual(review["suggestions"][0]["matched_terms"], ["download", "grant"])
        self.assertEqual(review["record_refs"], ["C", "D"])
        self.assertEqual(records, original)
        self.assertEqual(candidates, original_candidates)
        records["D"]["capability"]["provides"][0]["aliases"].append("download-grant")
        fresh = discover(CorpusFixture(records), anchors=["C"])["candidates"]
        self.assertEqual(build_type_reviews(records, ["C"], candidates=fresh), [])

    def test_explicit_conflict_allows_alternative_expression_review(self):
        records = corpus(
            record("B", provides=[spec("download-grant", tenant="other")]),
            record("C", needs=[spec("download-grant", tenant="current")]),
            record("D", provides=[spec("short-lived-pass", description="download grant", tenant="current")]),
        )
        candidates = discover(CorpusFixture(records), anchors=["C"])["candidates"]
        self.assertEqual(candidates[0]["compatibility"], "incompatible")
        review = build_type_reviews(records, ["C"], candidates=candidates)[0]
        self.assertEqual(review["reason"], "all_complete_matches_unusable_review_alternatives")
        self.assertEqual([item["producer_ref"] for item in review["suggestions"]], ["D"])
        self.assertEqual(review["suggestions"][0]["conflicts"], [])

    def test_an_usable_unknown_or_compatible_exact_match_keeps_existing_behavior(self):
        records = corpus(
            record("B", provides=[spec("download-grant")], status="refuted"),
            record("C", needs=[spec("download-grant")]),
            record("D", provides=[spec("short-lived-pass", description="download grant")]),
            record("E", provides=[spec("download-grant")]),
        )
        candidates = discover(CorpusFixture(records), anchors=["C"])["candidates"]
        usable = next(edge for edge in candidates if edge["producer_ref"] == "E")
        self.assertEqual(usable["compatibility"], "unknown")
        self.assertTrue(usable["producer_usable"])
        self.assertEqual(build_type_reviews(records, ["C"], candidates=candidates), [])
        usable["compatibility"] = "compatible"
        self.assertEqual(build_type_reviews(records, ["C"], candidates=candidates), [])
        incomplete = [edge for edge in candidates if edge["producer_ref"] != "E"]
        self.assertEqual(build_type_reviews(records, ["C"], candidates=incomplete), [])

    def test_missing_diagnostics_or_unusable_consumer_do_not_trigger_alternative_review(self):
        records = corpus(
            record("B", provides=[spec("download-grant")], status="refuted"),
            record("C", needs=[spec("download-grant")]),
            record("D", provides=[spec("short-lived-pass", description="download grant")]),
        )
        candidates = discover(CorpusFixture(records), anchors=["C"])["candidates"]
        self.assertEqual(build_type_reviews(records, ["C"]), [])
        self.assertEqual(build_type_reviews(records, ["C"], candidates=[]), [])
        edge = candidates[0]
        for field in ("consumer_usable", "producer_usable", "compatibility", "need_index", "provide_index"):
            with self.subTest(missing=field):
                partial = {key: value for key, value in edge.items() if key != field}
                self.assertEqual(build_type_reviews(records, ["C"], candidates=[partial]), [])
        for changed in ({"consumer_usable": False}, {"compatibility": "unrecognized"},
                        {"consumer_ref": "other"}, {"need_index": 99}, {"provide_index": 99}):
            with self.subTest(changed=changed):
                self.assertEqual(build_type_reviews(records, ["C"], candidates=[{**edge, **changed}]), [])

    def test_diagnostic_coverage_includes_every_matching_output_from_the_same_provider(self):
        records = corpus(
            record("B", provides=[spec("download-grant", tenant="other"),
                                  spec("DOWNLOAD_GRANT", tenant="current")]),
            record("C", needs=[spec("download-grant", tenant="current")]),
            record("D", provides=[spec("short-lived-pass", description="download grant")]),
        )
        candidates = discover(CorpusFixture(records), anchors=["C"])["candidates"]
        only_conflicting = [edge for edge in candidates if edge["provide_index"] == 0]
        self.assertEqual(len(only_conflicting), 1)
        self.assertEqual(build_type_reviews(records, ["C"], candidates=only_conflicting), [])
        self.assertEqual(build_type_reviews(records, ["C"], candidates=candidates), [])

    def test_unusable_exact_match_without_lexical_alternative_stays_an_honest_empty_prompt(self):
        records = corpus(record("B", provides=[spec("download-grant")], status="refuted"),
                         record("C", needs=[spec("download-grant")]),
                         record("D", provides=[spec("unrelated session")]))
        candidates = discover(CorpusFixture(records), anchors=["C"])["candidates"]
        review = build_type_reviews(records, ["C"], candidates=candidates)[0]
        self.assertEqual(review["reason"], "all_complete_matches_unusable_review_alternatives")
        self.assertEqual(review["suggestions"], [])
        self.assertIn("No lexical connection was found", review["message"])
        self.assertIn("obtain a new capability", review["message"])

    def test_only_focused_consumers_but_full_session_providers_are_considered(self):
        records = corpus(record("round-2", provides=[spec("old export reference")]),
                         record("round-30", needs=[spec("download reference")]),
                         record("unrelated", needs=[spec("totally absent")]))
        review = build_type_reviews(records, ["round-30", "missing"])[0]
        self.assertEqual(review["consumer_ref"], "round-30")
        self.assertEqual(review["suggestions"][0]["producer_ref"], "round-2")
        self.assertEqual(len(build_type_reviews(records, ["round-30"])), 1)
        self.assertEqual(build_type_reviews(records, []), [])
        self.assertEqual(build_type_reviews(records, ["round-2"]), [])

    def test_own_output_does_not_satisfy_or_suggest_its_own_input(self):
        records = corpus(record("cycle", provides=[spec("access credential")],
                                needs=[spec("ACCESS-CREDENTIAL")]))
        review = build_type_reviews(records, ["cycle"])[0]
        self.assertEqual(review["suggestions"], [])
        self.assertEqual(review["record_refs"], ["cycle"])

    def test_chinese_descriptions_and_english_record_text_supply_visible_terms(self):
        records = corpus(
            record("cn", provides=[spec("号码", description="创建导出任务后取得编号")]),
            record("english", provides=[spec("handle")], summary="ＤＯＷＮＬＯＡＤ receipt"),
            record("consumer", needs=[spec("输入凭据", description="下载导出任务的产物 download")],
                   summary="download input"),
        )
        suggestions = {row["producer_ref"]: row for row in
                       build_type_reviews(records, ["consumer"])[0]["suggestions"]}
        self.assertIn("导出", suggestions["cn"]["matched_terms"])
        self.assertIn("任务", suggestions["cn"]["matched_terms"])
        self.assertEqual(suggestions["english"]["matched_terms"], ["download"])

    def test_another_input_in_consumer_summary_does_not_pollute_the_missing_input(self):
        records = corpus(
            record("job", provides=[spec("export-job-id")], summary="Synthetic export job observed"),
            record("consumer", needs=[spec("export-job-id"), spec("download-grant")],
                   summary="Synthetic consumer requires an export job and download grant"),
        )
        review = build_type_reviews(records, ["consumer"])[0]
        self.assertEqual(review["need_index"], 1)
        self.assertEqual(review["suggestions"], [])

    def test_partial_alias_terms_split_separators_and_keep_the_provide_index(self):
        records = corpus(record("a", provides=[spec("heartbeat"),
                                                spec("opaque", aliases=["ＥＸＰＯＲＴ_JOB-ID"])]),
                         record("b", needs=[spec("download/id")]))
        suggestions = build_type_reviews(records, ["b"])[0]["suggestions"]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["provide_index"], 1)
        self.assertEqual(suggestions[0]["type"], "opaque")
        self.assertEqual(suggestions[0]["matched_terms"], ["id"])

    def test_lexical_suggestion_keeps_conflicts_and_unusable_status_visible(self):
        records = corpus(record("a", provides=[spec("login credential", tenant="other")],
                                status="refuted"),
                         record("b", needs=[spec("download credential", tenant="current", scope="one")]))
        suggestion = build_type_reviews(records, ["b"])[0]["suggestions"][0]
        self.assertEqual(suggestion["producer_status"], "refuted")
        self.assertEqual(suggestion["conditions"]["provided"], {"tenant": "other"})
        self.assertEqual(suggestion["conflicts"],
                         [{"constraint": "tenant", "provided": "other", "required": "current"}])
        self.assertEqual(suggestion["unknown_conditions"][0]["constraint"], "scope")
        self.assertFalse(suggestion["evidence"])

    def test_no_lexical_association_is_an_honest_empty_prompt(self):
        records = corpus(record("a", provides=[spec("opaque handle")]),
                         record("b", needs=[spec("访问凭据")]))
        review = build_type_reviews(records, ["b"])[0]
        self.assertEqual(review["suggestions"], [])
        self.assertIn("No lexical connection", review["message"])
        self.assertIn("check the capability expression", review["message"])
        self.assertIn("obtain a new capability", review["message"])
        self.assertEqual(review["record_refs"], ["b"])

    def test_all_alternatives_and_need_indexes_are_deterministic(self):
        records = corpus(*[record(f"p-{i:03}", provides=[spec("export reference")]) for i in range(120)],
                         record("b", needs=[spec("download reference"), spec("session reference")]))
        result = build_type_reviews(records, ["b", "b"])
        self.assertEqual([row["need_index"] for row in result], [0, 1])
        self.assertTrue(all(len(row["suggestions"]) == 120 for row in result))
        reversed_records = dict(reversed(list(records.items())))
        self.assertEqual(result, build_type_reviews(reversed_records, ["b"]))

    def test_provider_text_is_preprocessed_once_across_many_unmatched_needs(self):
        long_summary = "provider-only " * 5000 + "receipt"
        records = corpus(record("a", provides=[spec("source handle"), spec("opaque token")],
                                summary=long_summary),
                         record("b", needs=[spec(f"destination {i} receipt") for i in range(40)]))
        with patch.object(capability_hints, "_terms", wraps=capability_hints._terms) as tokenize:
            result = build_type_reviews(records, ["b"])
        self.assertEqual(len(result), 40)
        self.assertEqual(sum(call.args == (long_summary,) for call in tokenize.call_args_list), 1)
        self.assertTrue(all(len(row["suggestions"]) == 2 for row in result))


if __name__ == "__main__":
    unittest.main()
