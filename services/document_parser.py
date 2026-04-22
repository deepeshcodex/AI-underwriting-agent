"""
Generic LLM-powered financial document parser.

Accepts ANY financial document text (bank statement, income statement,
balance sheet, management accounts, payslip) and returns a rich structured
JSON including:
  - entity / customer details
  - ALL transactions (bank statement) or P&L lines (financial statement)
  - monthly cashflow summaries
  - derived underwriting metrics: NOI, DSCR, DTI, loan eligibility
  - delinquency events

This replaces the fragile regex CSV parser — a single LLM call handles any
document format.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_openai import ChatOpenAI

from services.config_loader import load_prompts
from services.logger import get_logger
from services.settings import settings

log = get_logger(__name__)

_FALLBACK_EMPTY: dict[str, Any] = {
    "document_type": "unknown",
    "entity_name": None,
    "account_number_masked": None,
    "statement_period_start": None,
    "statement_period_end": None,
    "months_covered": 0,
    "transactions": [],
    "monthly_summaries": [],
    "summary": {},
    "derived": {},
    "delinquency_events": [],
    "parse_error": None,
}


def _safe_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip()).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    return json.loads(text)


def parse_financial_document(
    ocr_text: str,
    *,
    category_hint: str = "unknown",
    underwriting_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Main entry point — parse any financial document via OpenAI.

    Args:
        ocr_text:              Raw text from OCR / PDF extraction.
        category_hint:         Hint passed by user (bank_statement, income_proof, etc.)
        underwriting_context:  Optional dict with {age, premium_zar, score_min, dscr_min, dti_max}

    Returns:
        Structured dict with transactions, summaries, derived DSCR/DTI, eligibility.
    """
    prompts = load_prompts()
    dp_sys  = prompts.get("document_parser_system", "")
    dp_user = prompts.get("document_parser_user", "")

    if not dp_sys or not dp_user or not ocr_text.strip():
        return {**_FALLBACK_EMPTY, "parse_error": "No parser prompt or empty text."}

    ctx = underwriting_context or {}
    # Use direct message construction (not ChatPromptTemplate) because the
    # prompt contains JSON examples with curly braces that confuse f-string parsing.
    user_rendered = (
        dp_user
        .replace("{ocr_text}",    ocr_text[:60000])
        .replace("{category_hint}", str(category_hint))
        .replace("{dscr_min}",    str(ctx.get("dscr_min", 1.25)))
        .replace("{dti_max}",     str(ctx.get("dti_max", 0.4)))
        .replace("{score_min}",   str(ctx.get("score_min", 650)))
        .replace("{premium_zar}", str(ctx.get("premium_zar", 0)))
    )

    from langchain_core.messages import HumanMessage, SystemMessage
    llm = ChatOpenAI(
        api_key=settings.resolved_openai_key(),
        model=settings.extraction_model or prompts.get("model", {}).get("default_model", "gpt-4o-mini"),
        temperature=0,
    )

    try:
        msg = llm.invoke([SystemMessage(content=dp_sys), HumanMessage(content=user_rendered)])
        raw = msg.content if hasattr(msg, "content") else str(msg)
        result = _safe_json(raw)
        result["parse_error"] = None
        result = _post_process(result, ocr_text)
        return result
    except Exception as e:
        log.info("document_parser_failed", extra={"error": str(e)})
        return {**_FALLBACK_EMPTY, "parse_error": str(e)}


def _post_process(result: dict[str, Any], ocr_text: str) -> dict[str, Any]:
    """
    Apply deterministic fixes that the LLM sometimes misses:
    - months_covered inference for financial statements
    - entity_name fallback from document title
    """
    doc_type = (result.get("document_type") or "").lower()

    # ── months_covered inference ─────────────────────────────────────────────
    if not result.get("months_covered"):
        text_lc = ocr_text.lower()
        mc: int
        if "annual" in text_lc or "year ended" in text_lc or "full year" in text_lc \
                or "annualised" in text_lc or "afs" in text_lc:
            mc = 12
        elif "half year" in text_lc or "six month" in text_lc or "6 month" in text_lc:
            mc = 6
        elif "quarter" in text_lc or "3 month" in text_lc or "three month" in text_lc:
            mc = 3
        elif doc_type in ("income_statement", "balance_sheet",
                          "management_accounts", "multi_period_accounts"):
            mc = 12   # default for financial statements
        else:
            # Bank statement: count distinct month keys in monthly_summaries or transactions
            months_set: set[str] = set()
            for m in result.get("monthly_summaries") or []:
                mo = str(m.get("month", ""))[:7]
                if mo:
                    months_set.add(mo)
            for t in result.get("transactions") or []:
                d = str(t.get("date", ""))[:7]
                if d:
                    months_set.add(d)
            mc = len(months_set) if months_set else 1
        result["months_covered"] = mc

    # ── entity_name fallback ─────────────────────────────────────────────────
    if not result.get("entity_name"):
        # Try first non-blank line of the document as document title
        for line in ocr_text.splitlines():
            stripped = line.strip()
            if stripped and len(stripped) > 2:
                result["entity_name"] = stripped[:80]
                break

    return result


_FINANCIAL_DOC_TYPES = {"income_statement", "balance_sheet", "management_accounts",
                        "multi_period_accounts"}
_BANK_DOC_TYPES      = {"bank_statement"}


def merge_parsed_documents(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Merge multiple parsed financial documents (bank statements + financial
    statements) into a single enriched record.

    Priority rules:
    • entity_name / currency       — first non-null across all docs
    • revenue / EBITDA / ratios    — financial statement wins over bank statement
    • transactions / monthly_sums  — union of all bank statement transactions
    • months_covered               — sum of unique bank-stmt months; annual stmts = 12
    • delinquency_events           — union of all events (de-duplicated)
    • derived fields               — financial stmt values take priority; bank stmt fills gaps
    """
    if not docs:
        return {**_FALLBACK_EMPTY}
    if len(docs) == 1:
        return docs[0]

    fin_docs  = [d for d in docs if (d.get("document_type") or "") in _FINANCIAL_DOC_TYPES]
    bank_docs = [d for d in docs if (d.get("document_type") or "") in _BANK_DOC_TYPES]
    other     = [d for d in docs if d not in fin_docs and d not in bank_docs]

    # Priority order for scalar fields: financial > bank > other
    priority = fin_docs + bank_docs + other

    def _first(*keys: str) -> Any:
        for doc in priority:
            for k in keys:
                v = doc.get(k)
                if v is not None and v != "" and v != [] and v != {}:
                    return v
        return None

    def _merge_derived() -> dict[str, Any]:
        merged: dict[str, Any] = {}
        # Collect all keys across all derived dicts
        all_keys: set[str] = set()
        for doc in docs:
            all_keys.update((doc.get("derived") or {}).keys())
        # Financial statement values take priority
        for k in all_keys:
            for doc in priority:
                v = (doc.get("derived") or {}).get(k)
                if v is not None:
                    merged[k] = v
                    break
        return merged

    # Union all bank-statement transactions (de-dup by date+description)
    seen_txns: set[str] = set()
    all_txns: list[dict] = []
    for doc in bank_docs:
        for t in (doc.get("transactions") or []):
            key = f"{t.get('date','')}|{t.get('description','')}"
            if key not in seen_txns:
                seen_txns.add(key)
                all_txns.append(t)

    # Union monthly summaries (de-dup by month)
    seen_months: set[str] = set()
    all_summaries: list[dict] = []
    for doc in bank_docs:
        for m in (doc.get("monthly_summaries") or []):
            mkey = str(m.get("month", ""))
            if mkey and mkey not in seen_months:
                seen_months.add(mkey)
                all_summaries.append(m)
    all_summaries.sort(key=lambda x: str(x.get("month", "")))

    # Union delinquency events (de-dup by date+description)
    seen_delinq: set[str] = set()
    all_delinq: list[dict] = []
    for doc in docs:
        for e in (doc.get("delinquency_events") or []):
            dkey = f"{e.get('date','')}|{e.get('description','')}"
            if dkey not in seen_delinq:
                seen_delinq.add(dkey)
                all_delinq.append(e)

    # Months covered: sum unique bank-stmt months; financial stmts add 12
    bank_months = len(seen_months) if seen_months else sum(
        int(d.get("months_covered") or 0) for d in bank_docs
    )
    fin_months  = 12 if fin_docs else 0
    months_covered = bank_months or fin_months or _first("months_covered")

    # Stated ratios: prefer financial statement
    stated = _first("stated_ratios") or {}

    result: dict[str, Any] = {
        "document_type":         "multi_document" if len(docs) > 1 else _first("document_type"),
        "source_documents":      [{"type": d.get("document_type"), "entity": d.get("entity_name")} for d in docs],
        "entity_name":           _first("entity_name", "account_holder_name"),
        "account_holder_name":   _first("account_holder_name"),
        "account_number_masked": _first("account_number_masked"),
        "bank_name":             _first("bank_name"),
        "account_type":          _first("account_type"),
        "currency":              _first("currency") or "ZAR",
        "statement_period_start":_first("statement_period_start"),
        "statement_period_end":  _first("statement_period_end"),
        "months_covered":        months_covered,
        "transactions":          all_txns,
        "monthly_summaries":     all_summaries,
        "delinquency_events":    all_delinq,
        "stated_ratios":         stated,
        "derived":               _merge_derived(),
        # Financial statement top-level fields
        "revenue_zar":                _first("revenue_zar"),
        "cost_of_goods_sold_zar":     _first("cost_of_goods_sold_zar"),
        "gross_profit_zar":           _first("gross_profit_zar"),
        "ebitda_computed_zar":        _first("ebitda_computed_zar", "ebitda_zar"),
        "operating_expenses_zar":     _first("operating_expenses_zar"),
        "net_income_zar":             _first("net_income_zar"),
        "total_assets_zar":           _first("total_assets_zar"),
        "current_assets_zar":         _first("current_assets_zar"),
        "current_liabilities_zar":    _first("current_liabilities_zar"),
        "total_equity_zar":           _first("total_equity_zar"),
        "total_debt_zar":             _first("total_debt_zar"),
        "annual_debt_service_zar":    _first("annual_debt_service_zar"),
        "parse_error":           None,
        "loan_eligibility":      _first("loan_eligibility"),
        "summary":               _first("summary") or {},
    }
    return result


def parsed_doc_to_dataframe(parsed: dict[str, Any]):
    """Convert transactions list to a Pandas DataFrame with canonical columns."""
    import pandas as pd

    txns = parsed.get("transactions") or []
    if not txns:
        return None
    rows = []
    for t in txns:
        if not isinstance(t, dict):
            continue
        rows.append({
            "date":        t.get("date") or t.get("txn_date") or "",
            "description": t.get("description") or t.get("desc") or "",
            "debit":       float(t.get("debit_zar") or t.get("debit") or 0),
            "credit":      float(t.get("credit_zar") or t.get("credit") or 0),
            "balance":     float(t.get("balance_zar") or t.get("balance") or 0),
        })
    if not rows:
        return None
    return pd.DataFrame(rows)
