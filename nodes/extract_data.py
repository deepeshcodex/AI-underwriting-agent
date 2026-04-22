"""
LLM extraction — three passes:

  Pass 0 (NEW): Generic document parser — calls OpenAI once with the full
                document text and returns: entity details, ALL transactions
                (or P&L lines for financial statements), monthly summaries,
                derived DSCR/DTI, delinquency events, loan eligibility.
                Result stored in state['parsed_document'].

  Pass 1: Standard field extraction per document (original behaviour).
          Enriched with Pass 0 results.

  Pass 2: Deep bank-statement profile (bank_statement_system prompt).
          Stored in state['bank_profile'].

The Pass 0 result is the authoritative source for DSCR, DTI, income, and
loan eligibility. Passes 1 & 2 fill remaining persona/contact fields.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from services.config_loader import load_prompts, load_underwriting
from services.document_parser import parse_financial_document
from services.logger import get_logger
from services.settings import settings
from models.extraction import ExtractedApplicant, merged_dict
from models.graph_state import UnderwritingState

log = get_logger(__name__)


def _safe_json(text: str) -> dict[str, Any]:
    text = text.strip()
    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    text = text.strip()
    # Extract first JSON object
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    return json.loads(text)


def _llm(prompts: dict[str, Any]) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.resolved_openai_key(),
        model=settings.extraction_model or prompts.get("model", {}).get("default_model", "gpt-4o-mini"),
        temperature=float(prompts.get("model", {}).get("temperature", 0)),
    )


# ── Pass 0: generic document parser ──────────────────────────────────────────

def _pass0_parse(segments: list[dict], uw_cfg: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Combine ALL document text and run the generic LLM parser once."""
    combined_text_parts = []
    hints_used = set()
    for seg in segments:
        text = seg.get("ocr_text") or ""
        if not text.strip():
            continue
        hint = seg.get("category_hint", "unknown")
        combined_text_parts.append(f"[DOCUMENT: {hint.upper()}]\n{text}")
        hints_used.add(hint)

    if not combined_text_parts:
        return {}, ["No OCR text available for document parsing."]

    full_text = "\n\n".join(combined_text_parts)
    ratios = uw_cfg.get("ratios", {})
    credit = uw_cfg.get("credit", {})
    context = {
        "dscr_min":   float(ratios.get("dscr_min", 1.25)),
        "dti_max":    float(ratios.get("dti_max", 0.4)),
        "score_min":  float(credit.get("score_min", 650)),
        "premium_zar": 0,
    }

    primary_hint = next(iter(hints_used), "unknown")
    parsed = parse_financial_document(full_text, category_hint=primary_hint, underwriting_context=context)

    if parsed.get("parse_error"):
        return parsed, [f"Document parser warning: {parsed['parse_error']}"]
    return parsed, []


# ── Pass 1: standard field extraction ────────────────────────────────────────

def _pass1_extract(segments: list[dict], prompts: dict, llm: ChatOpenAI, bundle_id: str) -> tuple[list[dict], list[str]]:
    field_spec = prompts.get("json_field_spec_extraction", "").strip()
    sys_msg  = prompts.get("system", "")
    user_tpl = prompts.get("user_template", "")
    chain = ChatPromptTemplate.from_messages([("system", sys_msg), ("human", user_tpl)]) | llm

    records: list[dict] = []
    errors:  list[str]  = []
    for seg in segments:
        text = seg.get("ocr_text") or ""
        if not text.strip():
            errors.append(f"Empty OCR for {seg.get('path')}")
            continue
        try:
            msg  = chain.invoke({"bundle_id": bundle_id, "category_hint": seg.get("category_hint", "unknown"), "ocr_text": text[:48000], "field_spec": field_spec})
            raw  = msg.content if hasattr(msg, "content") else str(msg)
            data = _safe_json(raw)
            ExtractedApplicant.model_validate(data)
            records.append(data)
        except Exception as e:
            errors.append(f"Pass-1 extract failed for {seg.get('path')}: {e}")
    return records, errors


# ── Pass 2: deep bank-statement profile ──────────────────────────────────────

def _pass2_bank_profile(segments: list[dict], prompts: dict, llm: ChatOpenAI) -> tuple[dict[str, Any], list[str]]:
    bs_sys  = prompts.get("bank_statement_system", "")
    bs_user = prompts.get("bank_statement_user", "")
    if not bs_sys or not bs_user:
        return {}, []

    texts = [f"[{s.get('category_hint','').upper()}]\n{s.get('ocr_text','')}"
             for s in segments if (s.get("ocr_text") or "").strip()
             and s.get("category_hint", "") in ("bank_statement", "unknown", "income_proof")]

    if not texts:
        return {}, []

    # Use direct message construction — the prompt contains JSON examples with curly
    # braces (e.g. {description, amount_zar, frequency}) that confuse ChatPromptTemplate.
    from langchain_core.messages import HumanMessage, SystemMessage
    user_rendered = bs_user.replace("{ocr_text}", "\n\n".join(texts)[:60000])
    try:
        msg = llm.invoke([SystemMessage(content=bs_sys), HumanMessage(content=user_rendered)])
        raw = msg.content if hasattr(msg, "content") else str(msg)
        return _safe_json(raw), []
    except Exception as e:
        return {}, [f"Deep bank-statement profile extraction failed: {e}"]


# ── Enrich merged_applicant from parsed_document ─────────────────────────────

def _enrich_from_parsed(merged: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    """Copy key financial fields from parsed_document → merged_applicant if missing."""
    derived = parsed.get("derived") or {}

    field_map = {
        "applicant_full_name":          ["entity_name", "account_holder_name"],
        "employer_name":                ["employer_name"],
        "gross_monthly_income":         ["gross_monthly_income_zar", "avg_monthly_income_zar"],
        "monthly_debt_payments":        ["total_monthly_debt_zar", "loan_repayment_monthly_zar"],
        "noi":                          ["noi_annual_zar"],
        "debt_service":                 ["annual_debt_service_zar"],
        "account_last4":                ["account_number_masked"],
    }
    for target, sources in field_map.items():
        if merged.get(target) is not None:
            continue
        for src in sources:
            v = parsed.get(src) or derived.get(src)
            if v is not None:
                merged[target] = v
                break
    return merged


# ── LangGraph node entry point ────────────────────────────────────────────────

def run(state: UnderwritingState) -> dict[str, Any]:
    prompts  = load_prompts()
    uw_cfg   = load_underwriting()
    segments = state.get("ocr_segments") or []
    bundle_id = state.get("application_id", "unknown")
    errors: list[str] = []

    # Inject premium into underwriting context
    sub = state.get("applicant_submission") or {}
    uw_cfg.setdefault("ratios", {})
    uw_cfg.setdefault("credit", {})
    uw_ctx = {
        "dscr_min":   float(uw_cfg.get("ratios", {}).get("dscr_min", 1.25)),
        "dti_max":    float(uw_cfg.get("ratios", {}).get("dti_max", 0.4)),
        "score_min":  float(uw_cfg.get("credit", {}).get("score_min", 650)),
        "premium_zar": sub.get("proposed_annuity_premium_zar", 0),
    }

    # Pass 0 — generic document parse (skip if wizard already computed it)
    pre = state.get("parsed_document") or {}
    if pre and not pre.get("parse_error") and pre.get("derived"):
        log.info("extract_data_skip_pass0_cached")
        parsed_doc, errs0 = pre, []
    else:
        parsed_doc, errs0 = _pass0_parse(segments, uw_cfg)
    if errs0:
        errors.extend(errs0)

    llm = _llm(prompts)

    # Pass 1 — standard field extraction
    records, errs1 = _pass1_extract(segments, prompts, llm, bundle_id)
    errors.extend(errs1)

    # Merge pass-1 + form submission
    merged: dict[str, Any] = merged_dict(*records) if records else {}
    if sub:
        merged = merged_dict(sub, merged)

    # Multi-doc aggregation
    if len(records) > 1:
        agg_sys = prompts.get("aggregation_system", "")
        agg_tpl = prompts.get("aggregation_user_template", "")
        if agg_sys and agg_tpl:
            try:
                chain2 = ChatPromptTemplate.from_messages([("system", agg_sys), ("human", agg_tpl)]) | llm
                msg2   = chain2.invoke({"records_json": json.dumps(records, default=str)[:48000]})
                raw2   = msg2.content if hasattr(msg2, "content") else str(msg2)
                merged = merged_dict(merged, _safe_json(raw2))
            except Exception as e:
                errors.append(f"Aggregation LLM skipped: {e}")

    # Pass 2 — deep bank profile
    bank_profile, errs2 = _pass2_bank_profile(segments, prompts, llm)
    errors.extend(errs2)

    # Enrich merged from parsed_document (authoritative for financial metrics)
    merged = _enrich_from_parsed(merged, parsed_doc)

    # Also enrich from bank_profile if pass-2 ran
    if bank_profile:
        p2_map = {
            "applicant_full_name": "account_holder_name",
            "employer_name": "employer_name",
            "gross_monthly_income": "salary_income_monthly_avg",
            "monthly_debt_payments": "debt_obligations_total_monthly",
        }
        for mk, pk in p2_map.items():
            if merged.get(mk) is None and bank_profile.get(pk) is not None:
                merged[mk] = bank_profile[pk]

    out: dict[str, Any] = {
        "extracted_records": records,
        "merged_applicant":  merged,
        "bank_profile":      bank_profile,
        "parsed_document":   parsed_doc,
        "stage":             "extract_data",
    }
    if errors:
        out["errors"] = errors
    return out
