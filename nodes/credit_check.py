"""
Credit check node — combines bureau score (mock/live) with ML delinquency credit_score.
All endpoints and thresholds from config/credit.yaml + config/underwriting.yaml.
"""

from __future__ import annotations

from typing import Any

from services.config_loader import load_underwriting
from services.credit_client import pull_credit_primary
from services.logger import get_logger
from models.graph_state import UnderwritingState

log = get_logger(__name__)


def _combined_score(bureau_score: float, ml_score: float, bureau_weight: float = 0.5) -> float:
    """Weighted average of bureau and ML credit scores (both on 300-850 scale)."""
    ml_w = 1.0 - bureau_weight
    return round(bureau_weight * bureau_score + ml_w * ml_score, 1)


def run(state: UnderwritingState) -> dict[str, Any]:
    cfg = load_underwriting()
    score_min = float(cfg.get("credit", {}).get("score_min", 650))
    errors: list[str] = []

    try:
        bureau = pull_credit_primary()
    except Exception as e:
        errors.append(f"Bureau pull failed (using mock fallback): {e}")
        bureau = {"bureau": "fallback_mock", "score": 720.0, "adverse_flags": [], "mock": True}

    bureau_score = float(bureau.get("score", 720.0))
    ml_credit_score = float((state.get("delinquency") or {}).get("credit_score", bureau_score))

    combined = _combined_score(bureau_score, ml_credit_score)
    adverse = list(bureau.get("adverse_flags") or [])
    is_delinquent = bool((state.get("delinquency") or {}).get("is_delinquent", False))
    if is_delinquent:
        adverse.append("ml_delinquency_detected")

    score_ok = combined >= score_min and not is_delinquent

    if combined < score_min:
        errors.append(f"Combined credit score {combined:.0f} < minimum {score_min:.0f}.")
    if is_delinquent:
        errors.append("Delinquency detected in bank statement — credit check failed.")

    credit_result = {
        "bureau_score": bureau_score,
        "ml_credit_score": ml_credit_score,
        "combined_score": combined,
        "score_min": score_min,
        "score_ok": score_ok,
        "adverse_flags": adverse,
        "bureau": bureau.get("bureau"),
        "mock": bureau.get("mock", True),
    }

    log.info("credit_check_done")
    out: dict[str, Any] = {"credit_result": credit_result, "stage": "credit_check"}
    if errors:
        out["errors"] = errors
    return out
