"""Evidence-gated triage and CVSS reporting; no scanning or keyword filtering."""
from __future__ import annotations

from cvss31 import calculate


CLAIM_COLLECTIONS = ("identities", "prerequisites", "steps", "observed_results", "supported_impact")
TRIAGE_BASIS = ("boundary", "reproducibility", "impact")
BASE_METRICS = ("AV", "AC", "PR", "UI", "S", "C", "I", "A")
FILTER_RULES = {f"F{number}" for number in range(1, 9)}


def validate_shapes(case, need, strs):
    """Reject uninterpretable shapes, leaving incomplete declarations reviewable."""
    if "triage" in case:
        triage = need(case["triage"], dict, "case.triage")
        for key in ("status", "reason"):
            if key in triage:
                need(triage[key], str, f"case.triage.{key}")
        if "matched_rules" in triage:
            strs(triage["matched_rules"], "case.triage.matched_rules")
        if "basis" in triage:
            basis = need(triage["basis"], dict, "case.triage.basis")
            for key, refs in basis.items():
                strs(refs, f"case.triage.basis.{key}")
    if "cvss31" in case:
        cvss = need(case["cvss31"], dict, "case.cvss31")
        if cvss.get("vector") is not None:
            need(cvss["vector"], str, "case.cvss31.vector")
        if "reason" in cvss:
            need(cvss["reason"], str, "case.cvss31.reason")
        if "rationale" in cvss:
            rationale = need(cvss["rationale"], dict, "case.cvss31.rationale")
            for metric, entry in rationale.items():
                entry = need(entry, dict, f"case.cvss31.rationale.{metric}")
                if "reason" in entry:
                    need(entry["reason"], str, f"case.cvss31.rationale.{metric}.reason")
                if "claim_refs" in entry:
                    strs(entry["claim_refs"], f"case.cvss31.rationale.{metric}.claim_refs")


def assess(case, materials, located, add):
    """Return checked declarations, never decide vulnerability truth from text."""
    claims = {}
    duplicate_ids = set()
    for collection in CLAIM_COLLECTIONS:
        for claim in case[collection]:
            if claim["id"] in claims:
                duplicate_ids.add(claim["id"])
            claims[claim["id"]] = claim
    semantic = case["semantic_review"]
    reviewed = set(semantic["reviewed_evidence_refs"])

    def check_claim_refs(refs, path, prefix):
        valid = bool(refs)
        if not refs:
            add(prefix + "_basis_missing", "warning", path, "缺少已观察事实引用，需要补充可定位的依据。")
        if len(refs) != len(set(refs)):
            valid = False
            add(prefix + "_duplicate_claim_ref", "error", path, "事实引用重复，需逐项核对。")
        for index, ref in enumerate(refs):
            ref_path = f"{path}[{index}]"
            claim = claims.get(ref)
            if claim is None or ref in duplicate_ids or not ref.strip():
                valid = False
                add(prefix + "_unknown_claim", "error", ref_path, "引用的事实不存在、编号为空或编号不唯一。")
                continue
            if claim["verification"] != "observed" or not claim["text"].strip():
                valid = False
                add(prefix + "_claim_not_observed", "warning", ref_path, "依据必须是内容非空的已观察事实；推测、未验证或冲突项不能作为通过依据。")
            evidence_refs = claim["evidence_refs"]
            if (not evidence_refs or len(evidence_refs) != len(set(evidence_refs))
                    or any(evidence not in materials or evidence not in located for evidence in evidence_refs)):
                valid = False
                add(prefix + "_evidence_invalid", "warning", ref_path, "依据缺少有效、已登记且可定位的证据引用。")
            if semantic["status"] != "completed" or not set(evidence_refs).issubset(reviewed):
                valid = False
                add(prefix + "_semantic_review_required", "warning", ref_path, "宿主需完成原件语义复核并覆盖此项引用的证据。")
        return valid

    triage = case.get("triage")
    declared = triage.get("status", "pending") if triage else "pending"
    passed = False
    if triage is None:
        add("triage_pending", "warning", "case.triage", "旧案例尚未进行漏洞筛选；当前输出仅为未筛选的平台草稿。")
    else:
        valid = True
        if declared not in {"pending", "lead", "supported"}:
            valid = False
            add("triage_status_invalid", "error", "case.triage.status", "筛选状态必须为 pending、lead 或 supported。")
        if not triage.get("reason", "").strip():
            valid = False
            add("triage_reason_missing", "warning", "case.triage.reason", "请说明筛选结论、已证实的边界或具体缺失的证据。")
        rules = triage.get("matched_rules", [])
        if "matched_rules" not in triage or any(rule not in FILTER_RULES for rule in rules) or len(rules) != len(set(rules)):
            valid = False
            add("triage_rules_invalid", "error", "case.triage.matched_rules", "需提供不重复的 F1–F8 规则编号数组；未命中规则用空数组。")
        basis = triage.get("basis", {})
        if set(basis) != set(TRIAGE_BASIS):
            valid = False
            add("triage_basis_invalid", "error", "case.triage.basis", "筛选依据需包含 boundary、reproducibility、impact 三个引用数组。")
        for category in TRIAGE_BASIS:
            refs = basis.get(category, [])
            if declared == "supported" or refs:
                valid = check_claim_refs(refs, f"case.triage.basis.{category}", "triage") and valid
        passed = declared == "supported" and valid
        if declared == "lead":
            add("triage_lead", "warning", "case.triage", "当前仅为线索，尚不足以认定漏洞；按筛选理由补证，不能据此断言不存在漏洞。")
        elif declared == "pending":
            add("triage_pending", "warning", "case.triage", "漏洞筛选尚未完成；需核对安全边界、可复现性和实际影响。")
        elif declared == "supported" and not passed:
            add("triage_not_supported", "warning", "case.triage", "支持声明的依据不完整，暂按线索记录处理并补证。")
    triage_result = {"status": declared, "passed": passed, "explicit": "triage" in case}

    cvss = case.get("cvss31")
    if cvss is None:
        if declared != "lead":
            add("cvss_pending", "warning", "case.cvss31", "CVSS 3.1 Base 尚待评估；缺少依据时留空，不能用 0 分代替。")
        return triage_result, None
    reason_valid = bool(cvss.get("reason", "").strip())
    if not reason_valid:
        add("cvss_reason_missing", "warning", "case.cvss31.reason", "请说明评分依据，或无法评分的具体证据缺口。")
    vector = cvss.get("vector")
    rationale = cvss.get("rationale", {})
    if vector is None:
        if rationale:
            add("cvss_pending_rationale", "warning", "case.cvss31.rationale", "待评估状态应使用空 rationale；补齐全部指标后再提供完整向量。")
        if declared != "lead":
            add("cvss_pending", "warning", "case.cvss31", "CVSS 3.1 Base 待评估；请按评分说明补充证据。")
        return triage_result, None
    try:
        calculated = calculate(vector)
    except ValueError:
        add("cvss_vector_invalid", "error", "case.cvss31.vector", "CVSS 向量无效；只接受完整、无重复及未知指标的 CVSS:3.1 Base 向量。")
        return triage_result, None
    valid = reason_valid
    if set(rationale) - set(BASE_METRICS):
        valid = False
        add("cvss_metric_unknown", "error", "case.cvss31.rationale", "指标依据含 Base 八项指标之外的名称。")
    for metric in BASE_METRICS:
        entry = rationale.get(metric, {})
        path = f"case.cvss31.rationale.{metric}"
        if not entry.get("reason", "").strip():
            valid = False
            add("cvss_metric_reason_missing", "warning", path + ".reason", "此指标缺少非空取值说明。")
        valid = check_claim_refs(entry.get("claim_refs", []), path + ".claim_refs", "cvss") and valid
    if not passed:
        add("cvss_triage_required", "warning", "case.cvss31", "漏洞筛选尚未获得三类已复核依据支持，暂不输出数值评分。")
    return triage_result, calculated if passed and valid else None
