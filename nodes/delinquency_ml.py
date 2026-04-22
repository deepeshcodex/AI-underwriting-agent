"""
Delinquency ML node.

Uses the generic parsed_document from extract_data (Pass 0) as primary source.
Falls back to regex OCR parsing only when parsed_document is absent.
"""

from __future__ import annotations

import json
import re
from typing import Any

import numpy as np
import pandas as pd

from services.config_loader import load_prompts, load_validation
from services.document_parser import parsed_doc_to_dataframe
from services.logger import get_logger
from models.graph_state import UnderwritingState

log = get_logger(__name__)


# ── DataFrame fallback helpers (regex — used only without parsed_document) ────

def _parse_amount(s: Any) -> float:
    if pd.isna(s):
        return 0.0
    try:
        return float(re.sub(r"[^\d.\-]", "", str(s).replace(",", "")))
    except ValueError:
        return 0.0


# ── Delinquency detection ─────────────────────────────────────────────────────

def _detect_delinquency(
    df: pd.DataFrame | None,
    ocr_texts: list[str],
    parsed_events: list[dict | str],
    keywords: list[str],
) -> tuple[int, list[str]]:
    """Returns (count, flags). Uses parsed delinquency_events first, then OCR scan."""
    flags: list[str] = []
    count  = 0
    kw_lower = [k.lower() for k in keywords]

    # Primary: structured events from LLM parser
    for ev in parsed_events:
        if isinstance(ev, dict):
            desc = f"{ev.get('date','')} — {ev.get('description','')} (ZAR {ev.get('amount_zar','')})"
        else:
            desc = str(ev)
        flags.append(f"Delinquency event: {desc}")
        count += 1

    # Secondary: DataFrame keyword scan
    if df is not None and "description" in df.columns:
        for val in df["description"].fillna("").astype(str):
            low = val.lower()
            for kw in kw_lower:
                if kw in low and val not in "".join(flags):
                    count += 1
                    flags.append(f"Keyword '{kw}' in: {val[:80]}")
                    break
        if "balance" in df.columns:
            neg = df["balance"].apply(_parse_amount) < 0
            if neg.any():
                count += int(neg.sum())
                flags.append(f"{int(neg.sum())} negative-balance row(s) detected.")

    # Tertiary: raw OCR keyword scan (de-duped)
    seen: set[str] = set()
    for text in ocr_texts:
        for kw in kw_lower:
            if kw in text.lower() and kw not in seen:
                seen.add(kw)
                count += 1
                flags.append(f"Keyword '{kw}' in OCR text.")

    return count, flags


# ── Feature computation ───────────────────────────────────────────────────────

def _features_from_parsed(derived: dict[str, Any], delinq_count: int) -> dict[str, float]:
    return {
        "avg_monthly_balance":     float(derived.get("avg_monthly_balance_zar") or 0),
        "delinquency_count":       float(delinq_count),
        "repayment_consistency":   max(0.0, 1.0 - (delinq_count * 0.2)),
        "cashflow_ratio":          float(derived.get("cashflow_ratio") or 1.0),
    }


def _features_from_df(df: pd.DataFrame | None, delinq_count: int) -> dict[str, float]:
    if df is None or df.empty:
        return {"avg_monthly_balance": 0.0, "delinquency_count": float(delinq_count), "repayment_consistency": 0.0, "cashflow_ratio": 0.0}
    debit_col  = "debit"  if "debit"  in df.columns else None
    credit_col = "credit" if "credit" in df.columns else None
    bal_col    = "balance" if "balance" in df.columns else None
    avg_bal    = float(df[bal_col].apply(_parse_amount).mean()) if bal_col else 0.0
    total_c    = df[credit_col].apply(_parse_amount).sum() if credit_col else 0.0
    total_d    = df[debit_col].apply(_parse_amount).sum()  if debit_col  else 0.0
    cashflow   = float(total_c / max(total_d, 1.0))
    repayment  = max(0.0, 1.0 - (delinq_count / max(len(df), 1)))
    return {"avg_monthly_balance": avg_bal, "delinquency_count": float(delinq_count), "repayment_consistency": repayment, "cashflow_ratio": cashflow}


# ── Cashflow chart ────────────────────────────────────────────────────────────

def _cashflow_from_summaries(monthly_summaries: list[dict]) -> list[dict[str, Any]]:
    rows = []
    for m in (monthly_summaries or []):
        if not isinstance(m, dict):
            continue
        rows.append({
            "period":  m.get("month") or "",
            "credits": float(m.get("total_credits") or 0),
            "debits":  float(m.get("total_debits")  or 0),
            "net":     float(m.get("net_cashflow")   or 0),
        })
    return rows


def _cashflow_from_df(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    if df is None or df.empty or "debit" not in df.columns or "credit" not in df.columns:
        return []
    tmp = df.copy()
    tmp["_d"] = tmp["debit"].apply(_parse_amount)
    tmp["_c"] = tmp["credit"].apply(_parse_amount)
    if "date" in tmp.columns:
        tmp["date"] = pd.to_datetime(tmp["date"], errors="coerce")
        rows = []
        for period, grp in tmp.groupby(pd.Grouper(key="date", freq="ME")):
            rows.append({"period": str(period)[:7], "credits": float(grp["_c"].sum()), "debits": float(grp["_d"].sum()), "net": float(grp["_c"].sum() - grp["_d"].sum())})
        return rows
    return [{"period": "all", "credits": float(tmp["_c"].sum()), "debits": float(tmp["_d"].sum()), "net": float(tmp["_c"].sum() - tmp["_d"].sum())}]


# ── OpenAI credit assessment ──────────────────────────────────────────────────

def _llm_credit_score(
    bank_profile: dict[str, Any],
    parsed_doc: dict[str, Any],
    features: dict[str, float],
    delinq_flags: list[str],
    merged: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI
    from services.settings import settings

    prompts = load_prompts()
    cs_sys  = prompts.get("credit_scoring_system", "")
    cs_user = prompts.get("credit_scoring_user", "")
    if not cs_sys or not cs_user:
        return _heuristic_fallback(features, thresholds)

    derived = parsed_doc.get("derived") or {}
    profile_for_prompt: dict[str, Any] = {
        **{k: v for k, v in {**bank_profile, **derived}.items() if v is not None},
        "delinquency_flags_detected": delinq_flags,
        "ml_features": features,
        "document_type": parsed_doc.get("document_type"),
        "loan_eligibility": parsed_doc.get("loan_eligibility"),
    }

    dob_str = merged.get("date_of_birth") or ""
    age_years: int | str = "unknown"
    if dob_str:
        try:
            from datetime import date
            dob = date.fromisoformat(dob_str[:10])
            td  = date.today()
            age_years = td.year - dob.year - ((td.month, td.day) < (dob.month, dob.day))
        except Exception:
            pass

    llm = ChatOpenAI(
        api_key=settings.resolved_openai_key(),
        model=settings.extraction_model or prompts.get("model", {}).get("default_model", "gpt-4o-mini"),
        temperature=0,
    )
    chain = ChatPromptTemplate.from_messages([("system", cs_sys), ("human", cs_user)]) | llm
    try:
        msg = chain.invoke({
            "profile_json": json.dumps(profile_for_prompt, default=str, ensure_ascii=False)[:14000],
            "age_years":    age_years,
            "premium_zar":  merged.get("proposed_annuity_premium_zar", 0),
            "score_min":    int(thresholds.get("credit_score_min", 650)),
        })
        raw = msg.content if hasattr(msg, "content") else str(msg)
        raw = raw.strip()
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw.strip()).strip()
        m   = re.search(r"\{[\s\S]*\}", raw)
        if m: raw = m.group(0)
        result = json.loads(raw)
        result["source"] = "openai"
        return result
    except Exception as e:
        log.info("llm_credit_score_failed", extra={"error": str(e)})
        fb = _heuristic_fallback(features, thresholds)
        fb["notes"] = f"OpenAI scoring unavailable ({e}); heuristic used."
        return fb


def _heuristic_fallback(features: dict[str, float], thresholds: dict[str, Any]) -> dict[str, Any]:
    score_min = float(thresholds.get("credit_score_min", 650))
    d  = features.get("delinquency_count", 0)
    cf = features.get("cashflow_ratio", 1.0)
    rep= features.get("repayment_consistency", 0.5)
    z  = 2.5 * d - 0.8 * (cf - 1) - 1.5 * rep   # higher z = higher risk
    risk_prob = float(1.0 / (1.0 + np.exp(-np.clip(z, -32, 32))))
    score = max(300.0, min(850.0, 850.0 - risk_prob * 550.0))
    grade = "A" if score >= 750 else ("B" if score >= 700 else ("C" if score >= 650 else ("D" if score >= 600 else ("E" if score >= 550 else "F"))))
    rec   = "APPROVE" if score >= score_min and d == 0 else ("REVIEW" if score >= score_min - 50 else "DECLINE")
    return {
        "credit_score": round(score, 0),
        "credit_grade": grade,
        "recommendation": rec,
        "confidence": "low",
        "positive_factors": ["Heuristic estimate — insufficient data."] if d == 0 else [],
        "risk_factors": [f"{int(d)} delinquency event(s) detected."] if d > 0 else [],
        "affordability_comment": "Unable to assess fully — limited data.",
        "data_quality": "poor",
        "notes": "Heuristic fallback (no OpenAI key or no document data).",
        "source": "heuristic",
    }


# ── LangGraph node entry point ────────────────────────────────────────────────

def run(state: UnderwritingState) -> dict[str, Any]:
    val_cfg       = load_validation()
    keywords      = val_cfg.get("delinq_keywords", [])
    thresholds    = val_cfg.get("thresholds", {})
    delinq_max    = int(thresholds.get("delinq_max", 0))

    parsed_doc    = state.get("parsed_document") or {}
    bank_profile  = state.get("bank_profile")    or {}
    merged        = state.get("merged_applicant") or {}
    segments      = state.get("ocr_segments")    or []
    ocr_texts     = [s.get("ocr_text") or "" for s in segments]

    # Build DataFrame — prefer LLM-parsed transactions
    df = parsed_doc_to_dataframe(parsed_doc) if parsed_doc.get("transactions") else None

    # Delinquency events from LLM (most accurate)
    parsed_events = parsed_doc.get("delinquency_events") or []
    delinq_count, risk_flags = _detect_delinquency(df, ocr_texts, parsed_events, keywords)

    # Features
    derived  = parsed_doc.get("derived") or {}
    features = _features_from_parsed(derived, delinq_count) if derived else _features_from_df(df, delinq_count)

    # Cashflow chart — prefer structured monthly summaries
    monthly  = parsed_doc.get("monthly_summaries") or []
    cashflow_data = _cashflow_from_summaries(monthly) if monthly else _cashflow_from_df(df)

    is_delinquent = delinq_count > delinq_max

    # OpenAI credit assessment
    llm_assessment = _llm_credit_score(bank_profile, parsed_doc, features, risk_flags, merged, thresholds)
    credit_score   = float(llm_assessment.get("credit_score") or 650)

    delinquency_result = {
        "is_delinquent":     is_delinquent,
        "credit_score":      round(credit_score, 1),
        "credit_grade":      llm_assessment.get("credit_grade", "—"),
        "delinquency_count": delinq_count,
        "risk_flags":        risk_flags,
        "ml_features":       features,
        "cashflow_data":     cashflow_data,
        "llm_recommendation": llm_assessment.get("recommendation"),
        "llm_confidence":    llm_assessment.get("confidence"),
    }

    log.info("delinquency_check_done")
    out: dict[str, Any] = {
        "delinquency":          delinquency_result,
        "llm_credit_assessment": llm_assessment,
        "stage":                "delinquency_ml",
    }
    if risk_flags:
        out["errors"] = [f"Delinquency flag: {f}" for f in risk_flags[:5]]
    return out
