"""
SA Policy Rules — configurable underwriting thresholds.

Matches the "Kudu Underwriting / SA Business Banking" design:
  dark-green sidebar · card rows · per-rule Save button.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import yaml
import streamlit as st

CONFIG_PATH = _ROOT / "config" / "underwriting.yaml"

st.set_page_config(
    page_title="SA Policy Rules",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="⚙️",
)

# ── Global styles ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Sidebar */
[data-testid="stSidebar"] {
    background: #162716 !important;
}
[data-testid="stSidebar"] * {
    color: #e8f5e8 !important;
}
[data-testid="stSidebar"] .sidebar-brand {
    font-size: 1.15rem;
    font-weight: 800;
    color: #ffffff !important;
    letter-spacing: 0.02em;
}
[data-testid="stSidebar"] .sidebar-sub {
    font-size: 0.72rem;
    color: #7db87d !important;
    margin-top: -4px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
[data-testid="stSidebar"] hr { border-color: #2e4e2e !important; }

/* Page background */
.main .block-container { background: #f5f5f0; padding-top: 2rem; }

/* Config label */
.config-label {
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #888;
    margin-bottom: 4px;
}
/* Page title */
.page-title {
    font-size: 1.8rem;
    font-weight: 800;
    color: #1a2e1a;
    margin: 0 0 4px 0;
}
.page-sub {
    font-size: 0.88rem;
    color: #666;
    margin-bottom: 1.6rem;
}
/* Rule card */
.rule-card {
    background: #fff;
    border: 1px solid #e8ebe8;
    border-radius: 10px;
    padding: 16px 22px;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 16px;
}
.rule-icon {
    width: 36px; height: 36px;
    background: #f0f4f0;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 1rem;
    flex-shrink: 0;
}
.rule-name { font-weight: 700; font-size: 0.97rem; color: #1a2e1a; }
.rule-code { font-size: 0.72rem; color: #888; margin-top: 1px; }
/* Nav links */
.nav-link {
    display: block;
    padding: 9px 14px;
    border-radius: 7px;
    margin: 3px 0;
    font-size: 0.9rem;
    font-weight: 500;
    color: #cde8cd !important;
    text-decoration: none;
    cursor: pointer;
}
.nav-link:hover, .nav-link.active {
    background: #2a4a2a;
    color: #ffffff !important;
}
/* Save button */
div[data-testid="stButton"] > button {
    background: #1a4a1a !important;
    color: #fff !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    padding: 6px 18px !important;
}
div[data-testid="stButton"] > button:hover {
    background: #0d330d !important;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_cfg() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save_cfg(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ── Rule definitions ───────────────────────────────────────────────────────────
# Each entry: (display_name, code_label, yaml_path, step, fmt_fn)
RULES: list[tuple] = [
    ("DSCR >= {v}",          "DSCR · GTE",              ["ratios", "dscr_min"],            0.01,  lambda v: v),
    ("Debt-to-Income <= {v}%","DTI · LTE",               ["ratios", "dti_max"],             0.01,  lambda v: v * 100),
    ("EBITDA Margin >= {v}%", "EBITDA_MARGIN · GTE",     ["ratios", "ebitda_margin_min"],   0.01,  lambda v: v * 100),
    ("Current Ratio >= {v}",  "CURRENT_RATIO · GTE",     ["ratios", "current_ratio_min"],   0.01,  lambda v: v),
    ("Bureau Score >= {v}",   "BUREAU_SCORE · GTE",      ["credit", "bureau_score_min"],    1.0,   lambda v: v),
    ("Years In Business >= {v}","YEARS_IN_BUSINESS · GTE",["business","years_in_business_min"],1.0, lambda v: v),
    ("Min Premium (ZAR)",     "MIN_PREMIUM",             ["rules", "min_premium"],          5000,  lambda v: v),
    ("Age Min",               "AGE_MIN · GTE",           ["rules", "age_min"],              1.0,   lambda v: v),
    ("Age Max",               "AGE_MAX · LTE",           ["rules", "age_max"],              1.0,   lambda v: v),
    ("Credit Score Min",      "CREDIT_SCORE · GTE",      ["credit", "score_min"],           1.0,   lambda v: v),
]

ICONS = ["⚙️", "⚙️", "⚙️", "⚙️", "⚙️", "⚙️", "⚙️", "⚙️", "⚙️", "⚙️"]


def _get_nested(cfg: dict, path: list[str]) -> float | None:
    d = cfg
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def _set_nested(cfg: dict, path: list[str], value) -> None:
    d = cfg
    for k in path[:-1]:
        d = d.setdefault(k, {})
    d[path[-1]] = value


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="sidebar-brand">SA Underwriting</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">SA Business Banking</div>', unsafe_allow_html=True)
    st.divider()
    if st.button("🏠  Dashboard", use_container_width=True, key="nav_dash"):
        st.switch_page("dashboard.py")
    if st.button("➕  New Application", use_container_width=True, key="nav_new"):
        import streamlit as _st
        _st.switch_page("dashboard.py")
    st.markdown("")
    # Active page highlight
    st.markdown(
        '<div style="background:#2a4a2a;border-radius:7px;padding:9px 14px;font-size:0.9rem;font-weight:600;color:#fff;">⚙️  Policy Rules</div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.caption("Changes are saved directly to `config/underwriting.yaml`.")


# ── Page header ────────────────────────────────────────────────────────────────

st.markdown('<div class="config-label">CONFIGURATION</div>', unsafe_allow_html=True)
st.markdown('<div class="page-title">SA Policy Rules</div>', unsafe_allow_html=True)
st.markdown('<div class="page-sub">Configurable thresholds applied on every underwriting decision.</div>', unsafe_allow_html=True)

cfg = _load_cfg()

# ── Rule cards ─────────────────────────────────────────────────────────────────

for i, (name_tpl, code_label, yaml_path, step, fmt_fn) in enumerate(RULES):
    raw_val = _get_nested(cfg, yaml_path)
    if raw_val is None:
        continue

    display_val = fmt_fn(raw_val)
    rule_name = name_tpl.replace("{v}", str(display_val))

    with st.container():
        st.markdown(
            f"""
            <div class="rule-card">
              <div class="rule-icon">⚙️</div>
              <div style="flex:1">
                <div class="rule-name">{rule_name}</div>
                <div class="rule-code">{code_label}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_inp, col_btn = st.columns([3, 1])
        with col_inp:
            new_display = st.number_input(
                f"Value for {code_label}",
                value=float(display_val),
                step=float(step),
                format="%.4g",
                key=f"rule_{i}",
                label_visibility="collapsed",
            )
        with col_btn:
            if st.button("Save", key=f"save_{i}", use_container_width=True):
                # Convert display value back to storage format
                if "%" in name_tpl and "DTI" in code_label or "EBITDA" in code_label:
                    store_val = new_display / 100.0
                else:
                    store_val = new_display
                _set_nested(cfg, yaml_path, store_val)
                _save_cfg(cfg)
                st.success(f"✅ **{code_label}** updated to `{new_display}`", icon="✅")
                st.rerun()

st.divider()
st.caption(f"Config file: `{CONFIG_PATH}`")
