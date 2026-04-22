"""DSCR / DTI and rule evaluation from YAML-driven field names."""

from __future__ import annotations

from typing import Any


def _f(data: dict[str, Any], key: str) -> float | None:
    v = data.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_dscr(merged: dict[str, Any], rules: dict[str, Any]) -> float | None:
    dcfg = rules.get("dscr", {})
    num_k = dcfg.get("numerator_field", "noi")
    den_k = dcfg.get("denominator_field", "debt_service")
    num = _f(merged, num_k)
    den = _f(merged, den_k)
    if den is None:
        mode = dcfg.get("treat_missing_denominator_as", "reject")
        if mode == "use_one" and num is not None:
            den = 1.0
        else:
            return None
    if num is None:
        return None
    if den == 0:
        return None
    return num / den


def compute_dti_percent(merged: dict[str, Any], rules: dict[str, Any]) -> float | None:
    dcfg = rules.get("dti", {})
    inc_k = dcfg.get("income_field", "gross_monthly_income")
    debt_k = dcfg.get("debt_field", "monthly_debt_payments")
    inc = _f(merged, inc_k)
    debt = _f(merged, debt_k)
    if inc is None or inc == 0 or debt is None:
        return None
    return (debt / inc) * 100.0


def normalize_credit_score(score: float) -> float:
    """Map 300-850-ish to 0-1 for ML features."""
    return max(0.0, min(1.0, (850.0 - float(score)) / 550.0))
