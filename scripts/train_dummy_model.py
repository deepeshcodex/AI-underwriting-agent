"""Train a tiny NumPy logistic-style artifact (no sklearn) and save with joblib."""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import joblib
import numpy as np

from services.config_loader import load_ml


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -32, 32)))


def main() -> None:
    ml_cfg = load_ml()
    default_rel = ml_cfg.get("model", {}).get("default_relative_path", "artifacts/risk_model.joblib")
    out = _root / default_rel
    feats = list(ml_cfg.get("features", []))
    rng = np.random.default_rng(42)
    x = rng.normal(size=(400, len(feats)))
    logits = 2.0 * x[:, 0] - 0.03 * x[:, 1] - 1.5 * x[:, 2] + 0.01 * rng.normal(size=400)
    y = (logits > np.median(logits)).astype(np.float64)
    # Simple least-squares style weights (demo only)
    xb = np.hstack([x, np.ones((x.shape[0], 1))])
    w, *_ = np.linalg.lstsq(xb, y, rcond=None)
    coef = w[:-1].reshape(1, -1)
    intercept = float(w[-1])
    bundle = {
        "kind": "numpy_logistic",
        "coef": coef,
        "intercept": intercept,
        "features": feats,
    }
    # Smoke test
    p = _sigmoid(x[:1] @ coef.T + intercept)[0, 0]
    assert 0.0 <= p <= 1.0
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out)
    print(f"Wrote {out} (prob_smoke={p:.4f})")


if __name__ == "__main__":
    main()
