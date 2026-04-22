"""Risk score from joblib model or YAML-driven heuristic fallback."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from services.config_loader import load_ml
from services.logger import get_logger
from services.settings import settings
from services.risk_math import normalize_credit_score

log = get_logger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def predict_risk_score(feature_row: dict[str, float]) -> tuple[float, str]:
    """
    Returns (score 0-1, source label).
    Higher score = higher risk by convention in this template.
    """
    ml_cfg = load_ml()
    path_env = ml_cfg.get("model", {}).get("path_env", "ML_MODEL_PATH")
    default_rel = ml_cfg.get("model", {}).get("default_relative_path", "artifacts/risk_model.joblib")
    explicit = os.environ.get(path_env) or settings.ml_model_path
    path = Path(explicit) if explicit else _project_root() / default_rel

    feats_order: list[str] = list(ml_cfg.get("features", []))
    x = np.array([[float(feature_row.get(k, 0.0)) for k in feats_order]])

    if path.is_file():
        try:
            bundle = joblib.load(path)
            if bundle.get("kind") == "numpy_logistic":
                coef = np.asarray(bundle["coef"], dtype=float)
                intercept = float(bundle["intercept"])
                z = float((x @ coef.T + intercept)[0, 0])
                p = float(1.0 / (1.0 + np.exp(-np.clip(z, -32, 32))))
                return p, "joblib"
            clf = bundle.get("model")
            proba = getattr(clf, "predict_proba", None) if clf is not None else None
            if callable(proba):
                p = float(proba(x)[0, 1])
                return p, "joblib"
            if clf is not None and hasattr(clf, "predict"):
                p = float(clf.predict(x)[0])
                return p, "joblib"
        except Exception as e:
            log.info("ml_load_failed", extra={"error": str(e), "path": str(path)})

    fb = ml_cfg.get("fallback", {})
    if not fb.get("use_heuristic", True):
        return 0.5, "default_mid"

    weights: dict[str, float] = dict(fb.get("heuristic_weights", {}))
    s = 0.0
    for k, w in weights.items():
        s += w * float(feature_row.get(k, 0.0))
    p = 1.0 / (1.0 + np.exp(-s))
    return float(np.clip(p, 0.0, 1.0)), "heuristic"


def build_feature_row(
    dscr: float | None,
    dti_percent: float | None,
    credit_score: float,
    merged: dict[str, Any],
) -> dict[str, float]:
    row = {
        "dscr": float(dscr if dscr is not None else 0.0),
        "dti_percent": float(dti_percent if dti_percent is not None else 0.0),
        "credit_score_normalized": normalize_credit_score(credit_score),
        "spouse_benefit_percent": float(merged.get("spouse_benefit_percent") or 0.0),
        "life_expectancy_years": float(merged.get("life_expectancy_years") or 0.0),
    }
    return row
