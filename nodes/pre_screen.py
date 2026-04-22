"""Pre-screen: validate basics using config/rules.yaml only."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from services.config_loader import load_rules
from services.logger import get_logger
from models.graph_state import UnderwritingState

log = get_logger(__name__)


def _parse_dob(s: str | None) -> date | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _age_on_date(dob: date, today: date | None = None) -> int:
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def run(state: UnderwritingState) -> dict[str, Any]:
    rules = load_rules()
    sub = state.get("applicant_submission") or {}
    ps_cfg = rules.get("pre_screen", {})
    errors: list[str] = []

    prem = sub.get("proposed_annuity_premium_zar")
    if ps_cfg.get("require_premium_before_docs") and prem is None:
        errors.append("Proposed annuity premium required at pre-screen.")

    min_zar = float(rules.get("premium", {}).get("min_zar", 0))
    if prem is not None:
        try:
            if float(prem) < min_zar:
                errors.append(f"Premium below minimum ZAR {min_zar}.")
        except (TypeError, ValueError):
            errors.append("Invalid proposed_annuity_premium_zar.")

    dob_s = sub.get("date_of_birth")
    dob = _parse_dob(dob_s) if isinstance(dob_s, str) else None
    age_min = int(rules.get("age", {}).get("min", 0))
    age_max = int(rules.get("age", {}).get("max", 999))
    if ps_cfg.get("require_dob_before_docs") and dob is None:
        errors.append("Date of birth required at pre-screen.")

    if dob is not None:
        age = _age_on_date(dob)
        if age < age_min or age > age_max:
            errors.append(f"Age {age} outside allowed range [{age_min}, {age_max}].")

    passed = len(errors) == 0
    out = {
        "pre_screen": {
            "passed": passed,
            "premium_ok": prem is None or (prem is not None and float(prem) >= min_zar),
            "age_years": _age_on_date(dob) if dob else None,
            "rules_ref": {"min_zar": min_zar, "age_min": age_min, "age_max": age_max},
        },
        "stage": "pre_screen",
    }
    if not passed:
        out["errors"] = errors
        out["decision"] = "DECLINED"
    log.info(
        "pre_screen_complete",
    )
    return out
