"""
Lightweight JSON-based application store.

Persists every processed underwriting application to data/applications.json.
Provides read helpers for the dashboard view.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_STORE_PATH = Path(__file__).resolve().parents[1] / "data" / "applications.json"
_lock = threading.Lock()


def _load_raw() -> list[dict[str, Any]]:
    if not _STORE_PATH.is_file():
        return []
    try:
        return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write_raw(records: list[dict[str, Any]]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(
        json.dumps(records, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )


def save_application(result: dict[str, Any], loan_type: str = "Term") -> None:
    """
    Extract key fields from a pipeline result and upsert into the store.

    Called after every successful pipeline run from the UI.
    """
    app_id     = result.get("application_id") or "UNKNOWN"
    merged     = result.get("merged_applicant") or {}
    parsed     = result.get("parsed_document") or {}
    derived    = parsed.get("derived") or {}
    delinq     = result.get("delinquency") or {}
    credit     = result.get("credit_result") or {}
    ratios     = result.get("ratios") or {}
    assess     = result.get("llm_credit_assessment") or {}
    decision   = result.get("decision") or "UNKNOWN"

    # Resolve display name
    entity_name = (
        merged.get("applicant_full_name")
        or parsed.get("entity_name")
        or merged.get("employer_name")
        or "Unknown"
    )

    # Requested amount = proposed premium or avg monthly income annualised
    requested = (
        merged.get("proposed_annuity_premium_zar")
        or derived.get("avg_monthly_income_zar", 0) * 12
        or 0
    )

    # ML score = credit_score from AI assessment (0–100 normalised for display)
    ml_score_raw = float(delinq.get("credit_score") or assess.get("credit_score") or 0)
    # Normalise 300-850 to 0-100 for the table display
    ml_score_display = round((ml_score_raw - 300) / 5.5, 2) if ml_score_raw >= 300 else ml_score_raw

    bureau_score = credit.get("bureau_score") or credit.get("combined_score") or None

    # Map internal decision to display status
    status_map = {
        "STP":                  ("DECIDED",     "APPROVED"),
        "CONDITIONAL_APPROVAL": ("DECIDED",     "CONDITIONALLY APPROVED"),
        "MANUAL_REVIEW":        ("IN_PROGRESS", "PENDING"),
        "DECLINED":             ("DECIDED",     "REJECTED"),
    }
    status, disp_decision = status_map.get(decision, ("DECIDED", decision))

    record: dict[str, Any] = {
        "id":                app_id,
        "entity_name":       entity_name,
        "loan_type":         loan_type,
        "requested_zar":     float(requested),
        "ml_score":          ml_score_display,
        "bureau_score":      float(bureau_score) if bureau_score else None,
        "status":            status,
        "decision":          disp_decision,
        "created_at":        datetime.now(tz=timezone.utc).isoformat(),
        # Extra detail (shown on click / in detail view)
        "dscr":              ratios.get("dscr"),
        "dti_percent":       round(float(ratios["dti"]) * 100, 1) if ratios.get("dti") else None,
        "credit_grade":      assess.get("credit_grade"),
        "delinquency_count": delinq.get("delinquency_count", 0),
        "months_covered":    parsed.get("months_covered"),
        "review_reasons":    result.get("review_reasons") or [],
    }

    with _lock:
        records = _load_raw()
        # Upsert — replace if same application_id exists
        records = [r for r in records if r.get("id") != app_id]
        records.insert(0, record)   # most-recent first
        _write_raw(records)


def load_all() -> list[dict[str, Any]]:
    """Return all applications, most-recent first."""
    with _lock:
        return _load_raw()


def get_summary(records: list[dict[str, Any]] | None = None) -> dict[str, int]:
    if records is None:
        records = load_all()
    total       = len(records)
    approved    = sum(1 for r in records if r.get("decision") in ("APPROVED", "STP", "CONDITIONALLY APPROVED"))
    declined    = sum(1 for r in records if r.get("decision") in ("REJECTED", "DECLINED"))
    in_progress = sum(1 for r in records if r.get("status") == "IN_PROGRESS")
    return {"total": total, "approved": approved, "declined": declined, "in_progress": in_progress}


def update_application(app_id: str, updates: dict[str, Any]) -> None:
    """Partial-update an existing application record (merge)."""
    with _lock:
        records = _load_raw()
        for r in records:
            if r.get("id") == app_id:
                r.update(updates)
                r["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
                break
        _write_raw(records)


def delete_application(app_id: str) -> None:
    with _lock:
        records = [r for r in _load_raw() if r.get("id") != app_id]
        _write_raw(records)
