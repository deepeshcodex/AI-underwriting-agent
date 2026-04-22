"""Unit-style scenarios for low / medium / high risk outcomes (config-driven)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

from nodes import decide  # noqa: E402
from services.config_loader import clear_cache, load_rules  # noqa: E402


def _state(**kwargs):
    base = {
        "metrics": {},
        "credit": {},
        "merged_applicant": {},
        "errors": [],
        "policy_preview": {},
    }
    base.update(kwargs)
    return base


def test_rules_load_without_hardcoded_literals():
    clear_cache()
    r = load_rules()
    assert "dscr" in r and "minimum" in r["dscr"]
    assert "dti" in r and "maximum_percent" in r["dti"]
    assert "age" in r


@pytest.mark.parametrize(
    ("ml", "dscr", "dti", "flags", "expect"),
    [
        (0.1, 1.3, 30.0, [], "STP"),
        (0.5, 1.3, 30.0, [], "MANUAL_REVIEW"),
        (0.1, 1.0, 30.0, [], "MANUAL_REVIEW"),
        (0.1, 1.3, 50.0, [], "MANUAL_REVIEW"),
    ],
)
def test_decide_bands(ml: float, dscr: float, dti: float, flags: list, expect: str):
    clear_cache()
    st = _state(
        metrics={"dscr": dscr, "dti_percent": dti, "ml_score": ml},
        credit={"adverse_flags": flags},
    )
    out = decide.run(st)
    assert out["decision"] == expect


def test_declined_respected():
    clear_cache()
    st = _state(
        decision="DECLINED",
        metrics={"dscr": 2.0, "dti_percent": 10.0, "ml_score": 0.01},
        credit={"adverse_flags": []},
    )
    out = decide.run(st)
    assert out["decision"] == "DECLINED"


def test_manual_when_errors():
    clear_cache()
    st = _state(
        metrics={"dscr": 1.5, "dti_percent": 25.0, "ml_score": 0.1},
        credit={"adverse_flags": []},
        errors=["doc_issue"],
    )
    out = decide.run(st)
    assert out["decision"] == "MANUAL_REVIEW"
