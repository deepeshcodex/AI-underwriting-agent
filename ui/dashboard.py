"""
SA Underwriting — multi-view Streamlit app.

Views (session_state.page_view):
  "dashboard"       — Loan Applications list with stats (default landing)
  "new_application" — Full underwriting pipeline form + result tabs
"""

from __future__ import annotations

import base64
import json
import math
import os
import sys
import tempfile
import uuid
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import math as _math

import pandas as pd
import streamlit as st

from app import run_application
from services.application_store import delete_application, get_summary, load_all, save_application, update_application


st.set_page_config(
    page_title="SA Underwriting",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🏦",
)

st.markdown("""
<style>
/* Sidebar dark-green theme */
[data-testid="stSidebar"] {
    background: #162716 !important;
}
[data-testid="stSidebar"] * { color: #e8f5e8 !important; }
[data-testid="stSidebar"] hr { border-color: #2e4e2e !important; }
[data-testid="stSidebar"] label { color: #c8e8c8 !important; }
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea { color: #fff !important; background: #1e3a1e !important; border-color: #3a5e3a !important; }
[data-testid="stSidebar"] .stNumberInput input { background: #1e3a1e !important; }

/* Active nav pill */
.nav-active {
    background: #2a4a2a;
    border-radius: 7px;
    padding: 9px 14px;
    font-size: 0.9rem;
    font-weight: 600;
    color: #ffffff !important;
    margin: 3px 0;
}

/* Decision banners */
.stp-banner          {background:#1a6e2e;color:#fff;padding:14px 20px;border-radius:8px;font-size:1.35rem;font-weight:700;text-align:center;}
.conditional-banner  {background:#1a5c8a;color:#fff;padding:14px 20px;border-radius:8px;font-size:1.35rem;font-weight:700;text-align:center;}
.review-banner       {background:#8b4b00;color:#fff;padding:14px 20px;border-radius:8px;font-size:1.35rem;font-weight:700;text-align:center;}
.declined-banner     {background:#7a0000;color:#fff;padding:14px 20px;border-radius:8px;font-size:1.35rem;font-weight:700;text-align:center;}
.grade-badge    {display:inline-block;padding:4px 14px;border-radius:20px;font-weight:700;font-size:1rem;}
.info-box       {background:#eef4ff;border-left:4px solid #4477bb;padding:8px 14px;border-radius:4px;margin:6px 0;}

/* ── Loan Applications Dashboard ── */
.page-crumb  {font-size:0.72rem;letter-spacing:0.12em;text-transform:uppercase;color:#888;margin-bottom:6px;}
.page-h1     {font-size:2rem;font-weight:800;color:#1a2e1a;margin:0 0 6px 0;line-height:1.1;}
.page-sub    {font-size:0.88rem;color:#666;margin-bottom:0;}

/* Stat cards */
.stat-card {
    background:#fff;border:1px solid #e8ebe8;border-radius:12px;
    padding:20px 22px;display:flex;align-items:center;gap:16px;
}
.stat-icon-wrap {
    width:44px;height:44px;border-radius:10px;
    display:flex;align-items:center;justify-content:center;font-size:1.3rem;
    flex-shrink:0;
}
.stat-label {font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:#888;margin-bottom:2px;}
.stat-value {font-size:1.9rem;font-weight:800;color:#1a2e1a;line-height:1;}

/* Applications table */
.app-table { width:100%;border-collapse:collapse;font-size:0.9rem; }
.app-table th {
    font-size:0.7rem;letter-spacing:0.1em;text-transform:uppercase;
    color:#999;font-weight:600;padding:10px 14px;
    border-bottom:2px solid #e8ebe8;text-align:left;background:#fff;
}
.app-table td { padding:14px 14px;border-bottom:1px solid #f0f0ee;vertical-align:middle; }
.app-table tr:last-child td { border-bottom:none; }
.app-table tr:hover td { background:#fafff8; }
.app-name   { font-weight:700;color:#1a2e1a;font-size:0.92rem; }
.app-id     { font-size:0.72rem;color:#aaa;margin-top:2px; }

/* Status / decision badges */
.badge-decided     {display:inline-block;padding:3px 10px;border-radius:5px;font-size:0.75rem;font-weight:600;background:#f0f0ee;color:#555;}
.badge-in-progress {display:inline-block;padding:3px 10px;border-radius:5px;font-size:0.75rem;font-weight:600;background:#fff8e6;color:#b07000;}
.badge-approved    {display:inline-flex;align-items:center;gap:5px;padding:4px 11px;border-radius:20px;font-size:0.78rem;font-weight:700;background:#e8f5e8;color:#1a6e2e;}
.badge-declined    {display:inline-flex;align-items:center;gap:5px;padding:4px 11px;border-radius:20px;font-size:0.78rem;font-weight:700;background:#fce8e8;color:#8b0000;}
.badge-review      {display:inline-flex;align-items:center;gap:5px;padding:4px 11px;border-radius:20px;font-size:0.78rem;font-weight:700;background:#fff3cd;color:#856404;}

/* New App button */
div[data-testid="stButton"].new-app-btn > button {
    background:#1a3a1a !important;color:#fff !important;
    border:none !important;border-radius:8px !important;
    font-weight:700 !important;font-size:0.95rem !important;
    padding:10px 20px !important;
}

/* ── Table header / row cells ── */
.tbl-hdr {
    font-size:0.68rem;letter-spacing:0.1em;text-transform:uppercase;
    color:#999;font-weight:600;padding:10px 4px 8px 4px;
    border-bottom:2px solid #e8ebe8;
}
.tbl-divider { border:none;border-top:1px solid #f0f0ee;margin:0; }
.tbl-name    { font-weight:700;color:#1a2e1a;font-size:0.9rem;line-height:1.3; }
.tbl-sub     { font-size:0.7rem;color:#aaa;margin-top:1px; }
.tbl-cell    { font-size:0.88rem;color:#333;padding:4px 0; }
.tbl-cell-bold{ font-size:0.88rem;font-weight:700;color:#1a2e1a;padding:4px 0; }
.tbl-row-sep { margin:0;border:none;border-top:1px solid #f4f4f2; }

/* Action buttons */
div[data-testid="stButton"].btn-view > button {
    background:#f0f4ff !important;color:#1a3a8a !important;
    border:1px solid #c8d4f8 !important;border-radius:7px !important;
    font-size:0.78rem !important;font-weight:600 !important;
    padding:5px 10px !important;width:100%;
}
div[data-testid="stButton"].btn-edit > button {
    background:#fff8f0 !important;color:#8a4a00 !important;
    border:1px solid #f5d8a8 !important;border-radius:7px !important;
    font-size:0.78rem !important;font-weight:600 !important;
    padding:5px 10px !important;width:100%;
}

/* ── Detail / Edit view ── */
.detail-header-card {
    background:#fff;border:1px solid #e8ebe8;border-radius:12px;
    padding:24px 28px;margin-bottom:16px;
}
.detail-title { font-size:1.6rem;font-weight:800;color:#1a2e1a;margin:0 0 4px; }
.detail-meta  { font-size:0.8rem;color:#888;margin:0; }
.detail-section {
    background:#fff;border:1px solid #e8ebe8;border-radius:10px;
    padding:18px 22px;margin-bottom:12px;
}
.detail-section-title {
    font-size:0.68rem;letter-spacing:0.1em;text-transform:uppercase;
    color:#888;font-weight:600;margin:0 0 12px;
}
.detail-kv {
    display:flex;justify-content:space-between;align-items:center;
    padding:7px 0;border-bottom:1px solid #f4f4f2;font-size:0.88rem;
}
.detail-kv:last-child { border-bottom:none; }
.detail-kv-label { color:#666; }
.detail-kv-value { font-weight:700;color:#1a2e1a; }
.back-btn-row { margin-bottom:16px; }
.edit-form-card {
    background:#fff;border:1px solid #e8ebe8;border-radius:12px;
    padding:28px;margin-bottom:16px;
}

/* ── Wizard ── */
.wiz-card {background:#fff;border:1px solid #e8ebe8;border-radius:12px;padding:28px;margin-bottom:16px;}
.wiz-step-label {font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:#888;margin-bottom:4px;}
.wiz-step-title {font-size:1.4rem;font-weight:800;color:#1a2e1a;margin-bottom:20px;}
.wiz-emi-card   {background:#fff;border:1px solid #e8ebe8;border-radius:12px;padding:24px;}
.wiz-emi-amount {font-size:2.1rem;font-weight:900;color:#1a2e1a;margin:6px 0 2px;}
.wiz-emi-label  {font-size:0.78rem;color:#888;margin-bottom:0;}
.wiz-emi-row    {display:flex;justify-content:space-between;padding:9px 0;border-top:1px solid #f0f0ee;font-size:0.85rem;}
.wiz-decision-approved     {font-size:2.2rem;font-weight:900;color:#1a6e2e;}
.wiz-decision-conditional  {font-size:2.2rem;font-weight:900;color:#1a5c8a;}
.wiz-decision-declined     {font-size:2.2rem;font-weight:900;color:#8b0000;}
.wiz-decision-review       {font-size:2.2rem;font-weight:900;color:#856404;}
.wiz-decision-pending      {font-size:2.2rem;font-weight:900;color:#555;}
.badge-conditional {display:inline-flex;align-items:center;gap:5px;padding:4px 11px;border-radius:20px;font-size:0.78rem;font-weight:700;background:#e8f0ff;color:#1a5c8a;}
.wiz-ratio-tile {background:#f8faf8;border-radius:8px;padding:14px;text-align:center;}
.wiz-ratio-lbl  {font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;color:#888;margin-bottom:5px;}
.wiz-ratio-val  {font-size:1.25rem;font-weight:800;color:#1a2e1a;}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(v: object) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"R {v:,.2f}" if v > 99 else f"{v:.4f}"
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str, ensure_ascii=False)
    return str(v)


def _zar(v: float | None) -> str:
    return f"R {v:,.0f}" if v else "—"


def _kv_df(data: dict) -> pd.DataFrame:
    return pd.DataFrame([
        {"Field": k.replace("_", " ").title(), "Value": _fmt(v)}
        for k, v in data.items() if not str(k).startswith("_")
    ])


def _table(data: dict) -> None:
    if data:
        st.dataframe(_kv_df(data), use_container_width=True, hide_index=True)
    else:
        st.caption("_No data._")


def _policy_download(policy: dict) -> None:
    b64 = policy.get("bytes_b64", "")
    fname = policy.get("filename", "policy.txt")
    is_pdf = policy.get("is_pdf", False)
    try:
        st.download_button(
            label=f"⬇️  Download Policy {'PDF' if is_pdf else 'TXT'} ({policy.get('size_kb', 0)} KB)",
            data=base64.b64decode(b64),
            file_name=fname,
            mime="application/pdf" if is_pdf else "text/plain",
            use_container_width=True,
        )
    except Exception as e:
        st.caption(f"Policy download unavailable: {e}")


def _grade_color(g: str) -> str:
    return {"A": "#1a6e2e", "B": "#2d7d46", "C": "#e07b00", "D": "#c04000", "E": "#900000", "F": "#600000"}.get(g, "#555")


# ── Amortization plan ─────────────────────────────────────────────────────────

def _amortization_table(premium: float, years: int, annual_rate: float = 0.0) -> pd.DataFrame:
    """
    Simple SA annuity amortization schedule.
    For a pure annuity (no loan amortization), shows premium payments + notional interest component.
    annual_rate = 0 means flat (no interest escalation).
    """
    rows = []
    cumulative = 0.0
    balance = premium * years  # total commitment
    for yr in range(1, years + 1):
        interest = balance * annual_rate
        principal = premium - interest
        cumulative += premium
        balance = max(0.0, balance - principal)
        rows.append({
            "Year": yr,
            "Annual Premium (ZAR)": premium,
            "Interest Component": round(interest, 2),
            "Principal Component": round(principal, 2),
            "Cumulative Paid (ZAR)": round(cumulative, 2),
            "Remaining Commitment (ZAR)": round(balance, 2),
        })
    return pd.DataFrame(rows)


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _sidebar(view: str) -> dict:
    with st.sidebar:
        # Brand
        st.markdown(
            '<div style="font-size:1.15rem;font-weight:800;color:#ffffff;letter-spacing:0.02em;">SA Underwriting</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="font-size:0.7rem;color:#7db87d;margin-top:-4px;letter-spacing:0.1em;text-transform:uppercase;">SA Business Banking</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        # Navigation
        dash_active = view in ("dashboard", "view_application", "edit_application")
        new_active  = view == "new_application"

        if dash_active and view == "dashboard":
            st.markdown('<div class="nav-active">🏠  Dashboard</div>', unsafe_allow_html=True)
        else:
            if st.button("🏠  Dashboard", use_container_width=True, key="nav_dash"):
                st.session_state.page_view = "dashboard"
                st.session_state.result    = None
                _wiz_reset()
                st.rerun()

        if new_active:
            st.markdown('<div class="nav-active">➕  New Application</div>', unsafe_allow_html=True)
        else:
            if st.button("➕  New Application", use_container_width=True, key="nav_new_app"):
                _wiz_reset()
                st.session_state.page_view = "new_application"
                st.rerun()

        # Contextual nav for detail/edit views
        if view == "view_application":
            selected = st.session_state.get("dash_selected_id", "")
            st.markdown(
                f'<div style="margin:8px 0;padding:8px 12px;background:#1e3a1e;border-radius:7px;'
                f'font-size:0.8rem;color:#a8d8a8;">📄 Viewing<br/>'
                f'<b style="color:#fff;">{selected[:18]}</b></div>',
                unsafe_allow_html=True,
            )
        elif view == "edit_application":
            selected = st.session_state.get("dash_selected_id", "")
            st.markdown(
                f'<div style="margin:8px 0;padding:8px 12px;background:#3a2a0e;border-radius:7px;'
                f'font-size:0.8rem;color:#f5d8a8;">✏️ Editing<br/>'
                f'<b style="color:#fff;">{selected[:18]}</b></div>',
                unsafe_allow_html=True,
            )

        if st.button("⚙️  Policy Rules", use_container_width=True, key="nav_policy"):
            st.switch_page("pages/policy_rules.py")

        st.divider()

        # Application form inputs — only shown when creating a new application
        if view == "new_application":
            if "app_id_val" not in st.session_state:
                st.session_state.app_id_val = f"APP-{uuid.uuid4().hex[:8]}"
            app_id  = st.text_input("Application ID", value=st.session_state.app_id_val)
            dob     = st.text_input("Date of birth (YYYY-MM-DD)", value="1978-04-10")
            premium = st.number_input("Proposed annual premium (ZAR)", min_value=0.0, value=120_000.0, step=5_000.0)
            years   = st.number_input("Policy term (years)", min_value=1, max_value=30, value=10, step=1)
            loan_type = st.selectbox(
                "Loan / product type",
                ["Structured Annuity", "Term Loan", "Equipment Finance", "Working Capital", "Revolving Credit"],
            )
            hints_raw = st.text_input(
                "Doc categories (comma, per-file order)",
                value="bank_statement",
                help="E.g. identity,bank_statement,income_proof",
            )
            st.divider()
            st.caption("Needs `OPENAI_API_KEY` or `OPEN_API` in `env.local`.")
        else:
            app_id = dob = hints_raw = loan_type = ""
            premium = years = 0

    return {
        "app_id":     app_id,
        "dob":        dob,
        "premium":    float(premium) if premium else 0.0,
        "years":      int(years) if years else 10,
        "hints_raw":  hints_raw,
        "loan_type":  loan_type,
    }


# ── KPI row ───────────────────────────────────────────────────────────────────

def _kpi_row(result: dict) -> None:
    delinq   = result.get("delinquency") or {}
    credit_r = result.get("credit_result") or {}
    ratios   = result.get("ratios") or {}
    assess   = result.get("llm_credit_assessment") or {}

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        sc = credit_r.get("combined_score")
        ok = credit_r.get("score_ok")
        st.metric("Combined credit score",
                  f"{sc:.0f}" if sc else "—",
                  delta="✅ OK" if ok else "❌ FAIL",
                  delta_color="normal" if ok else "inverse")
    with c2:
        grade = delinq.get("credit_grade") or assess.get("credit_grade") or "—"
        st.metric("AI credit grade", grade, delta=assess.get("recommendation") or "—")
    with c3:
        flag = delinq.get("is_delinquent")
        st.metric("Delinquency",
                  "⚠️ Yes" if flag else "✅ None",
                  delta=f"{delinq.get('delinquency_count', 0)} flag(s)")
    with c4:
        dscr = ratios.get("dscr")
        dscr_ok = ratios.get("dscr_ok")
        st.metric("DSCR",
                  f"{dscr:.2f}" if dscr is not None else "N/A",
                  delta="✅ OK" if dscr_ok is True else ("❌ FAIL" if dscr_ok is False else "ℹ️ Unavailable"),
                  delta_color="normal" if dscr_ok is True else ("inverse" if dscr_ok is False else "off"))
    with c5:
        dti = ratios.get("dti")
        dti_ok = ratios.get("dti_ok")
        st.metric("DTI",
                  f"{dti:.1%}" if dti is not None else "N/A",
                  delta="✅ OK" if dti_ok is True else ("❌ FAIL" if dti_ok is False else "ℹ️ Unavailable"),
                  delta_color="normal" if dti_ok is True else ("inverse" if dti_ok is False else "off"))


# ── Tab renderers ─────────────────────────────────────────────────────────────

def _tab_policy(result: dict, sidebar: dict) -> None:
    decision = (result.get("decision") or "").upper()
    review_reasons = result.get("review_reasons") or []
    info_notes = result.get("info_notes") or []

    if decision == "STP":
        st.success("✅ Straight-through approved — application auto-booked.")
    elif decision == "MANUAL_REVIEW":
        st.warning("⚠️ Manual review required before policy can be issued.")
        if review_reasons:
            st.markdown("**Reasons for review:**")
            for r in review_reasons:
                st.markdown(f"- {r}")
    else:
        st.error("🚫 Declined at pre-screen. No policy issued.")

    if info_notes:
        with st.expander("ℹ️ Informational notes (not blocking)", expanded=False):
            for n in info_notes:
                st.markdown(f'<div class="info-box">{n}</div>', unsafe_allow_html=True)

    policy = result.get("policy")
    if policy:
        _policy_download(policy)

    # Amortization plan
    st.divider()
    st.subheader("📅 Amortization / premium schedule")
    premium = float(sidebar.get("premium") or 120_000)
    years   = int(sidebar.get("years") or 10)
    df_am   = _amortization_table(premium, years)
    st.dataframe(df_am, use_container_width=True, hide_index=True)
    st.caption(f"Total commitment over {years} years: **{_zar(premium * years)}**")

    if decision == "MANUAL_REVIEW":
        st.divider()
        st.subheader("Underwriter action")
        notes = st.text_area("Notes / override reason", height=100, key="uw_notes")
        col_a, col_r = st.columns(2)
        with col_a:
            if st.button("✅ Approve & issue policy", use_container_width=True):
                st.session_state["uw_action"] = "approved"
                st.success("Approved. Policy issued.")
                if policy:
                    _policy_download(policy)
        with col_r:
            if st.button("❌ Reject application", use_container_width=True):
                st.session_state["uw_action"] = "rejected"
                st.error(f"Rejected. Reason: {notes or '(none provided)'}")


def _tab_customer(result: dict, sidebar: dict) -> None:
    bank_profile = result.get("bank_profile") or result.get("policy_preview", {}).get("bank_profile") or {}
    parsed       = result.get("parsed_document") or {}
    derived      = parsed.get("derived") or {}
    merged       = result.get("merged_applicant") or {}

    # Pick best values: parsed_document > bank_profile > merged
    def _pick(*sources_keys):
        for src, key in sources_keys:
            v = src.get(key)
            if v is not None and v not in ("", "—"):
                return v
        return "—"

    st.subheader("Customer / entity overview")
    doc_type = parsed.get("document_type") or "unknown"
    st.badge(f"Document type: {doc_type.replace('_', ' ').upper()}", icon="📄")

    c1, c2 = st.columns(2)
    with c1:
        name  = _pick((merged, "applicant_full_name"), (parsed, "entity_name"), (parsed, "account_holder_name"), (bank_profile, "account_holder_name"))
        st.markdown(f"**Entity / name:** {name}")
        st.markdown(f"**Date of birth:** {merged.get('date_of_birth') or '—'}")
        st.markdown(f"**Employer:** {_pick((merged, 'employer_name'), (derived, 'employer_name'), (bank_profile, 'employer_name'))}")
        st.markdown(f"**Account (masked):** {_pick((parsed, 'account_number_masked'), (bank_profile, 'account_number_masked'), (merged, 'account_last4'))}")
        st.markdown(f"**Bank / account type:** {_pick((parsed, 'bank_name'), (bank_profile, 'bank_name'))} · {_pick((parsed, 'account_type'), (bank_profile, 'account_type'))}")
        st.markdown(f"**Branch code:** {parsed.get('branch_code') or '—'}")
        st.markdown(f"**Currency:** {parsed.get('currency') or 'ZAR'}")
    with c2:
        st.markdown(f"**Statement start:** {_pick((parsed, 'statement_period_start'), (bank_profile, 'statement_period_start'))}")
        st.markdown(f"**Statement end:** {_pick((parsed, 'statement_period_end'), (bank_profile, 'statement_period_end'))}")
        st.markdown(f"**Months covered:** {parsed.get('months_covered') or bank_profile.get('months_covered') or '—'}")
        # Get opening/closing from monthly_summaries if available
        ms = parsed.get("monthly_summaries") or []
        open_bal  = ms[0].get("opening_balance") if ms else None
        close_bal = ms[-1].get("closing_balance") if ms else None
        st.markdown(f"**Opening balance:** {_zar(open_bal or bank_profile.get('opening_balance_zar'))}")
        st.markdown(f"**Closing balance:** {_zar(close_bal or bank_profile.get('closing_balance_zar'))}")
        st.markdown(f"**Balance trend:** {derived.get('balance_trend') or bank_profile.get('balance_trend') or '—'}")

    st.divider()
    st.subheader("Income & expense summary")
    c3, c4 = st.columns(2)
    avg_inc = derived.get("avg_monthly_income_zar") or bank_profile.get("total_income_monthly_avg") or merged.get("gross_monthly_income")
    avg_exp = derived.get("avg_monthly_expenses_zar") or bank_profile.get("total_expenses_monthly_avg")
    avg_net = derived.get("avg_monthly_net_zar") or bank_profile.get("net_cashflow_monthly_avg")
    loan_rep = derived.get("loan_repayment_monthly_zar") or bank_profile.get("debt_obligations_total_monthly") or merged.get("monthly_debt_payments")
    with c3:
        st.metric("Avg monthly income (credits)", _zar(avg_inc))
        st.metric("Avg monthly expenses (debits)", _zar(avg_exp))
        st.metric("Avg net cashflow / month", _zar(avg_net),
                  delta="Positive" if (avg_net or 0) > 0 else "Negative",
                  delta_color="normal" if (avg_net or 0) > 0 else "inverse")
    with c4:
        st.metric("Loan repayment / month", _zar(loan_rep))
        st.metric("Annual debt service", _zar(derived.get("annual_debt_service_zar")))
        st.metric("Avg monthly balance", _zar(derived.get("avg_monthly_balance_zar") or bank_profile.get("avg_balance_zar")))

    st.divider()
    st.subheader("Behavioural indicators")
    cols = st.columns(4)
    cols[0].metric("Income stability",   derived.get("income_stability")  or bank_profile.get("income_stability") or "—")
    cols[1].metric("Balance trend",      derived.get("balance_trend")     or bank_profile.get("balance_trend") or "—")
    cols[2].metric("Savings behaviour",  derived.get("savings_behaviour") or bank_profile.get("savings_behaviour") or "—")
    cols[3].metric("Cashflow ratio",     f"{derived.get('cashflow_ratio', 0):.2f}" if derived.get("cashflow_ratio") else "—")

    # Recurring debits from bank_profile
    recurring = bank_profile.get("recurring_debits") or []
    if recurring and isinstance(recurring, list):
        st.divider()
        st.subheader("Recurring debt obligations")
        rows = [{"Description": i.get("description") or "—", "Monthly (ZAR)": _zar(i.get("amount_zar")), "Frequency": i.get("frequency") or "monthly"}
                for i in recurring if isinstance(i, dict)]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("📋 All extracted fields", expanded=False):
        combined = {**merged}
        for k, v in {**bank_profile, **derived}.items():
            if k not in combined:
                combined[k] = v
        _table(combined)


def _tab_ai_score(result: dict) -> None:
    assess  = result.get("llm_credit_assessment") or {}
    delinq  = result.get("delinquency") or {}

    if not assess:
        st.info("No AI credit assessment available (no bank statement or no API key).")
        return

    score = assess.get("credit_score")
    grade = assess.get("credit_grade") or "—"
    rec   = assess.get("recommendation") or "—"
    conf  = assess.get("confidence") or "—"
    src   = assess.get("source") or "—"

    c1, c2, c3 = st.columns(3)
    with c1:
        gc = _grade_color(grade)
        score_display = f"{score:.0f}" if score else "—"
        st.markdown(f'<div style="font-size:3rem;font-weight:900;color:{gc};">{score_display}</div>', unsafe_allow_html=True)
        st.markdown(f'<span class="grade-badge" style="background:{gc};color:#fff;">Grade {grade}</span>', unsafe_allow_html=True)
    with c2:
        rec_color = "#1a6e2e" if rec == "APPROVE" else ("#8b4b00" if rec == "REVIEW" else "#7a0000")
        st.markdown(f'**Recommendation:** <span style="color:{rec_color};font-weight:700">{rec}</span>', unsafe_allow_html=True)
        st.markdown(f"**Confidence:** {conf}")
        st.markdown(f"**Data quality:** {assess.get('data_quality') or '—'}")
        st.markdown(f"**Source:** {src}")
    with c3:
        st.markdown(f"**Delinquency:** {'⚠️ Yes' if delinq.get('is_delinquent') else '✅ None'}")
        st.markdown(f"**Delinquency count:** {delinq.get('delinquency_count', 0)}")

    st.divider()
    col_pos, col_risk = st.columns(2)
    with col_pos:
        st.markdown("#### ✅ Positive factors")
        for f in (assess.get("positive_factors") or []):
            st.success(f)
    with col_risk:
        st.markdown("#### ⚠️ Risk factors")
        for f in (assess.get("risk_factors") or []):
            st.warning(f)

    if assess.get("affordability_comment"):
        st.divider()
        st.markdown(f"**Affordability:** {assess['affordability_comment']}")

    if assess.get("notes"):
        st.info(f"**Analyst notes:** {assess['notes']}")

    if delinq.get("risk_flags"):
        st.divider()
        st.markdown("**Delinquency flags detected:**")
        for f in delinq["risk_flags"]:
            st.error(f)


def _tab_transactions(result: dict) -> None:
    parsed  = result.get("parsed_document") or {}
    derived = parsed.get("derived") or {}
    delinq  = result.get("delinquency") or {}

    # ── Loan eligibility card ────────────────────────────────────────────────
    st.subheader("Loan eligibility")
    elig = parsed.get("loan_eligibility") or {}
    if elig:
        summary = elig.get("eligibility_summary")
        if summary:
            decision = result.get("decision") or ""
            if decision == "STP" or elig.get("dscr_pass") and elig.get("dti_pass") and elig.get("delinquency_free"):
                st.success(f"✅ {summary}")
            elif decision == "DECLINED":
                st.error(f"🚫 {summary}")
            else:
                st.warning(f"⚠️ {summary}")

        c1, c2, c3, c4 = st.columns(4)
        def _elig_metric(col, label, val):
            if val is True:
                col.metric(label, "✓ PASS", delta=None)
            elif val is False:
                col.metric(label, "✗ FAIL")
            else:
                col.metric(label, "N/A")

        _elig_metric(c1, "DSCR ≥ min",          elig.get("dscr_pass"))
        _elig_metric(c2, "DTI ≤ max",            elig.get("dti_pass"))
        _elig_metric(c3, "Delinquency-free",     elig.get("delinquency_free"))
        _elig_metric(c4, "Premium affordable",   elig.get("premium_affordable"))

        flags = elig.get("flags") or []
        if flags:
            st.markdown("**Underwriter flags:**")
            for f in flags:
                st.warning(f)
    else:
        st.info("Loan eligibility data not extracted — ensure a financial document was uploaded.")

    # ── Key derived metrics ──────────────────────────────────────────────────
    st.divider()
    st.subheader("Derived financial metrics")
    m = st.columns(4)
    m[0].metric("DSCR",          f"{derived['dscr']:.2f}"      if derived.get("dscr") else "—")
    m[1].metric("DTI",           f"{derived.get('dti_percent',0):.1f}%" if derived.get("dti_percent") else (
                                   f"{derived.get('dti_ratio',0)*100:.1f}%" if derived.get("dti_ratio") else "—"))
    m[2].metric("EBITDA (monthly)", _zar(derived.get("ebitda_monthly_zar") or derived.get("noi_monthly_zar")))
    m[3].metric("EBITDA Margin",
                f"{derived['ebitda_margin']*100:.1f}%" if derived.get("ebitda_margin") else "—")

    # ── Monthly summaries ────────────────────────────────────────────────────
    monthly = parsed.get("monthly_summaries") or []
    if monthly:
        st.divider()
        st.subheader("Monthly cashflow summaries")
        ms_rows = []
        for m_row in monthly:
            if not isinstance(m_row, dict):
                continue
            row: dict = {"Month": m_row.get("month") or ""}
            for fld in ("total_credits", "total_debits", "net_cashflow", "loan_repayments", "salary_payments", "opening_balance", "closing_balance"):
                v = m_row.get(fld)
                row[fld.replace("_", " ").title()] = f"R {v:,.0f}" if isinstance(v, (int, float)) and v else ("R 0" if v == 0 else "—")
            delinqs = m_row.get("delinquency_events") or []
            row["Delinquency events"] = "; ".join(str(d) for d in delinqs) if delinqs else ""
            ms_rows.append(row)
        if ms_rows:
            st.dataframe(pd.DataFrame(ms_rows), use_container_width=True, hide_index=True)

    # ── Full transactions table ──────────────────────────────────────────────
    txns = parsed.get("transactions") or []
    if txns:
        st.divider()
        st.subheader(f"All transactions ({len(txns)} rows)")
        txn_rows = []
        for t in txns:
            if not isinstance(t, dict):
                continue
            debit  = t.get("debit_zar") or t.get("debit") or 0
            credit = t.get("credit_zar") or t.get("credit") or 0
            bal    = t.get("balance_zar") or t.get("balance") or 0
            txn_rows.append({
                "Date":        t.get("date") or "",
                "Description": t.get("description") or "",
                "Debit (ZAR)":  f"R {debit:,.0f}"  if debit  else "—",
                "Credit (ZAR)": f"R {credit:,.0f}" if credit else "—",
                "Balance (ZAR)":f"R {bal:,.0f}"    if bal    else "—",
            })
        if txn_rows:
            st.dataframe(pd.DataFrame(txn_rows), use_container_width=True, hide_index=True)
    elif not monthly:
        st.info("No transactions extracted — upload a bank statement or financial document.")

    # ── Delinquency events ───────────────────────────────────────────────────
    delinq_events = parsed.get("delinquency_events") or []
    if delinq_events:
        st.divider()
        st.subheader("⚠️ Delinquency events detected")
        for ev in delinq_events:
            if isinstance(ev, dict):
                st.error(f"**{ev.get('date', '')}** — {ev.get('description', '')} (ZAR {ev.get('amount_zar', 0):,.0f})" if ev.get("amount_zar") else f"**{ev.get('date', '')}** — {ev.get('description', '')}")
            else:
                st.error(str(ev))


def _tab_cashflow(result: dict) -> None:
    delinq  = result.get("delinquency") or {}
    parsed  = result.get("parsed_document") or {}

    # Prefer monthly_summaries from parsed_document (more reliable)
    monthly = parsed.get("monthly_summaries") or []
    cashflow_from_parsed = [
        {"period": m.get("month") or "", "credits": float(m.get("total_credits") or 0),
         "debits": float(m.get("total_debits") or 0), "net": float(m.get("net_cashflow") or 0)}
        for m in monthly if isinstance(m, dict)
    ]
    cashflow = cashflow_from_parsed or delinq.get("cashflow_data") or []

    if not cashflow:
        st.info("No cashflow chart data — bank statement rows could not be parsed from OCR text.")
        return

    df_cf = pd.DataFrame(cashflow)
    if "period" in df_cf.columns:
        df_cf = df_cf.set_index("period")

    st.subheader("Monthly cashflow")
    if {"credits", "debits"}.issubset(df_cf.columns):
        st.bar_chart(df_cf[["credits", "debits"]])
    if "net" in df_cf.columns:
        st.subheader("Net cashflow trend")
        st.line_chart(df_cf[["net"]])

    st.divider()
    feats = delinq.get("ml_features") or {}
    if feats:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Avg monthly balance", _zar(feats.get("avg_monthly_balance")))
        c2.metric("Cashflow ratio",     f"{feats.get('cashflow_ratio', 0):.2f}")
        c3.metric("Repayment consistency", f"{feats.get('repayment_consistency', 0):.0%}")
        c4.metric("Delinquency count",  str(int(feats.get("delinquency_count", 0))))


def _tab_checks(result: dict) -> None:
    preview = result.get("policy_preview") or {}
    checks  = preview.get("checks") or {}
    if not checks:
        st.json(preview)
        return

    status_icon = {"pass": "✅", "fail": "❌", "not_available": "ℹ️", None: "⬜", True: "✅", False: "❌"}

    for name, body in checks.items():
        raw_ok  = body.get("ok")
        raw_st  = body.get("status") or raw_ok
        icon    = status_icon.get(raw_st) or status_icon.get(raw_ok) or "⬜"
        label   = name.replace("_", " ").title()
        expand  = raw_ok is False or raw_st in ("fail",)
        with st.expander(f"{icon} {label}", expanded=expand):
            # Friendly render rather than raw JSON
            for k, v in body.items():
                if k in ("ok", "status"):
                    continue
                if isinstance(v, list):
                    if v:
                        st.markdown(f"**{k.replace('_', ' ').title()}:**")
                        for item in v:
                            st.markdown(f"  - {item}")
                else:
                    st.markdown(f"**{k.replace('_', ' ').title()}:** {_fmt(v)}")

    ratios = result.get("ratios") or {}
    if ratios.get("info_notes"):
        st.divider()
        st.markdown("**ℹ️ Data availability notes:**")
        for n in ratios["info_notes"]:
            st.markdown(f'<div class="info-box">{n}</div>', unsafe_allow_html=True)


def _tab_ocr(result: dict) -> None:
    segs = result.get("ocr_segments") or []
    if not segs:
        st.caption("No OCR segments — upload a document to extract text.")
        return
    for i, seg in enumerate(segs):
        name = Path(seg.get("path", "")).name
        st.markdown(f"##### {name} · _{seg.get('category_hint', '')}_")
        text = seg.get("ocr_text") or ""
        st.text_area("", value=text[:15_000], height=220, key=f"ocr_{i}", disabled=True, label_visibility="collapsed")


# ══════════════════════════════════════════════════════════════════════════════
# WIZARD HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _emi_calc(principal: float, rate_pa: float, tenor_months: int) -> tuple[float, float, float]:
    """(monthly_emi, total_interest, total_repayment)."""
    if principal <= 0 or tenor_months <= 0:
        return 0.0, 0.0, 0.0
    if rate_pa <= 0:
        emi = principal / tenor_months
        return round(emi, 2), 0.0, round(principal, 2)
    r = rate_pa / 100.0 / 12.0
    factor = (1 + r) ** tenor_months
    emi = principal * r * factor / (factor - 1)
    total = emi * tenor_months
    return round(emi, 2), round(total - principal, 2), round(total, 2)


def _gauge_html(value: float, min_v: float, max_v: float, title: str) -> str:
    """Inline SVG semicircular gauge — correctly centred with arc aligned to track."""
    pct   = max(0.0, min(1.0, (value - min_v) / (max_v - min_v))) if (max_v - min_v) > 0 else 0.0
    cx, cy, r = 100, 100, 72          # centre at (100,100), radius 72
    sx, sy    = cx - r, cy            # track start: left (28, 100)
    ex_track  = cx + r                 # track end:   right (172, 100)

    # Active arc endpoint — theta measured from RIGHT, going counterclockwise
    # pct=0 → endpoint = start (left); pct=1 → endpoint = right
    theta = (1.0 - pct) * _math.pi    # 0 = rightmost, π = leftmost
    ex = cx + r * _math.cos(theta)
    ey = cy - r * _math.sin(theta)

    # For an upper-semicircle sweep (M left→top→right, clockwise, sweep=1):
    # large-arc-flag is ALWAYS 0 — the arc never exceeds 180° within the track
    color = ("#1a6e2e" if pct >= 0.65 else ("#e07b00" if pct >= 0.35 else "#c04000")) if value > 0 else "#e0e0e0"
    arc   = (
        f'<path d="M {sx},{sy} A {r},{r} 0 0 1 {ex:.2f},{ey:.2f}" '
        f'fill="none" stroke="{color}" stroke-width="16" stroke-linecap="round"/>'
    ) if pct > 0.005 else ""

    return (
        f'<div style="text-align:center;padding:4px 0;">'
        f'<div style="font-size:0.66rem;letter-spacing:0.1em;text-transform:uppercase;'
        f'color:#888;margin-bottom:2px;">{title}</div>'
        f'<svg viewBox="0 0 200 120" style="width:180px;display:block;margin:0 auto;">'
        # Background track
        f'<path d="M {sx},{sy} A {r},{r} 0 0 1 {ex_track},{cy}" '
        f'fill="none" stroke="#efefed" stroke-width="16" stroke-linecap="round"/>'
        # Coloured arc
        f'{arc}'
        # Centre value
        f'<text x="{cx}" y="{cy + 10}" text-anchor="middle" font-size="30" '
        f'font-weight="900" fill="#1a2e1a" font-family="sans-serif">{value:.0f}</text>'
        f'</svg>'
        # Min / max labels
        f'<div style="display:flex;justify-content:space-between;font-size:0.65rem;'
        f'color:#bbb;margin-top:-14px;padding:0 14px;">'
        f'<span>{min_v:.0f}</span><span>{max_v:.0f}</span></div></div>'
    )


def _step_bar_html(current: int) -> str:
    """Render the 5-step progress bar matching the design."""
    steps = ["Upload", "Extract", "Apply", "Decision", "Schedule"]
    parts = []
    for i, name in enumerate(steps, 1):
        if i == current:
            dot = (
                f'<div style="display:inline-flex;align-items:center;gap:8px;background:#1a3a1a;'
                f'border-radius:20px;padding:7px 16px;white-space:nowrap;">'
                f'<span style="background:rgba(255,255,255,.9);color:#1a3a1a;width:22px;height:22px;'
                f'border-radius:50%;display:inline-flex;align-items:center;justify-content:center;'
                f'font-size:.72rem;font-weight:800;">{i}</span>'
                f'<span style="color:#fff;font-size:.85rem;font-weight:700;">{name}</span></div>'
            )
        elif i < current:
            dot = (
                f'<div style="display:inline-flex;align-items:center;gap:7px;white-space:nowrap;">'
                f'<span style="background:#c0392b;color:#fff;width:22px;height:22px;border-radius:50%;'
                f'display:inline-flex;align-items:center;justify-content:center;font-size:.72rem;font-weight:700;">{i}</span>'
                f'<span style="color:#c0392b;font-size:.85rem;font-weight:600;">{name}</span></div>'
            )
        else:
            dot = (
                f'<div style="display:inline-flex;align-items:center;gap:7px;white-space:nowrap;">'
                f'<span style="background:#d0d0d0;color:#fff;width:22px;height:22px;border-radius:50%;'
                f'display:inline-flex;align-items:center;justify-content:center;font-size:.72rem;font-weight:600;">{i}</span>'
                f'<span style="color:#aaa;font-size:.85rem;">{name}</span></div>'
            )
        parts.append(dot)
    line = '<div style="flex:1;height:1.5px;background:#e0e0e0;min-width:24px;align-self:center;margin:0 4px;"></div>'
    return (
        f'<div style="display:flex;align-items:center;background:#fff;border:1px solid #e8ebe8;'
        f'border-radius:12px;padding:12px 20px;margin-bottom:22px;">{line.join(parts)}</div>'
    )


def _evaluate_rule_checks(uw_result: dict, loan_details: dict) -> list[dict]:
    """Read thresholds from config and evaluate against pipeline result."""
    from services.config_loader import load_underwriting
    cfg          = load_underwriting()
    ratios_cfg   = cfg.get("ratios", {})
    credit_cfg   = cfg.get("credit", {})
    business_cfg = cfg.get("business", {})

    ratios  = uw_result.get("ratios") or {}
    credit  = uw_result.get("credit_result") or {}
    parsed  = uw_result.get("parsed_document") or {}
    derived = parsed.get("derived") or {}
    merged  = uw_result.get("merged_applicant") or {}

    def _fv(src, *keys):
        for k in keys:
            v = src.get(k)
            if v is not None:
                try:
                    return float(v)
                except Exception:
                    pass
        return None

    checks: list[dict] = []

    dscr_min = float(ratios_cfg.get("dscr_min", 1.25))
    dscr = ratios.get("dscr")
    checks.append({"name": f"DSCR >= {dscr_min}", "value": f"{dscr:.2f}" if dscr else "N/A", "pass": ratios.get("dscr_ok")})

    dti_max = float(ratios_cfg.get("dti_max", 0.4))
    dti = ratios.get("dti")
    checks.append({"name": f"Debt-to-Income <= {dti_max*100:.0f}%", "value": f"{dti*100:.1f}%" if dti else "N/A", "pass": ratios.get("dti_ok")})

    em_min = float(ratios_cfg.get("ebitda_margin_min", 0.1))
    em = _fv(derived, "ebitda_margin") or _fv(merged, "ebitda_margin")
    checks.append({"name": f"EBITDA Margin >= {em_min*100:.0f}%", "value": f"{em*100:.1f}%" if em is not None else "N/A", "pass": (em >= em_min) if em is not None else None})

    cr_min = float(ratios_cfg.get("current_ratio_min", 1.2))
    cr = _fv(derived, "current_ratio") or _fv(merged, "current_ratio")
    checks.append({"name": f"Current Ratio >= {cr_min}", "value": f"{cr:.2f}" if cr is not None else "N/A", "pass": (cr >= cr_min) if cr is not None else None})

    b_min = float(credit_cfg.get("bureau_score_min", 600))
    bureau = _fv(credit, "bureau_score") or _fv(credit, "combined_score")
    checks.append({"name": f"Bureau Score >= {b_min:.0f}", "value": f"{bureau:.0f}" if bureau else "N/A", "pass": (bureau >= b_min) if bureau else None})

    yib_min = float(business_cfg.get("years_in_business_min", 2))
    yib = _fv(derived, "years_in_business") or _fv(merged, "years_in_business")
    checks.append({"name": f"Years In Business >= {yib_min:.0f}", "value": f"{yib:.0f}" if yib else "N/A", "pass": (yib >= yib_min) if yib else None})

    return checks


def _wiz_reset() -> None:
    for k in list(st.session_state.keys()):
        if k.startswith("wiz_"):
            del st.session_state[k]


def _wiz_app_header(app_id: str, entity_name: str) -> None:
    hcol, bcol = st.columns([4, 1])
    with hcol:
        st.markdown(f'<div class="page-crumb">APPLICATION · {(app_id or "")[:12].upper()}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="page-h1">{entity_name or "New Application"}</div>', unsafe_allow_html=True)
    with bcol:
        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
        if st.button("← Back to dashboard", key="wiz_back_top"):
            st.session_state.page_view = "dashboard"
            st.session_state.result = None
            _wiz_reset()
            st.rerun()


_DOC_TYPE_OPTIONS = [
    ("auto",               "Auto-detect"),
    ("bank_statement",     "Bank Statement"),
    ("income_statement",   "Annual Financial Statement"),
    ("management_accounts","Management Accounts"),
    ("payslip",            "Payslip / Salary Advice"),
    ("other",              "Other"),
]
_DOC_TYPE_LABELS = {k: v for k, v in _DOC_TYPE_OPTIONS}
_DOC_TYPE_KEYS   = [k for k, _ in _DOC_TYPE_OPTIONS]
_DOC_TYPE_VALUES = [v for _, v in _DOC_TYPE_OPTIONS]


# ── Step 1: Upload ─────────────────────────────────────────────────────────────

def _wiz_step_upload() -> None:
    app_id = st.session_state.get("wiz_app_id", "")
    entity = st.session_state.get("wiz_entity_name", "New Application")
    _wiz_app_header(app_id, entity)
    st.markdown(_step_bar_html(1), unsafe_allow_html=True)

    # Initialise staged-files list in session state
    if "wiz_staged_files" not in st.session_state:
        st.session_state.wiz_staged_files = []   # list of {name, bytes, type_hint}

    left, right = st.columns([2, 1], gap="large")

    with left:
        st.markdown('<div class="wiz-card">', unsafe_allow_html=True)
        st.markdown('<div class="wiz-step-label">STEP 1</div>', unsafe_allow_html=True)
        st.markdown('<div class="wiz-step-title">Upload Business Documents</div>', unsafe_allow_html=True)
        st.caption("You can upload **multiple** bank statements and/or financial statements together.")

        new_files = st.file_uploader(
            "Drop files here or click to browse",
            type=["pdf", "png", "jpg", "jpeg", "txt", "csv"],
            accept_multiple_files=True,
            key="wiz_file_upload_multi",
            help="PDF, PNG, JPG or TXT — add as many documents as needed",
            label_visibility="collapsed",
        )

        # Add newly dropped files to staged list (avoid duplicates by name+size)
        if new_files:
            existing_keys = {(f["name"], f["size"]) for f in st.session_state.wiz_staged_files}
            for uf in new_files:
                key = (uf.name, uf.size)
                if key not in existing_keys:
                    st.session_state.wiz_staged_files.append({
                        "name":      uf.name,
                        "bytes":     uf.getvalue(),
                        "size":      uf.size,
                        "type_hint": "auto",
                    })
                    existing_keys.add(key)

        st.markdown("</div>", unsafe_allow_html=True)

        # ── Staged files list ──────────────────────────────────────────────────
        staged = st.session_state.wiz_staged_files
        if staged:
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            st.markdown('<div class="wiz-card">', unsafe_allow_html=True)
            st.markdown(
                f'<div style="font-size:0.68rem;letter-spacing:.1em;text-transform:uppercase;'
                f'color:#888;margin-bottom:12px;">STAGED DOCUMENTS ({len(staged)})</div>',
                unsafe_allow_html=True,
            )

            to_remove: list[int] = []
            for i, f in enumerate(staged):
                fc1, fc2, fc3 = st.columns([3, 2.5, 0.6])
                size_kb = f["size"] / 1024
                fc1.markdown(
                    f'<div style="font-size:0.85rem;font-weight:600;color:#1a2e1a;padding-top:6px;">'
                    f'📄 {f["name"]}</div>'
                    f'<div style="font-size:0.7rem;color:#aaa;">{size_kb:.1f} KB</div>',
                    unsafe_allow_html=True,
                )
                cur_idx = _DOC_TYPE_KEYS.index(f["type_hint"]) if f["type_hint"] in _DOC_TYPE_KEYS else 0
                new_type = fc2.selectbox(
                    "Type", _DOC_TYPE_VALUES,
                    index=cur_idx,
                    key=f"dtype_{i}_{f['name']}",
                    label_visibility="collapsed",
                )
                staged[i]["type_hint"] = _DOC_TYPE_KEYS[_DOC_TYPE_VALUES.index(new_type)]
                if fc3.button("✕", key=f"rm_{i}_{f['name']}", help="Remove"):
                    to_remove.append(i)

            for idx in reversed(to_remove):
                st.session_state.wiz_staged_files.pop(idx)
                st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        can_proceed = len(st.session_state.wiz_staged_files) > 0
        if st.button(
            f"Extract Fields → ({len(staged)} doc{'s' if len(staged) != 1 else ''})",
            type="primary",
            disabled=not can_proceed,
            use_container_width=True,
            key="wiz_extract_btn",
        ):
            # Save to temp files with type hints
            saved: list[dict] = []
            for f in staged:
                suffix = Path(f["name"]).suffix or ".pdf"
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(f["bytes"])
                tmp.close()
                saved.append({"path": tmp.name, "name": f["name"], "type_hint": f["type_hint"]})
            st.session_state.wiz_uploaded_paths = saved
            # Clear old parsed cache so extract step re-runs
            for k in ("wiz_parsed_doc", "wiz_ocr_segments", "wiz_per_doc_results"):
                st.session_state.pop(k, None)
            st.session_state.wiz_step = 2
            st.rerun()

    with right:
        _extract_list = [
            "Company name & registration",
            "Annual revenue & EBITDA",
            "Net profit / loss",
            "Total & current assets",
            "Total & current liabilities",
            "Existing debt & service",
            "Monthly cashflow (bank stmts)",
            "Delinquency events",
            "Bureau / credit score",
            "Years in business",
        ]
        items_html = "".join(
            f'<div style="display:flex;align-items:center;gap:9px;padding:5px 0;'
            f'font-size:0.84rem;color:#333;">'
            f'<span style="color:#c0392b;font-size:1rem;">●</span>{item}</div>'
            for item in _extract_list
        )
        st.markdown(
            f'<div class="wiz-card">'
            f'<div style="font-size:0.68rem;letter-spacing:0.1em;text-transform:uppercase;'
            f'color:#888;margin-bottom:14px;">WHAT WE EXTRACT</div>'
            f'{items_html}'
            f'<div style="font-size:0.72rem;color:#aaa;margin-top:16px;line-height:1.5;">'
            f'Multiple documents are merged — financial statement ratios take priority '
            f'over bank statement averages.</div></div>',
            unsafe_allow_html=True,
        )


# ── Step 2: Extract ────────────────────────────────────────────────────────────

def _wiz_step_extract() -> None:
    app_id = st.session_state.get("wiz_app_id", "")
    entity = st.session_state.get("wiz_entity_name", "New Application")
    _wiz_app_header(app_id, entity)
    st.markdown(_step_bar_html(2), unsafe_allow_html=True)

    # wiz_uploaded_paths is now list of {path, name, type_hint}
    file_items: list[dict] = st.session_state.get("wiz_uploaded_paths") or []
    # Back-compat: old format was list of path strings
    if file_items and isinstance(file_items[0], str):
        file_items = [{"path": p, "name": Path(p).name, "type_hint": "auto"} for p in file_items]

    if not st.session_state.get("wiz_parsed_doc"):
        from services.ocr_service import partition_file_to_text
        from services.document_parser import parse_financial_document, merge_parsed_documents
        from services.config_loader import load_underwriting

        uw_cfg = load_underwriting()
        ctx = {
            "dscr_min":    float((uw_cfg.get("ratios") or {}).get("dscr_min", 1.25)),
            "dti_max":     float((uw_cfg.get("ratios") or {}).get("dti_max", 0.4)),
            "score_min":   float((uw_cfg.get("credit") or {}).get("score_min", 650)),
            "premium_zar": 0,
        }

        per_doc_results: list[dict] = []
        ocr_segments: list[dict]    = []

        progress = st.progress(0, text="Starting extraction…")
        total = len(file_items) or 1

        for i, fi in enumerate(file_items):
            pct  = int((i / total) * 90)
            name = fi.get("name", f"Document {i+1}")
            progress.progress(pct, text=f"Extracting: {name}…")

            ocr_text  = partition_file_to_text(fi["path"])
            hint      = fi.get("type_hint") or "auto"
            if hint == "auto":
                hint = "bank_statement"   # fallback; LLM will self-detect
            parsed_i  = parse_financial_document(ocr_text, category_hint=hint, underwriting_context=ctx)
            parsed_i["_source_file"] = name
            per_doc_results.append(parsed_i)
            ocr_segments.append({"path": fi["path"], "category_hint": hint, "ocr_text": ocr_text})

        progress.progress(95, text="Merging documents…")
        merged = merge_parsed_documents(per_doc_results)
        progress.progress(100, text="Done.")
        progress.empty()

        st.session_state.wiz_per_doc_results = per_doc_results
        st.session_state.wiz_parsed_doc      = merged
        st.session_state.wiz_ocr_segments    = ocr_segments
        entity_name = merged.get("entity_name") or merged.get("account_holder_name") or "Unknown Entity"
        st.session_state.wiz_entity_name = entity_name

    parsed  = st.session_state.wiz_parsed_doc or {}
    derived = parsed.get("derived") or {}

    # ── Per-document summary cards ─────────────────────────────────────────────
    per_docs: list[dict] = st.session_state.get("wiz_per_doc_results") or []
    if len(per_docs) > 1:
        st.markdown(
            f'<div style="font-size:0.68rem;letter-spacing:.1em;text-transform:uppercase;'
            f'color:#888;margin:8px 0 10px;">DOCUMENTS PROCESSED ({len(per_docs)})</div>',
            unsafe_allow_html=True,
        )
        doc_cols = st.columns(min(len(per_docs), 3))
        for ci, (col, pd_) in enumerate(zip(doc_cols * 10, per_docs)):
            dtype  = (pd_.get("document_type") or "unknown").replace("_", " ").title()
            fname  = pd_.get("_source_file", f"Doc {ci+1}")
            ename  = pd_.get("entity_name") or "—"
            mc     = pd_.get("months_covered")
            delinq = len(pd_.get("delinquency_events") or [])
            rev    = (pd_.get("derived") or {}).get("avg_monthly_income_zar")
            col.markdown(
                f'<div style="background:#f8faf8;border:1px solid #e2e8e2;border-radius:10px;'
                f'padding:14px 16px;margin-bottom:12px;">'
                f'<div style="font-size:0.65rem;text-transform:uppercase;color:#888;'
                f'letter-spacing:.08em;margin-bottom:4px;">{dtype}</div>'
                f'<div style="font-weight:700;font-size:0.88rem;color:#1a2e1a;'
                f'margin-bottom:6px;white-space:nowrap;overflow:hidden;'
                f'text-overflow:ellipsis;" title="{fname}">{fname[:32]}</div>'
                f'<div style="font-size:0.78rem;color:#555;">'
                f'Entity: <b>{ename[:24]}</b><br/>'
                f'Months: <b>{mc or "—"}</b> &nbsp;|&nbsp; '
                f'Delinquency: <b style="color:{("#c04000" if delinq else "#1a6e2e")};">'
                f'{delinq} event{"s" if delinq != 1 else ""}</b><br/>'
                f'Rev/mo: <b>{"R {:,.0f}".format(rev) if rev else "—"}</b>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        st.markdown('<hr style="margin:8px 0 16px;border-color:#eee;">', unsafe_allow_html=True)

    st.markdown('<div class="wiz-card">', unsafe_allow_html=True)
    st.markdown('<div class="wiz-step-label">STEP 2</div>', unsafe_allow_html=True)
    mc_total = parsed.get("months_covered")
    title_suffix = f" — {len(per_docs)} documents merged" if len(per_docs) > 1 else ""
    st.markdown(f'<div class="wiz-step-title">Extracted Fields{title_suffix}</div>', unsafe_allow_html=True)

    # Entity overview
    c1, c2, c3, c4 = st.columns(4)
    mc_raw  = parsed.get("months_covered")
    mc_disp = f"{mc_raw} mo" if mc_raw else "—"
    # Annotate inferred annual periods
    if mc_raw == 12:
        doc_t = (parsed.get("document_type") or "").lower()
        if doc_t in ("income_statement", "balance_sheet", "management_accounts"):
            mc_disp = "12 mo (annual)"
    c1.metric("Entity / Name",    parsed.get("entity_name") or "—")
    c2.metric("Document Type",    (parsed.get("document_type") or "—").replace("_", " ").title())
    c3.metric("Months Covered",   mc_disp)
    c4.metric("Currency",         parsed.get("currency") or "ZAR")

    st.divider()

    # Financial highlights — correct business formulae
    fc1, fc2, fc3, fc4 = st.columns(4)
    avg_inc   = derived.get("avg_monthly_income_zar")
    opex      = derived.get("opex_monthly_zar")
    ebitda_m  = derived.get("ebitda_monthly_zar")
    ebitda_mg = derived.get("ebitda_margin")
    # Fallback: compute EBITDA from income − opex if LLM didn't return it
    if ebitda_m is None and avg_inc and opex:
        ebitda_m  = avg_inc - opex
        ebitda_mg = ebitda_m / avg_inc if avg_inc else None
    dscr_v    = derived.get("dscr")
    dti_v     = derived.get("dti_percent") or (
                (derived.get("dti_ratio") or 0) * 100 or None)
    debt_svc  = (derived.get("debt_service_monthly_zar")
                 or derived.get("total_monthly_debt_zar")
                 or derived.get("loan_repayment_monthly_zar"))

    fc1.metric("Monthly Revenue",        f"R {avg_inc:,.0f}"       if avg_inc   else "—")
    fc2.metric("EBITDA / month",         f"R {ebitda_m:,.0f}"      if ebitda_m  else "—")
    fc3.metric("EBITDA Margin",          f"{ebitda_mg*100:.1f}%"   if ebitda_mg else "—")
    fc4.metric("OPEX / month",           f"R {opex:,.0f}"          if opex      else "—")

    st.divider()

    fc5, fc6, fc7, fc8 = st.columns(4)
    fc5.metric("Debt Service / month",   f"R {debt_svc:,.0f}"      if debt_svc  else "—")
    fc6.metric("DSCR  (EBITDA/Debt)",   f"{dscr_v:.2f}"            if dscr_v    else "—")
    fc7.metric("DTI  (Debt/Revenue)",   f"{dti_v:.1f}%"            if dti_v     else "—")
    fc8.metric("Income Stability",       derived.get("income_stability") or "—")

    st.markdown("</div>", unsafe_allow_html=True)

    delinq_events = parsed.get("delinquency_events") or []
    if delinq_events:
        st.error(f"⚠️  {len(delinq_events)} delinquency event(s) detected in document — will impact credit assessment.")

    txns = parsed.get("transactions") or []
    if txns:
        with st.expander(f"📋  {len(txns)} transactions extracted", expanded=False):
            rows = [{"Date": t.get("date", ""), "Description": t.get("description", ""),
                     "Debit": f"R {t['debit_zar']:,.0f}" if t.get("debit_zar") else "—",
                     "Credit": f"R {t['credit_zar']:,.0f}" if t.get("credit_zar") else "—",
                     "Balance": f"R {t['balance_zar']:,.0f}" if t.get("balance_zar") else "—"}
                    for t in txns if isinstance(t, dict)]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    col_back, _, col_cont = st.columns([1, 2, 2])
    with col_back:
        if st.button("← Back", key="wiz2_back"):
            st.session_state.wiz_step = 1
            st.session_state.pop("wiz_parsed_doc", None)
            st.rerun()
    with col_cont:
        if st.button("Continue to Loan Details →", type="primary", use_container_width=True, key="wiz2_cont"):
            st.session_state.wiz_step = 3
            st.rerun()


# ── Step 3: Apply ──────────────────────────────────────────────────────────────

_LOAN_TYPES = ["Structured Annuity", "Term Loan", "Equipment Finance", "Working Capital", "Revolving Credit", "Mortgage Bond"]

def _wiz_step_apply() -> None:
    app_id = st.session_state.get("wiz_app_id", "")
    entity = st.session_state.get("wiz_entity_name", "New Application")
    _wiz_app_header(app_id, entity)
    st.markdown(_step_bar_html(3), unsafe_allow_html=True)

    left, right = st.columns([2, 1], gap="large")
    with left:
        st.markdown('<div class="wiz-card">', unsafe_allow_html=True)
        st.markdown('<div class="wiz-step-label">STEP 3</div>', unsafe_allow_html=True)
        st.markdown('<div class="wiz-step-title">Loan Application Details</div>', unsafe_allow_html=True)

        default_lt = st.session_state.get("wiz_loan_type", "Structured Annuity")
        lt_idx = _LOAN_TYPES.index(default_lt) if default_lt in _LOAN_TYPES else 0
        loan_type = st.selectbox("LOAN TYPE", _LOAN_TYPES, index=lt_idx, key="wiz_lt_sel")

        a1, a2 = st.columns(2)
        with a1:
            loan_amount = st.number_input("LOAN AMOUNT (ZAR)", min_value=0.0,
                value=float(st.session_state.get("wiz_loan_amount", 2_000_000)),
                step=50_000.0, format="%.0f", key="wiz_amt")
        with a2:
            tenor = st.number_input("TENOR (MONTHS)", min_value=1, max_value=360,
                value=int(st.session_state.get("wiz_tenor_months", 60)),
                step=6, key="wiz_tenor")
        rate_pa = st.number_input("INTEREST RATE (% P.A.)", min_value=0.0, max_value=50.0,
            value=float(st.session_state.get("wiz_rate_pa", 14.5)),
            step=0.1, format="%.1f", key="wiz_rate")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        cb, _, cr = st.columns([1, 1, 2])
        with cb:
            if st.button("← Back", key="wiz3_back"):
                st.session_state.wiz_step = 2
                st.rerun()
        with cr:
            if st.button("Run Underwriting →", type="primary", use_container_width=True, key="wiz3_run"):
                st.session_state.wiz_loan_type    = loan_type
                st.session_state.wiz_loan_amount  = float(loan_amount)
                st.session_state.wiz_tenor_months = int(tenor)
                st.session_state.wiz_rate_pa      = float(rate_pa)
                st.session_state.pop("wiz_uw_result", None)
                st.session_state.wiz_step = 4
                st.rerun()

    with right:
        emi, total_int, total_rep = _emi_calc(float(loan_amount), float(rate_pa), int(tenor))
        st.markdown(
            f'<div class="wiz-emi-card">'
            f'<div class="wiz-emi-label">ESTIMATED EMI</div>'
            f'<div class="wiz-emi-amount">R {emi:,.0f}</div>'
            f'<div class="wiz-emi-label">per month</div>'
            f'<div style="height:14px;"></div>'
            f'<div class="wiz-emi-row"><span style="color:#666;">Total Interest</span>'
            f'<span style="font-weight:700;color:#1a2e1a;">R {total_int:,.0f}</span></div>'
            f'<div class="wiz-emi-row"><span style="color:#666;">Total Repayment</span>'
            f'<span style="font-weight:700;color:#1a2e1a;">R {total_rep:,.0f}</span></div>'
            f'<div class="wiz-emi-row"><span style="color:#666;">Tenor</span>'
            f'<span style="font-weight:700;color:#1a2e1a;">{int(tenor)} months</span></div>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Step 4: Decision ───────────────────────────────────────────────────────────

def _wiz_step_decision() -> None:
    app_id = st.session_state.get("wiz_app_id", "")
    entity = st.session_state.get("wiz_entity_name", "New Application")
    _wiz_app_header(app_id, entity)
    st.markdown(_step_bar_html(4), unsafe_allow_html=True)

    if not st.session_state.get("wiz_uw_result"):
        loan_amount = st.session_state.get("wiz_loan_amount", 0)
        tenor       = int(st.session_state.get("wiz_tenor_months", 60))
        rate_pa     = st.session_state.get("wiz_rate_pa", 14.5)
        loan_type   = st.session_state.get("wiz_loan_type", "Structured Annuity")
        emi, _, _   = _emi_calc(loan_amount, rate_pa, tenor)

        with st.spinner("Running AI underwriting analysis — OCR → LLM extraction → Credit scoring → Policy rules…"):
            try:
                initial = {
                    "application_id": app_id,
                    "applicant_submission": {
                        "date_of_birth": "1970-01-01",
                        "proposed_annuity_premium_zar": loan_amount,
                        "loan_amount_zar": loan_amount,
                        "loan_tenor_months": tenor,
                        "loan_rate_pa": rate_pa,
                        "loan_type": loan_type,
                        "monthly_emi_zar": emi,
                    },
                    "uploaded_file_paths": st.session_state.get("wiz_uploaded_paths") or [],
                    "category_hints": ["bank_statement"],
                    "ocr_segments":   st.session_state.get("wiz_ocr_segments") or [],
                    "parsed_document": st.session_state.get("wiz_parsed_doc") or {},
                    "errors": [],
                }
                result = run_application(initial)
                st.session_state.wiz_uw_result = result
                try:
                    save_application(result, loan_type=loan_type)
                except Exception:
                    pass
            except Exception as e:
                st.error(f"Pipeline error: {e}")
                st.info("Check `OPENAI_API_KEY` or `OPEN_API` in `env.local`.")
                if st.button("← Back", key="wiz4_err_back"):
                    st.session_state.wiz_step = 3
                    st.rerun()
                return

    result      = st.session_state.wiz_uw_result
    decision    = (result.get("decision") or "PENDING").upper()
    assess      = result.get("llm_credit_assessment") or {}
    delinq      = result.get("delinquency") or {}
    credit      = result.get("credit_result") or {}
    ratios      = result.get("ratios") or {}
    parsed      = result.get("parsed_document") or {}
    derived     = parsed.get("derived") or {}
    loan_details = {
        "type":         st.session_state.get("wiz_loan_type", "—"),
        "amount":       st.session_state.get("wiz_loan_amount", 0),
        "tenor_months": int(st.session_state.get("wiz_tenor_months", 60)),
        "rate_pa":      st.session_state.get("wiz_rate_pa", 0),
    }
    emi, total_int, total_rep = _emi_calc(loan_details["amount"], loan_details["rate_pa"], loan_details["tenor_months"])

    # ── Decision banner ────────────────────────────────────────────────────────
    d_class = {
        "STP":                  "wiz-decision-approved",
        "CONDITIONAL_APPROVAL": "wiz-decision-conditional",
        "MANUAL_REVIEW":        "wiz-decision-review",
        "DECLINED":             "wiz-decision-declined",
    }.get(decision, "wiz-decision-pending")
    d_label = {
        "STP":                  "APPROVED",
        "CONDITIONAL_APPROVAL": "CONDITIONALLY APPROVED",
        "MANUAL_REVIEW":        "PENDING",
        "DECLINED":             "REJECTED",
    }.get(decision, "PENDING")
    ai_text = (
        assess.get("affordability_comment")
        or " ".join(result.get("review_reasons") or [])
        or "AI analysis complete. See scores and rule checks below."
    )
    pos_factors = assess.get("positive_factors") or []
    risk_factors = assess.get("risk_factors") or []
    ai_detail = ""
    if pos_factors or risk_factors:
        ai_detail = " ".join(pos_factors[:3]) + (" " if pos_factors and risk_factors else "") + " ".join(risk_factors[:2])

    st.markdown(
        f'<div class="wiz-card">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        f'<div><div class="wiz-step-label">UNDERWRITING DECISION</div>'
        f'<div class="{d_class}">{d_label}</div></div>'
        f'<div style="font-size:0.78rem;color:#888;">✓ AI-assisted reasoning</div></div>'
        f'<div style="font-size:0.87rem;color:#555;margin-top:14px;line-height:1.65;">{ai_text}'
        f'{(" " + ai_detail) if ai_detail else ""}</div></div>',
        unsafe_allow_html=True,
    )

    # ── Scores + Loan snapshot ─────────────────────────────────────────────────
    g1, g2, snap = st.columns([1, 1, 1])
    bureau_sc  = float(credit.get("bureau_score") or credit.get("combined_score") or 0)
    ml_raw     = float(delinq.get("credit_score") or assess.get("credit_score") or 0)
    ml_norm    = round((ml_raw - 300) / 5.5, 0) if ml_raw >= 300 else ml_raw

    with g1:
        st.markdown(
            f'<div class="wiz-card" style="padding:20px;">{_gauge_html(bureau_sc, 200, 830, "BUREAU SCORE")}</div>',
            unsafe_allow_html=True,
        )
    with g2:
        st.markdown(
            f'<div class="wiz-card" style="padding:20px;">{_gauge_html(ml_norm, 0, 100, "ML COMPOSITE SCORE")}</div>',
            unsafe_allow_html=True,
        )
    with snap:
        st.markdown(
            f'<div class="wiz-card" style="padding:20px;height:100%;">'
            f'<div style="font-size:0.68rem;letter-spacing:.1em;text-transform:uppercase;color:#888;margin-bottom:14px;">LOAN SNAPSHOT</div>'
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<tr><td style="color:#888;font-size:.82rem;padding:6px 0;">Type</td><td style="text-align:right;font-weight:700;font-size:.85rem;">{loan_details["type"]}</td></tr>'
            f'<tr><td style="color:#888;font-size:.82rem;padding:6px 0;">Amount</td><td style="text-align:right;font-weight:700;font-size:.85rem;">R {loan_details["amount"]:,.0f}</td></tr>'
            f'<tr><td style="color:#888;font-size:.82rem;padding:6px 0;">Tenor</td><td style="text-align:right;font-weight:700;font-size:.85rem;">{loan_details["tenor_months"]} mo</td></tr>'
            f'<tr><td style="color:#888;font-size:.82rem;padding:6px 0;">Rate</td><td style="text-align:right;font-weight:700;font-size:.85rem;">{loan_details["rate_pa"]:.1f}%</td></tr>'
            f'</table></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Key financial ratios grid ──────────────────────────────────────────────
    total_monthly_debt = (derived.get("total_monthly_debt_zar") or 0) + emi

    def _pct(v):   return f"{v*100:.1f}%"  if v is not None else "—"
    def _dec(v):   return f"{v:.2f}"       if v is not None else "—"

    # Pull from ratios dict first (risk_calc computes fallbacks), then derived
    em   = ratios.get("ebitda_margin")   or derived.get("ebitda_margin")
    npm  = ratios.get("net_profit_margin") or derived.get("net_profit_margin")
    cr   = ratios.get("current_ratio")   or derived.get("current_ratio")
    de   = ratios.get("debt_to_equity")  or derived.get("debt_to_equity")

    ratio_items = [
        ("DSCR",               f"{ratios['dscr']:.2f}" if ratios.get("dscr") else "—"),
        ("DEBT-TO-INCOME",     f"{ratios['dti']*100:.1f}%" if ratios.get("dti") else "—"),
        ("EBITDA MARGIN",      _pct(em)),
        ("CURRENT RATIO",      _dec(cr)),
        ("DEBT-TO-EQUITY",     _dec(de)),
        ("NET PROFIT MARGIN",  _pct(npm)),
        ("NEW LOAN MONTHLY",   f"R {emi:,.1f}" if emi else "—"),
        ("TOTAL MONTHLY DEBT", f"R {total_monthly_debt:,.1f}" if total_monthly_debt else "—"),
    ]
    tiles = "".join(
        f'<div class="wiz-ratio-tile"><div class="wiz-ratio-lbl">{lbl}</div><div class="wiz-ratio-val">{val}</div></div>'
        for lbl, val in ratio_items
    )
    st.markdown(
        f'<div class="wiz-card">'
        f'<div style="font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:#888;margin-bottom:14px;">KEY FINANCIAL RATIOS</div>'
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">{tiles}</div></div>',
        unsafe_allow_html=True,
    )

    # ── SA Policy rule checks ──────────────────────────────────────────────────
    checks = _evaluate_rule_checks(result, loan_details)
    check_cards_html = []
    for ch in checks:
        ok = ch.get("pass")
        if ok is True:
            bg, icon, bc, bt = "#e8f5e8", "✓", "#1a6e2e", "PASS"
        elif ok is False:
            bg, icon, bc, bt = "#fce8e8", "✗", "#8b0000", "FAIL"
        else:
            bg, icon, bc, bt = "#f5f5f0", "–", "#888",    "N/A"
        val_t = f'<span style="font-size:.74rem;color:#888;">Value: {ch["value"]}</span>' if ch["value"] != "N/A" else ""
        check_cards_html.append(
            f'<div style="background:{bg};border-radius:8px;padding:14px 18px;display:flex;align-items:center;justify-content:space-between;">'
            f'<div style="display:flex;align-items:center;gap:10px;">'
            f'<span style="color:{bc};font-size:1rem;font-weight:700;">{icon}</span>'
            f'<div><div style="font-size:.85rem;font-weight:700;color:#1a2e1a;">{ch["name"]}</div>{val_t}</div></div>'
            f'<span style="background:{bc};color:#fff;padding:3px 10px;border-radius:4px;font-size:.72rem;font-weight:700;">{bt}</span></div>'
        )
    st.markdown(
        f'<div class="wiz-card">'
        f'<div style="font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:#888;margin-bottom:14px;">SA POLICY RULE CHECKS</div>'
        f'<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;">{"".join(check_cards_html)}</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    cb2, _, cs2 = st.columns([1, 2, 2])
    with cb2:
        if st.button("← Back", key="wiz4_back"):
            st.session_state.wiz_step = 3
            st.session_state.pop("wiz_uw_result", None)
            st.rerun()
    with cs2:
        if st.button("View Amortization Schedule →", type="primary", use_container_width=True, key="wiz4_sched"):
            st.session_state.wiz_step = 5
            st.rerun()


# ── Step 5: Schedule ───────────────────────────────────────────────────────────

def _wiz_step_schedule() -> None:
    app_id = st.session_state.get("wiz_app_id", "")
    entity = st.session_state.get("wiz_entity_name", "New Application")
    _wiz_app_header(app_id, entity)
    st.markdown(_step_bar_html(5), unsafe_allow_html=True)

    loan_amount = st.session_state.get("wiz_loan_amount", 0)
    tenor       = int(st.session_state.get("wiz_tenor_months", 60))
    rate_pa     = st.session_state.get("wiz_rate_pa", 0)

    if not loan_amount:
        st.markdown(
            '<div class="wiz-card" style="text-align:center;padding:60px;">'
            '<div style="color:#888;font-size:1rem;margin-bottom:16px;">No schedule yet. Run the decision step first.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("← Back", key="wiz5_back_empty"):
            st.session_state.wiz_step = 4
            st.rerun()
        return

    emi, total_int, total_rep = _emi_calc(loan_amount, rate_pa, tenor)
    r = rate_pa / 100.0 / 12.0
    rows, balance, cumulative = [], loan_amount, 0.0
    for m in range(1, tenor + 1):
        interest_comp  = balance * r if r > 0 else 0.0
        principal_comp = emi - interest_comp
        balance        = max(0.0, balance - principal_comp)
        cumulative    += emi
        rows.append({
            "Month": m,
            "EMI (ZAR)": round(emi, 2),
            "Interest (ZAR)": round(interest_comp, 2),
            "Principal (ZAR)": round(principal_comp, 2),
            "Cumulative Paid (ZAR)": round(cumulative, 2),
            "Outstanding Balance (ZAR)": round(balance, 2),
        })

    st.markdown('<div class="wiz-card">', unsafe_allow_html=True)
    st.markdown('<div class="wiz-step-label">STEP 5</div>', unsafe_allow_html=True)
    st.markdown('<div class="wiz-step-title">Amortization Schedule</div>', unsafe_allow_html=True)
    cs1, cs2, cs3, cs4 = st.columns(4)
    cs1.metric("Monthly EMI",     f"R {emi:,.0f}")
    cs2.metric("Total Interest",  f"R {total_int:,.0f}")
    cs3.metric("Total Repayment", f"R {total_rep:,.0f}")
    cs4.metric("Tenor",           f"{tenor} months")
    st.divider()
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    cb3, _ = st.columns([1, 5])
    with cb3:
        if st.button("← Back", key="wiz5_back"):
            st.session_state.wiz_step = 4
            st.rerun()


# ── Loan Applications Dashboard ──────────────────────────────────────────────

def _decision_badge(decision: str) -> str:
    d = (decision or "").upper()
    norm = {
        "STP":                  "APPROVED",
        "CONDITIONAL_APPROVAL": "CONDITIONALLY APPROVED",
        "MANUAL_REVIEW":        "PENDING",
        "DECLINED":             "REJECTED",
        "REVIEW":               "PENDING",
    }.get(d, d)
    if norm == "APPROVED":
        return '<span class="badge-approved">● APPROVED</span>'
    if norm == "CONDITIONALLY APPROVED":
        return '<span class="badge-conditional">◑ CONDITIONALLY APPROVED</span>'
    if norm in ("REJECTED", "DECLINED"):
        return '<span class="badge-declined">● REJECTED</span>'
    if norm == "PENDING":
        return '<span class="badge-review">● PENDING</span>'
    return f'<span class="badge-decided">{norm}</span>'


def _status_badge(status: str) -> str:
    s = (status or "").upper()
    if s == "IN_PROGRESS":
        return '<span class="badge-in-progress">IN PROGRESS</span>'
    return '<span class="badge-decided">DECIDED</span>'


def _kv_row_html(label: str, value: str) -> str:
    return (
        f'<div class="detail-kv">'
        f'<span class="detail-kv-label">{label}</span>'
        f'<span class="detail-kv-value">{value}</span>'
        f'</div>'
    )


def _render_app_detail() -> None:
    """Read-only detail view for a saved application."""
    app_id = st.session_state.get("dash_selected_id", "")
    records = load_all()
    rec = next((r for r in records if r.get("id") == app_id), None)

    # Back button
    st.markdown('<div class="back-btn-row">', unsafe_allow_html=True)
    if st.button("← Back to Dashboard", key="detail_back"):
        st.session_state.page_view = "dashboard"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    if not rec:
        st.error(f"Application {app_id} not found.")
        return

    name     = rec.get("entity_name") or "Unknown"
    loan_t   = rec.get("loan_type") or "—"
    req      = rec.get("requested_zar") or 0
    decision = rec.get("decision") or "—"
    status   = rec.get("status") or "—"
    created  = (rec.get("created_at") or "")[:19].replace("T", " ")
    updated  = (rec.get("updated_at") or "")[:19].replace("T", " ")
    dscr     = rec.get("dscr")
    dti      = rec.get("dti_percent")
    ml       = rec.get("ml_score")
    bureau   = rec.get("bureau_score")
    grade    = rec.get("credit_grade") or "—"
    delinq   = rec.get("delinquency_count", 0)
    months   = rec.get("months_covered")
    reasons  = rec.get("review_reasons") or []
    notes    = rec.get("notes") or ""

    # ── Header card ────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="detail-header-card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;">
            <div>
              <p class="detail-meta">APPLICATION · {app_id}</p>
              <h2 class="detail-title">{name}</h2>
              <p class="detail-meta">Created {created}{(" · Updated " + updated) if updated else ""}</p>
            </div>
            <div style="text-align:right;">
              {_decision_badge(decision)}
              <br/><br/>
              {_status_badge(status)}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Three info columns ──────────────────────────────────────────────────────
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        rows = (
            _kv_row_html("Loan Type", loan_t)
            + _kv_row_html("Requested Amount", f"R {req:,.0f}" if req else "—")
            + _kv_row_html("Months Covered", str(months) if months else "—")
            + _kv_row_html("Delinquency Events", str(delinq))
        )
        st.markdown(
            f'<div class="detail-section">'
            f'<p class="detail-section-title">Application Details</p>{rows}</div>',
            unsafe_allow_html=True,
        )

    with col_b:
        rows = (
            _kv_row_html("DSCR", f"{dscr:.2f}" if dscr is not None else "—")
            + _kv_row_html("DTI", f"{dti:.1f}%" if dti is not None else "—")
        )
        st.markdown(
            f'<div class="detail-section">'
            f'<p class="detail-section-title">Financial Metrics</p>{rows}</div>',
            unsafe_allow_html=True,
        )

    with col_c:
        rows = (
            _kv_row_html("Bureau Score", f"{int(bureau)}" if bureau else "—")
            + _kv_row_html("ML Score", f"{ml:.2f}" if ml is not None else "—")
            + _kv_row_html("Credit Grade", grade)
        )
        st.markdown(
            f'<div class="detail-section">'
            f'<p class="detail-section-title">Credit Scores</p>{rows}</div>',
            unsafe_allow_html=True,
        )

    # ── Review reasons ─────────────────────────────────────────────────────────
    if reasons:
        st.markdown(
            '<div class="detail-section">'
            '<p class="detail-section-title">Review / Decline Reasons</p>'
            + "".join(f'<div style="padding:5px 0;font-size:0.87rem;color:#555;">• {r}</div>' for r in reasons)
            + "</div>",
            unsafe_allow_html=True,
        )

    # ── Notes ──────────────────────────────────────────────────────────────────
    if notes:
        st.markdown(
            f'<div class="detail-section">'
            f'<p class="detail-section-title">Notes</p>'
            f'<p style="font-size:0.88rem;color:#444;margin:0;">{notes}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Action row ─────────────────────────────────────────────────────────────
    _, edit_col = st.columns([4, 1])
    if edit_col.button("✏️ Edit Application", key="detail_edit_btn", use_container_width=True):
        st.session_state.page_view = "edit_application"
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────

LOAN_TYPES = [
    "Structured Annuity",
    "Term Loan",
    "Revolving Credit",
    "Mortgage",
    "Equipment Finance",
    "Invoice Discounting",
    "Other",
]
DECISION_OPTIONS = ["APPROVED", "PENDING", "REJECTED"]


def _render_app_edit() -> None:
    """Editable form for an existing application record."""
    app_id = st.session_state.get("dash_selected_id", "")
    records = load_all()
    rec = next((r for r in records if r.get("id") == app_id), None)

    # Back button
    st.markdown('<div class="back-btn-row">', unsafe_allow_html=True)
    back_c, _ = st.columns([1, 5])
    if back_c.button("← Back", key="edit_back"):
        st.session_state.page_view = "view_application"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    if not rec:
        st.error(f"Application {app_id} not found.")
        return

    name = rec.get("entity_name") or "Unknown"
    st.markdown(
        f'<div class="detail-header-card">'
        f'<p class="detail-meta">EDIT APPLICATION · {app_id}</p>'
        f'<h2 class="detail-title">{name}</h2>'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.form("edit_app_form"):
        st.markdown('<div class="edit-form-card">', unsafe_allow_html=True)

        col_l, col_r = st.columns(2)

        with col_l:
            current_lt  = rec.get("loan_type") or LOAN_TYPES[0]
            lt_idx      = LOAN_TYPES.index(current_lt) if current_lt in LOAN_TYPES else 0
            new_loan_t  = st.selectbox("Loan Type", LOAN_TYPES, index=lt_idx, key="ef_loan_type")

            new_amount  = st.number_input(
                "Requested Amount (ZAR)",
                min_value=0.0,
                value=float(rec.get("requested_zar") or 0),
                step=10_000.0,
                format="%.0f",
                key="ef_amount",
            )

        with col_r:
            cur_dec     = rec.get("decision") or "PENDING"
            dec_idx     = DECISION_OPTIONS.index(cur_dec) if cur_dec in DECISION_OPTIONS else 1
            new_dec     = st.selectbox("Decision Override", DECISION_OPTIONS, index=dec_idx, key="ef_decision")

            new_status  = st.selectbox(
                "Status",
                ["IN_PROGRESS", "DECIDED"],
                index=0 if rec.get("status") == "IN_PROGRESS" else 1,
                key="ef_status",
            )

        new_notes = st.text_area(
            "Notes / Underwriter Comments",
            value=rec.get("notes") or "",
            height=120,
            placeholder="Add any manual underwriter observations here…",
            key="ef_notes",
        )

        st.markdown('</div>', unsafe_allow_html=True)

        save_c, cancel_c, _ = st.columns([1, 1, 4])
        submitted = save_c.form_submit_button("💾 Save Changes", use_container_width=True, type="primary")
        cancelled = cancel_c.form_submit_button("✕ Cancel", use_container_width=True)

    if submitted:
        update_application(app_id, {
            "loan_type":     new_loan_t,
            "requested_zar": float(new_amount),
            "decision":      new_dec,
            "status":        new_status,
            "notes":         new_notes,
        })
        st.success("Changes saved successfully.")
        st.session_state.page_view = "view_application"
        st.rerun()

    if cancelled:
        st.session_state.page_view = "view_application"
        st.rerun()


# ── Loan Applications Dashboard ───────────────────────────────────────────────

def _render_loan_dashboard() -> None:
    records = load_all()
    summary = get_summary(records)

    # ── Header row ────────────────────────────────────────────────────────────
    hcol, bcol = st.columns([3, 1])
    with hcol:
        st.markdown('<div class="page-crumb">OPERATIONS · UNDERWRITING DESK</div>', unsafe_allow_html=True)
        st.markdown('<div class="page-h1">Loan Applications</div>', unsafe_allow_html=True)
        st.markdown('<div class="page-sub">South African business lending · DSCR, EBITDA and bureau-driven decisions.</div>', unsafe_allow_html=True)
    with bcol:
        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
        if st.button("＋  New Application", type="primary", use_container_width=True):
            st.session_state.page_view = "new_application"
            st.session_state.result    = None
            if "app_id_val" in st.session_state:
                del st.session_state["app_id_val"]
            st.rerun()

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # ── Stat cards ────────────────────────────────────────────────────────────
    STAT_DEFS = [
        ("total",       "TOTAL",        "#f0f4f0", "🗒️"),
        ("approved",    "APPROVED",     "#e8f5e8", "✅"),
        ("declined",    "REJECTED",     "#fce8e8", "❌"),
        ("in_progress", "PENDING",      "#fff8e6", "⏳"),
    ]
    cols = st.columns(4)
    for col, (key, label, bg, icon) in zip(cols, STAT_DEFS):
        val = summary.get(key, 0)
        col.markdown(
            f"""
            <div class="stat-card">
              <div class="stat-icon-wrap" style="background:{bg};">{icon}</div>
              <div>
                <div class="stat-label">{label}</div>
                <div class="stat-value">{val}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)

    # ── Applications table ────────────────────────────────────────────────────
    table_header, count_col = st.columns([3, 1])
    with table_header:
        st.markdown("**All Applications**")
    with count_col:
        st.markdown(f"<div style='text-align:right;color:#888;font-size:0.82rem;padding-top:4px;'>{summary['total']} total</div>", unsafe_allow_html=True)

    if not records:
        st.info("No applications yet. Click **＋ New Application** to process your first document.")
        return

    # ── Native Streamlit table (supports interactive buttons per row) ──────────
    COL_W = [2.5, 1.6, 1.3, 1.0, 0.9, 1.2, 1.3, 1.6]
    HEADERS = ["APPLICANT", "LOAN TYPE", "REQUESTED", "ML SCORE", "BUREAU", "STATUS", "DECISION", "ACTIONS"]
    hdr_cols = st.columns(COL_W)
    for col, h in zip(hdr_cols, HEADERS):
        col.markdown(f'<div class="tbl-hdr">{h}</div>', unsafe_allow_html=True)

    st.markdown('<hr class="tbl-divider">', unsafe_allow_html=True)

    for r in records:
        name     = r.get("entity_name") or "Unknown"
        app_id   = r.get("id") or "—"
        loan_t   = r.get("loan_type") or "—"
        req      = r.get("requested_zar") or 0
        ml       = r.get("ml_score")
        bureau   = r.get("bureau_score")
        status   = r.get("status") or "DECIDED"
        decision = r.get("decision") or "—"

        req_str    = f"R {req:,.0f}" if req else "—"
        ml_str     = f"{ml:.2f}" if ml is not None else "—"
        bureau_str = f"{int(bureau)}" if bureau else "—"

        row_cols = st.columns(COL_W)
        row_cols[0].markdown(
            f'<div class="tbl-name">{name}</div><div class="tbl-sub">{app_id[:18]}</div>',
            unsafe_allow_html=True,
        )
        row_cols[1].markdown(f'<div class="tbl-cell">{loan_t}</div>', unsafe_allow_html=True)
        row_cols[2].markdown(f'<div class="tbl-cell-bold">{req_str}</div>', unsafe_allow_html=True)
        row_cols[3].markdown(f'<div class="tbl-cell-bold">{ml_str}</div>', unsafe_allow_html=True)
        row_cols[4].markdown(f'<div class="tbl-cell">{bureau_str}</div>', unsafe_allow_html=True)
        row_cols[5].markdown(_status_badge(status), unsafe_allow_html=True)
        row_cols[6].markdown(_decision_badge(decision), unsafe_allow_html=True)

        with row_cols[7]:
            btn_a, btn_b = st.columns(2)
            with btn_a:
                st.markdown('<div class="btn-view">', unsafe_allow_html=True)
                if st.button("👁 View", key=f"view_{app_id}", use_container_width=True):
                    st.session_state.dash_selected_id = app_id
                    st.session_state.page_view = "view_application"
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            with btn_b:
                st.markdown('<div class="btn-edit">', unsafe_allow_html=True)
                if st.button("✏️ Edit", key=f"edit_{app_id}", use_container_width=True):
                    st.session_state.dash_selected_id = app_id
                    st.session_state.page_view = "edit_application"
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<hr class="tbl-row-sep">', unsafe_allow_html=True)

    # ── Optional: delete / manage row ─────────────────────────────────────────
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    with st.expander("🗑️  Remove an application", expanded=False):
        ids = [r.get("id", "") for r in records]
        to_del = st.selectbox("Select Application ID to remove", ids, key="del_select")
        if st.button("Delete", key="del_btn", type="secondary"):
            delete_application(to_del)
            st.success(f"Deleted {to_del}")
            st.rerun()


# ── Main ─────────────────────────────────────────────────────────────────────

def _render_new_application(sidebar: dict) -> None:  # noqa: ARG001
    """5-step wizard controller."""
    if "wiz_step"        not in st.session_state: st.session_state.wiz_step        = 1
    if "wiz_app_id"      not in st.session_state: st.session_state.wiz_app_id      = f"APP-{uuid.uuid4().hex[:8].upper()}"
    if "wiz_entity_name" not in st.session_state: st.session_state.wiz_entity_name = "New Application"

    step = st.session_state.wiz_step
    if   step == 1: _wiz_step_upload()
    elif step == 2: _wiz_step_extract()
    elif step == 3: _wiz_step_apply()
    elif step == 4: _wiz_step_decision()
    elif step == 5: _wiz_step_schedule()


def _render_new_application_legacy(sidebar: dict) -> None:
    """Legacy pipeline form + result tabs (kept for reference)."""
    if "result" not in st.session_state:
        st.session_state.result = None

    st.markdown('<div class="page-crumb">OPERATIONS · UNDERWRITING DESK</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-h1">New Application</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:0.88rem;color:#666;margin-bottom:1rem;">Upload a bank statement or financial document. '
        'Pipeline: OCR → LLM extraction → DSCR/DTI → AI credit score → decision → policy.</div>',
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "Upload documents",
        type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "txt", "csv"],
        accept_multiple_files=True,
    )

    paths: list[str] = []
    if uploaded:
        for f in uploaded:
            suffix = Path(f.name).suffix or ".bin"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(f.getvalue())
            tmp.close()
            paths.append(tmp.name)

    col_run, col_clear, col_back = st.columns([3, 1, 1])
    with col_run:
        run_btn = st.button("🚀 Run underwriting pipeline", type="primary", disabled=not paths, use_container_width=True)
    with col_clear:
        if st.button("🗑 Clear", use_container_width=True):
            st.session_state.result = None
    with col_back:
        if st.button("← Back", use_container_width=True):
            st.session_state.page_view = "dashboard"
            st.session_state.result    = None
            st.rerun()

    if not paths and not st.session_state.result:
        st.info("👆 Upload a bank statement or financial document PDF, then click **Run underwriting pipeline**.")
        return

    if run_btn and paths:
        hints_raw  = sidebar["hints_raw"]
        hints_list = [h.strip() for h in hints_raw.split(",") if h.strip()] or ["bank_statement"]
        while len(hints_list) < len(paths):
            hints_list.append(hints_list[-1])

        initial = {
            "application_id": sidebar["app_id"],
            "applicant_submission": {
                "date_of_birth": sidebar["dob"],
                "proposed_annuity_premium_zar": sidebar["premium"],
            },
            "uploaded_file_paths": paths,
            "category_hints": hints_list[: len(paths)],
            "errors": [],
        }

        with st.spinner("Running: OCR → LLM extraction → Delinquency → OpenAI credit score → Decision → Policy…"):
            try:
                result = run_application(initial)
                st.session_state.result = result
                # Persist to applications store
                try:
                    save_application(result, loan_type=sidebar.get("loan_type") or "Structured Annuity")
                except Exception as se:
                    st.warning(f"Could not save to applications store: {se}")
            except Exception as e:
                st.error(f"Pipeline error: {e}")
                st.info("Check `OPENAI_API_KEY` or `OPEN_API` in `env.local`.")
                return

    result = st.session_state.result
    if not result:
        return

    # Decision banner
    decision = (result.get("decision") or "").upper()
    if decision == "STP":
        st.markdown('<div class="stp-banner">✅ STRAIGHT-THROUGH APPROVED — Auto-booked</div>', unsafe_allow_html=True)
    elif decision == "CONDITIONAL_APPROVAL":
        st.markdown('<div class="conditional-banner">◑ CONDITIONALLY APPROVED — Subject to conditions</div>', unsafe_allow_html=True)
    elif decision == "DECLINED":
        st.markdown('<div class="declined-banner">🚫 DECLINED — Pre-screen failed</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="review-banner">⚠️ MANUAL REVIEW REQUIRED</div>', unsafe_allow_html=True)

    st.divider()
    _kpi_row(result)
    st.divider()

    tab_pol, tab_cust, tab_txn, tab_ai, tab_cf, tab_chk, tab_ocr = st.tabs([
        "📄 Policy", "👤 Customer Profile", "💳 Transactions & Eligibility",
        "🤖 AI Credit Score", "📊 Cashflow", "✅ Rule Checks", "🔍 OCR text",
    ])

    with tab_pol:
        _tab_policy(result, sidebar)
    with tab_cust:
        _tab_customer(result, sidebar)
    with tab_txn:
        _tab_transactions(result)
    with tab_ai:
        _tab_ai_score(result)
    with tab_cf:
        _tab_cashflow(result)
    with tab_chk:
        _tab_checks(result)
    with tab_ocr:
        _tab_ocr(result)

    errs = result.get("errors") or []
    if errs:
        with st.expander("⚠️ Pipeline warnings", expanded=False):
            for e in errs:
                st.warning(str(e))

    st.divider()
    st.caption(f"SA Underwriting Agent · CREDIT_USE_MOCK={os.environ.get('CREDIT_USE_MOCK', 'true')}")

    # Offer to go back to dashboard after save
    if st.button("📋 Back to Applications Dashboard", use_container_width=True):
        st.session_state.page_view = "dashboard"
        st.session_state.result    = None
        st.rerun()


def main() -> None:
    # Initialise session state
    if "page_view" not in st.session_state:
        st.session_state.page_view = "dashboard"
    if "result" not in st.session_state:
        st.session_state.result = None

    view   = st.session_state.page_view
    sidebar = _sidebar(view)

    if view == "dashboard":
        _render_loan_dashboard()
    elif view == "view_application":
        _render_app_detail()
    elif view == "edit_application":
        _render_app_edit()
    else:
        _render_new_application(sidebar)


if __name__ == "__main__":
    main()
