"""
Routing decision — config/underwriting.yaml thresholds.

KEY CHANGE: DSCR / DTI being None (data unavailable) is NOT a block for STP.
The underwriter sees it as "data not in docs — verify manually", but it does not
automatically push to MANUAL_REVIEW unless both are explicitly failing.

Routing:
  delinq=True OR combined_score < min  → MANUAL_REVIEW
  dscr_ok is False (computed & fails)  → MANUAL_REVIEW
  dti_ok  is False (computed & fails)  → MANUAL_REVIEW
  DSCR/DTI unavailable                 → noted in rationale (not a hard fail)
  OpenAI recommends DECLINE            → MANUAL_REVIEW (underwriter makes final call)
  ALL PASS                             → STP
  Pre-screen hard fail                 → DECLINED
"""

from __future__ import annotations

from typing import Any

from services.config_loader import load_underwriting
from services.logger import get_logger
from models.graph_state import UnderwritingState

log = get_logger(__name__)


def run(state: UnderwritingState) -> dict[str, Any]:
    if state.get("decision") == "DECLINED":
        return {"decision": "DECLINED", "stage": "decision"}

    cfg = load_underwriting()
    score_min = float(cfg.get("credit", {}).get("score_min", 650))
    ratios_cfg = cfg.get("ratios", {})
    dscr_min = float(ratios_cfg.get("dscr_min", 1.25))
    dti_max = float(ratios_cfg.get("dti_max", 0.4))

    ratios = state.get("ratios") or {}
    credit_result = state.get("credit_result") or {}
    delinquency = state.get("delinquency") or {}
    llm_assessment = state.get("llm_credit_assessment") or {}
    hard_errors = [e for e in (state.get("errors") or []) if "DSCR" in e or "DTI" in e or "premium" in e or "Age" in e]

    is_delinquent = bool(delinquency.get("is_delinquent", False))
    combined_score = float(credit_result.get("combined_score", 0))
    dscr_ok = ratios.get("dscr_ok")   # True, False, or None (unavailable)
    dti_ok  = ratios.get("dti_ok")    # True, False, or None (unavailable)
    llm_rec = (llm_assessment.get("recommendation") or "").upper()

    review_reasons: list[str] = []
    info_notes: list[str] = list(ratios.get("info_notes") or [])

    # Hard failures
    if is_delinquent:
        review_reasons.append(f"Delinquency detected ({delinquency.get('delinquency_count', 0)} flag(s)).")
    if combined_score < score_min:
        review_reasons.append(f"Credit score {combined_score:.0f} < minimum {score_min:.0f}.")
    if dscr_ok is False:
        review_reasons.append(f"DSCR {ratios.get('dscr', '—')} < minimum {dscr_min}.")
    if dti_ok is False:
        review_reasons.append(f"DTI {ratios.get('dti', 0):.1%} > maximum {dti_max:.0%}.")
    if llm_rec == "DECLINE":
        review_reasons.append(f"OpenAI credit model recommends DECLINE (grade {llm_assessment.get('credit_grade', '—')}).")
    if hard_errors:
        review_reasons.append(f"{len(hard_errors)} validation error(s) in pipeline.")

    # Informational unavailability — not hard failures
    if dscr_ok is None:
        info_notes.append("DSCR unavailable — data not in documents (not counted as a failure).")
    if dti_ok is None:
        info_notes.append("DTI unavailable — data not in documents (not counted as a failure).")

    # Classify decision:
    # STP               — all checks pass
    # CONDITIONAL_APPROVAL — only financial ratio gaps (DSCR/DTI/LLM-model),
    #                        no delinquency and credit score passes
    # MANUAL_REVIEW     — delinquency present OR credit score below minimum
    # DECLINED          — pre-screen hard fail (set upstream)
    critical_failures = [r for r in review_reasons if
                         "Delinquency" in r or "Credit score" in r]
    soft_failures     = [r for r in review_reasons if r not in critical_failures]

    if not review_reasons:
        decision = "STP"
    elif critical_failures:
        decision = "MANUAL_REVIEW"
    else:
        # Only soft ratio/model failures — conditionally approve with conditions
        decision = "CONDITIONAL_APPROVAL"

    checks = {
        "delinquency_clear": {
            "ok": not is_delinquent,
            "status": "pass" if not is_delinquent else "fail",
            "flags": delinquency.get("risk_flags", []),
        },
        "credit_score": {
            "ok": combined_score >= score_min,
            "status": "pass" if combined_score >= score_min else "fail",
            "value": combined_score,
            "min": score_min,
            "grade": delinquency.get("credit_grade") or llm_assessment.get("credit_grade"),
        },
        "dscr": {
            "ok": dscr_ok,
            "status": "pass" if dscr_ok is True else ("fail" if dscr_ok is False else "not_available"),
            "value": ratios.get("dscr"),
            "min": dscr_min,
            "note": ratios.get("dscr_status"),
        },
        "dti": {
            "ok": dti_ok,
            "status": "pass" if dti_ok is True else ("fail" if dti_ok is False else "not_available"),
            "value": ratios.get("dti"),
            "max": dti_max,
            "note": ratios.get("dti_status"),
        },
        "openai_recommendation": {
            "ok": llm_rec in ("APPROVE", ""),
            "status": llm_rec or "not_available",
            "confidence": llm_assessment.get("confidence"),
            "grade": llm_assessment.get("credit_grade"),
        },
    }

    log.info("decision_done")
    return {
        "decision": decision,
        "review_reasons": review_reasons,
        "info_notes": info_notes,
        "policy_preview": {
            "checks": checks,
            "merged_applicant": state.get("merged_applicant") or {},
            "bank_profile": state.get("bank_profile") or {},
            "llm_credit_assessment": llm_assessment,
            "delinquency": delinquency,
            "ratios": ratios,
            "credit_result": credit_result,
        },
        "stage": "decision",
    }
