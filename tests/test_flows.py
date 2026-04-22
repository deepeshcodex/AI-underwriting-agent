"""
End-to-end and unit-level pytest scenarios (per END-TO-END.md Phase 6).

Scenarios:
  test_low_risk_stp       — all checks pass → STP
  test_delinq_reject      — "FAILED" in OCR → MANUAL_REVIEW
  test_high_dti           — DTI > 40 % → MANUAL_REVIEW
  test_pre_screen_decline — age outside range → DECLINED
  test_delinquency_ml_*   — unit tests for delinquency node helpers
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from services.config_loader import clear_cache
from nodes import decision, delinquency_ml, risk_calc
from nodes.delinquency_ml import (
    _features_from_df,
    _detect_delinquency,
    _heuristic_fallback,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _base_state(**kwargs) -> dict:
    state: dict = {
        "errors": [],
        "merged_applicant": {},
        "delinquency": {
            "is_delinquent": False,
            "credit_score": 720.0,
            "delinquency_count": 0,
            "risk_flags": [],
            "ml_features": {"avg_monthly_balance": 10000, "delinquency_count": 0, "cashflow_ratio": 1.5, "repayment_consistency": 1.0},
            "cashflow_data": [],
        },
        "ratios": {"dscr": 1.5, "dscr_ok": True, "dti": 0.3, "dti_ok": True},
        "credit_result": {"combined_score": 720.0, "score_ok": True, "adverse_flags": [], "score_min": 650},
        "ocr_segments": [],
    }
    state.update(kwargs)
    return state


# ── Scenario 1: low-risk STP ─────────────────────────────────────────────────

def test_low_risk_stp():
    clear_cache()
    state = _base_state()
    out = decision.run(state)
    assert out["decision"] == "STP", f"Expected STP, got {out['decision']}"
    assert out.get("review_reasons") == []


# ── Scenario 2: delinquency → MANUAL_REVIEW ──────────────────────────────────

def test_delinq_reject():
    """Simulated 'FAILED' text in OCR → is_delinquent=True → MANUAL_REVIEW."""
    clear_cache()
    state = _base_state(
        delinquency={
            "is_delinquent": True,
            "credit_score": 580.0,
            "delinquency_count": 2,
            "risk_flags": ["Keyword 'failed' in: PAYMENT FAILED June 2024"],
            "ml_features": {},
            "cashflow_data": [],
        },
        credit_result={"combined_score": 615.0, "score_ok": False, "adverse_flags": ["ml_delinquency_detected"], "score_min": 650},
    )
    out = decision.run(state)
    assert out["decision"] == "MANUAL_REVIEW"
    assert any("elinq" in r.lower() for r in out["review_reasons"])


# ── Scenario 3: high DTI → MANUAL_REVIEW ─────────────────────────────────────

def test_high_dti():
    clear_cache()
    state = _base_state(
        ratios={"dscr": 1.4, "dscr_ok": True, "dti": 0.55, "dti_ok": False},
    )
    out = decision.run(state)
    assert out["decision"] == "MANUAL_REVIEW"
    assert any("dti" in r.lower() for r in out["review_reasons"])


# ── Scenario 4: pre-screen decline ───────────────────────────────────────────

def test_pre_screen_decline():
    clear_cache()
    from nodes import pre_screen

    state = {
        "applicant_submission": {
            "date_of_birth": "1930-01-01",  # age 95 → outside 40-85
            "proposed_annuity_premium_zar": 120_000,
        },
        "errors": [],
    }
    out = pre_screen.run(state)
    assert out.get("decision") == "DECLINED"
    assert "errors" in out and len(out["errors"]) > 0


# ── Unit tests: delinquency_ml helpers ───────────────────────────────────────

def test_detect_delinquency_from_ocr():
    clear_cache()
    keywords = ["failed", "overdue", "nsf"]
    count, flags = _detect_delinquency(None, ["Payment FAILED June 2024", "normal text"], [], keywords)
    assert count > 0
    assert any("failed" in f.lower() for f in flags)


def test_detect_no_delinquency():
    clear_cache()
    keywords = ["failed", "overdue", "nsf"]
    count, flags = _detect_delinquency(None, ["salary deposit", "grocery store"], [], keywords)
    assert count == 0
    assert flags == []


def test_compute_features_empty():
    clear_cache()
    feats = _features_from_df(None, 3)
    assert feats["delinquency_count"] == 3.0
    assert feats["cashflow_ratio"] == 0.0


def test_score_drops_with_delinquency():
    clear_cache()
    thresholds = {"credit_score_min": 650}
    score_clean = _heuristic_fallback({"avg_monthly_balance": 10000, "delinquency_count": 0, "repayment_consistency": 1.0, "cashflow_ratio": 1.5}, thresholds)
    score_bad   = _heuristic_fallback({"avg_monthly_balance": 500,   "delinquency_count": 5, "repayment_consistency": 0.2, "cashflow_ratio": 0.6}, thresholds)
    assert float(score_clean["credit_score"]) > float(score_bad["credit_score"]), "Clean profile should score higher."


# ── Scenario 5: low credit score → MANUAL_REVIEW ─────────────────────────────

def test_low_credit_score():
    clear_cache()
    state = _base_state(
        credit_result={"combined_score": 600.0, "score_ok": False, "adverse_flags": [], "score_min": 650},
    )
    out = decision.run(state)
    assert out["decision"] == "MANUAL_REVIEW"


# ── Scenario 6: ratios ok but credit fail ─────────────────────────────────────

def test_dscr_fail():
    clear_cache()
    state = _base_state(
        ratios={"dscr": 0.9, "dscr_ok": False, "dscr_min": 1.25, "dti": 0.3, "dti_ok": True},
    )
    out = decision.run(state)
    assert out["decision"] == "MANUAL_REVIEW"
    assert any("dscr" in r.lower() for r in out["review_reasons"])
