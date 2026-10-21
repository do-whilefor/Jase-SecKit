"""Question-scoped source and prerequisite checks, never answer verification."""

from combinations import build_combinations
from discovery import _Sources, _refs


def assess_question(corpus, question_ref, result, *, mode):
    report = {"question_ref": question_ref, "assessment": "mechanical_checks_only",
              "evidence": False, "answer_support": "not_assessed",
              "source_observation_refs": [], "source_artifact_refs": [], "source_issues": [],
              "requirements": {"status": "not_checked"}, "next_actions": []}
    # Do not interpret missing packages or truncated plans as absent evidence.
    if (result["status"] == "unavailable" or result["budget"].get("omitted_units")
            or question_ref not in {row["id"] for row in result.get("records", [])}):
        report["source_issues"] = [{"code": "question_context_incomplete"}]
        report["next_actions"] = [{"command": "context", "question_ref": question_ref,
                                   "reason": "retrieve_complete_current_material"}]
        return report

    row = corpus.records[question_ref]
    checked = _Sources(corpus).inspect(question_ref)
    report["source_observation_refs"] = sorted(checked["observations"])
    report["source_artifact_refs"] = sorted(checked["artifacts"])
    report["source_issues"] = checked["issues"]
    report["declared_conditions"] = row.get("conditions", {})
    # These are navigation to competing claims, not automatic acceptance of them.
    competing = set(_refs(row.get("contradicts", [])))
    for issue in checked["issues"]:
        competing.update(issue.get("record_refs", []))
    report["competing_record_refs"] = sorted(competing)
    read_refs = sorted({question_ref, *checked["observations"], *checked["artifacts"], *competing})
    report["next_actions"].append({"command": "read", "ids": read_refs,
                                   "reason": "check_original_support_and_applicability"})
    if not checked["observations"] and not checked["artifacts"]:
        report["next_actions"].append({"command": "context", "mode": "lexical",
            "reason": "locate_existing_observations_before_requesting_new_experiment"})

    needs = row.get("capability", {}).get("needs", [])
    if not needs:
        report["requirements"] = {"status": "not_declared"}
    elif mode == "lexical":
        report["requirements"] = {"status": "not_checked", "declared_count": len(needs)}
        report["next_actions"].append({"command": "context", "mode": "combined",
            "question_ref": question_ref, "reason": "check_declared_prerequisites"})
    else:
        chain = result["chain_discovery"]
        combination = next((item for item in chain["combinations"]
                            if item["consumer_ref"] == question_ref), None)
        if combination is None:
            # Reuse the same recursive AND/OR planner for a single input too.
            combination = build_combinations(corpus.records, chain["candidates"],
                                             [question_ref], minimum_inputs=1)[0]
        plan = combination["plan"]
        report["requirements"] = {
            "status": "candidate_complete" if plan["coverage"]["complete"] else "unresolved",
            "coverage": plan["coverage"], "candidate_record_refs": combination["record_refs"],
            "missing_preconditions": plan["missing_preconditions"],
            "conflicts": plan["conflicts"], "unknown_conditions": plan["unknown_conditions"],
            "selection": plan["selection"], "evidence": False}
        for gap in plan["missing_preconditions"]:
            report["next_actions"].append({"command": "discover", "anchor": gap["record_ref"],
                "query": gap["type"], "need_index": gap["need_index"],
                "reason": "inspect_missing_input_and_alternatives"})
        report["next_actions"].append({"command": "read", "ids": combination["record_refs"],
            "reason": "verify_actual_consumption_and_joint_conditions"})
    return report
