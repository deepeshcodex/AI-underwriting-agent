"""Streamlit — upload documents and view extracted underwriting details."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

# Project root (parent of `ui/`) — fixes `ModuleNotFoundError: No module named 'app'`
# when Streamlit is started from `ui/` instead of the repo root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

from app import run_application


st.set_page_config(page_title="SA Underwriting", layout="wide", initial_sidebar_state="expanded")


def _decision_style(decision: str | None) -> tuple[str, str]:
    d = (decision or "").upper()
    if d == "STP":
        return "Straight-through", "🟢"
    if d == "DECLINED":
        return "Declined", "🔴"
    return "Manual review", "🟡"


def _fmt_val(v: object) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return "" if v is None else str(v)


def _show_kv_table(data: dict | None) -> None:
    if not data:
        st.caption("_No data._")
        return
    rows = [{"Field": k, "Value": _fmt_val(v)} for k, v in data.items() if not str(k).startswith("_")]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def main() -> None:
    if "last_result" not in st.session_state:
        st.session_state.last_result = None

    st.title("Structured Annuity underwriting")
    st.markdown(
        "Upload your document(s) below. The system runs **OCR → LLM extraction → DSCR/DTI/ML + credit (mock)** "
        "and shows **extracted details**, **policy checks**, and **raw OCR text**."
    )

    with st.sidebar:
        st.header("Context (optional)")
        app_id = st.text_input("Application ID", value=f"APP-{uuid.uuid4().hex[:8]}")
        dob = st.text_input("Date of birth (YYYY-MM-DD)", value="1980-05-05", help="Used if not found in documents")
        premium = st.number_input("Proposed premium (ZAR)", min_value=0.0, value=120_000.0, step=1_000.0)
        hints_raw = st.text_input(
            "Document categories (comma order, one per file)",
            value="bank_statement",
            help="Ids from config/docs.yaml: e.g. identity, bank_statement, income_proof",
        )
        st.divider()
        st.caption("Needs `OPENAI_API_KEY` or `OPEN_API` in `.env` / `env.local` for extraction.")

    uploaded = st.file_uploader(
        "Upload documents",
        type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "txt", "csv"],
        accept_multiple_files=True,
        help="Bank statement, ID scan, payslip, etc.",
    )

    paths: list[str] = []
    if uploaded:
        for f in uploaded:
            suffix = Path(f.name).suffix or ".bin"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(f.getvalue())
            tmp.close()
            paths.append(tmp.name)

    run = st.button("Run extraction & underwriting", type="primary", disabled=not paths, use_container_width=True)

    if not paths:
        st.info("👆 Upload at least one file to enable the run button.")
    elif not run:
        st.caption(f"**{len(paths)}** file(s) ready — click **Run extraction & underwriting**.")

    if run and paths:
        hints_list = [h.strip() for h in hints_raw.split(",") if h.strip()] or ["bank_statement"]
        while len(hints_list) < len(paths):
            hints_list.append(hints_list[-1])

        initial = {
            "application_id": app_id,
            "applicant_submission": {
                "date_of_birth": dob,
                "proposed_annuity_premium_zar": premium,
            },
            "uploaded_file_paths": paths,
            "category_hints": hints_list[: len(paths)],
            "errors": [],
        }

        with st.spinner("Running: OCR → LLM → risk & policy…"):
            try:
                st.session_state.last_result = run_application(initial)
            except Exception as e:
                st.error(str(e))
                st.info("Set `OPENAI_API_KEY` or `OPEN_API` in `env.local` or `.env`.")
                return

    if st.session_state.last_result:
        if not paths:
            st.caption("Showing **previous** run — upload files and run again to refresh.")
        _render_results(st.session_state.last_result)

    st.divider()
    st.caption(
        f"Working directory: `{os.getcwd()}` · "
        f"CREDIT_USE_MOCK={os.environ.get('CREDIT_USE_MOCK', 'true')}",
    )


def _render_results(result: dict) -> None:
    decision = result.get("decision")
    label, icon = _decision_style(decision)

    st.divider()
    st.subheader("Your results")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Outcome", f"{icon} {decision or '—'}", help=label)
    metrics = result.get("metrics") or {}
    ml_s = metrics.get("ml_score")
    with c2:
        st.metric(
            "ML risk score",
            f"{float(ml_s):.3f}" if ml_s is not None else "—",
            help="Higher = riskier in this template",
        )
    with c3:
        cr = result.get("credit") or {}
        st.metric("Credit score", f"{cr.get('score', '—')} ({cr.get('bureau', '—')})")

    tab_ext, tab_pol, tab_ocr = st.tabs(["Extracted details", "Policy & ratios", "OCR text"])

    merged = result.get("merged_applicant") or {}
    with tab_ext:
        st.markdown("Extracted and merged fields (your sidebar inputs + what the model read from documents)")
        _show_kv_table(merged)
        if not merged:
            st.warning("No fields merged — try a clearer PDF/image or check API key / model access.")

    with tab_pol:
        preview = result.get("policy_preview") or {}
        checks = preview.get("checks") or {}
        if checks:
            st.markdown("**Automated rule checks**")
            for name, body in checks.items():
                ok = body.get("ok")
                icon_ch = "✅" if ok else "❌"
                st.markdown(f"{icon_ch} **{name.replace('_', ' ')}**")
                st.caption(json.dumps(body, indent=2, default=str))
        else:
            st.json(preview)
        st.markdown("**Computed metrics**")
        st.json(metrics)

    with tab_ocr:
        ocr = result.get("ocr_segments") or []
        if not ocr:
            st.caption("No OCR segments returned.")
            return
        for i, seg in enumerate(ocr):
            name = Path(seg.get("path", "")).name
            st.markdown(f"##### {name} · _{seg.get('category_hint', '')}_")
            text = seg.get("ocr_text") or ""
            st.text_area(
                "Extracted text",
                value=text[:15_000],
                height=min(400, max(120, 10 + len(text) // 4)),
                key=f"ocr_{i}_{name}",
                disabled=True,
                label_visibility="collapsed",
            )

    errs = result.get("errors") or []
    if errs:
        with st.expander("Warnings / extraction notes", expanded=True):
            for e in errs:
                st.warning(str(e))


if __name__ == "__main__":
    main()
