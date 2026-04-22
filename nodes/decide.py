"""Policy decision: STP vs manual queue using YAML risk bands."""

from __future__ import annotations

from typing import Any

from services.config_loader import load_rules
from services.logger import get_logger
from models.graph_state import UnderwritingState

log = get_logger(__name__)


def run(state: UnderwritingState) -> dict[str, Any]:
    rules = load_rules()
    metrics = state.get("metrics") or {}
    credit = state.get("credit") or {}
    errors = list(state.get("errors") or [])

    dscr = metrics.get("dscr")
    dti = metrics.get("dti_percent")
    ml_score = float(metrics.get("ml_score", 1.0))

    min_dscr = float(rules.get("dscr", {}).get("minimum", 0))
    max_dti = float(rules.get("dti", {}).get("maximum_percent", 100))

    stp_band = str(rules.get("stp_risk_band", "low"))
    bands = rules.get("risk_bands", {}) or {}
    low_cfg = bands.get(stp_band, {})
    max_ml_stp = float(low_cfg.get("max_ml_score", 0.35))
    need_clear = bool(low_cfg.get("require_credit_clear", False))

    dscr_ok = dscr is None or float(dscr) >= min_dscr
    dti_ok = dti is None or float(dti) <= max_dti
    credit_ok = True
    if need_clear:
        flags = credit.get("adverse_flags") or []
        credit_ok = len(flags) == 0

    ml_ok = ml_score <= max_ml_stp

    policy_preview = {
        "checks": {
            "dscr_rule": {"minimum": min_dscr, "value": dscr, "ok": dscr_ok},
            "dti_rule": {"maximum_percent": max_dti, "value": dti, "ok": dti_ok},
            "ml_rule": {"max_for_stp": max_ml_stp, "value": ml_score, "ok": ml_ok},
            "credit_clear": {"required": need_clear, "ok": credit_ok},
        },
        "merged_applicant": state.get("merged_applicant") or {},
        "credit": credit,
    }

    hard_decline = state.get("decision") == "DECLINED"
    if hard_decline:
        return {"decision": "DECLINED", "policy_preview": policy_preview, "stage": "decide"}

    if errors:
        return {
            "decision": "MANUAL_REVIEW",
            "policy_preview": policy_preview,
            "stage": "decide",
        }

    if dscr_ok and dti_ok and ml_ok and credit_ok:
        return {"decision": "STP", "policy_preview": policy_preview, "stage": "decide"}

    return {"decision": "MANUAL_REVIEW", "policy_preview": policy_preview, "stage": "decide"}
