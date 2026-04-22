"""DSCR / DTI / ML + bureau pull — thresholds from YAML."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from services.config_loader import load_rules
from services.credit_client import pull_credit_primary
from services.logger import get_logger
from services.ml_risk import build_feature_row, predict_risk_score
from services.risk_math import compute_dscr, compute_dti_percent
from models.graph_state import UnderwritingState

log = get_logger(__name__)


def _parse_dob(s: str | None) -> date | None:
    if not s or not isinstance(s, str):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def run(state: UnderwritingState) -> dict[str, Any]:
    rules = load_rules()
    merged = dict(state.get("merged_applicant") or {})
    errors: list[str] = []

    dscr = compute_dscr(merged, rules)
    dti = compute_dti_percent(merged, rules)

    try:
        credit = pull_credit_primary()
    except Exception as e:
        errors.append(f"Credit pull failed: {e}")
        credit = {"bureau": "none", "score": 0.0, "adverse_flags": ["credit_unavailable"], "mock": True}
    score = float(credit.get("score", 0.0))

    row = build_feature_row(dscr, dti, score, merged)
    ml_score, ml_src = predict_risk_score(row)

    df = pd.DataFrame([{**row, "ml_score": ml_score, "dscr": dscr, "dti_percent": dti}])
    log.info(
        "pandas_metrics_snapshot",
    )

    metrics: dict[str, Any] = {
        "dscr": dscr,
        "dti_percent": dti,
        "ml_score": ml_score,
        "ml_source": ml_src,
        "feature_row": row,
        "dataframe_rows": int(len(df)),
    }

    # Validate premium and age from merged when present
    min_zar = float(rules.get("premium", {}).get("min_zar", 0))
    prem = merged.get("proposed_annuity_premium_zar")
    if prem is not None:
        try:
            if float(prem) < min_zar:
                errors.append(f"Extracted premium below minimum {min_zar} ZAR.")
        except (TypeError, ValueError):
            errors.append("Invalid extracted proposed_annuity_premium_zar.")

    dob = _parse_dob(merged.get("date_of_birth"))
    age_min = int(rules.get("age", {}).get("min", 0))
    age_max = int(rules.get("age", {}).get("max", 999))
    if dob is not None:
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < age_min or age > age_max:
            errors.append(f"Age {age} outside allowed range.")

    le_cfg = (rules.get("life_expectancy") or {})
    if le_cfg.get("enabled") and le_cfg.get("field_name"):
        le = merged.get(le_cfg["field_name"])
        min_years = float(le_cfg.get("min_years_remaining", 0))
        if le is not None:
            try:
                if float(le) < min_years:
                    errors.append("Life expectancy below configured minimum.")
            except (TypeError, ValueError):
                pass

    sb_cfg = rules.get("spouse_benefit") or {}
    fn = sb_cfg.get("field_name")
    if fn and merged.get(fn) is not None:
        try:
            p = float(merged[fn])
            lo = float(sb_cfg.get("min_percent", 0))
            hi = float(sb_cfg.get("max_percent", 100))
            if p < lo or p > hi:
                errors.append("Spouse benefit percent outside allowed band.")
        except (TypeError, ValueError):
            errors.append("Invalid spouse benefit percent.")

    out: dict[str, Any] = {
        "metrics": metrics,
        "credit": credit,
        "ml": {"score": ml_score, "source": ml_src},
        "stage": "compute_risk",
    }
    if errors:
        out["errors"] = errors
    return out
