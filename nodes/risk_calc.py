"""
Risk ratios node — DSCR and DTI.

Source priority:
  1. parsed_document.derived  (LLM-computed from the uploaded doc — most accurate)
  2. merged_applicant fields   (from standard LLM extraction / form)
  3. bank_profile              (pass-2 bank profile)
  4. delinquency ML features   (last resort estimate)

When data is genuinely unavailable, the field is marked as "not_available"
(informational note for underwriter, NOT a hard block for STP).
"""

from __future__ import annotations

from typing import Any

from services.config_loader import load_underwriting
from services.logger import get_logger
from models.graph_state import UnderwritingState

log = get_logger(__name__)


def _f(d: dict, *keys: str) -> float | None:
    """Return first non-None float from dict using multiple key names."""
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        try:
            fv = float(v)
            if fv > 0:
                return fv
        except (TypeError, ValueError):
            continue
    return None


def run(state: UnderwritingState) -> dict[str, Any]:
    cfg       = load_underwriting()
    ratios_cfg = cfg.get("ratios", {})
    dscr_min  = float(ratios_cfg.get("dscr_min", 1.25))
    dti_max   = float(ratios_cfg.get("dti_max", 0.4))

    parsed    = state.get("parsed_document") or {}
    derived   = parsed.get("derived") or {}
    merged    = dict(state.get("merged_applicant") or {})
    bp        = dict(state.get("bank_profile") or {})
    info_notes: list[str] = []
    hard_errors: list[str] = []

    # ── Extract stated ratios from the document's "Key Financial Ratios" section ─
    # LLM may place stated_ratios at top level OR inside derived — check both.
    stated: dict = (
        parsed.get("stated_ratios")
        or derived.get("stated_ratios")
        or {}
    )

    def _stated(key: str, lo: float = -1e9, hi: float = 1e9) -> float | None:
        """Read a stated ratio with sanity bounds; return None if absent or implausible."""
        v = stated.get(key)
        if v is None:
            return None
        try:
            fv = float(v)
            return fv if lo < fv < hi else None
        except (TypeError, ValueError):
            return None

    stated_dscr   = _stated("dscr",              lo=0.05, hi=20.0)  # e.g. 1.18
    stated_em_pct = _stated("ebitda_margin_pct",  lo=1.0,  hi=95.0) # e.g. 31.5
    stated_dti_pct= _stated("dti_pct",            lo=0.1,  hi=100.0)# e.g. 26.6
    stated_cr     = _stated("current_ratio",       lo=0.1,  hi=50.0) # e.g. 2.4

    # ── Revenue (monthly) ─────────────────────────────────────────────────────
    rev_annual  = _f(parsed, "revenue_zar")
    revenue_monthly = (
        _f(derived, "avg_monthly_income_zar", "gross_monthly_income_zar")
        or (rev_annual / 12 if rev_annual else None)
        or _f(merged, "gross_monthly_income")
        or _f(bp, "total_income_monthly_avg")
    )

    # ── Debt service (monthly) ────────────────────────────────────────────────
    # Prefer the Cash Flow Statement annual figure / 12 — most reliable for fin stmts
    ann_ds_parsed  = _f(parsed, "annual_debt_service_zar")
    ann_ds_derived = _f(derived, "annual_debt_service_zar")
    debt_monthly = (
        _f(derived, "debt_service_monthly_zar", "loan_repayment_monthly_zar")
        or (ann_ds_parsed  / 12 if ann_ds_parsed  else None)
        or (ann_ds_derived / 12 if ann_ds_derived else None)
        or _f(derived, "total_monthly_debt_zar")
        or _f(merged, "monthly_debt_payments")
        or _f(bp, "debt_obligations_total_monthly")
    )

    # ── EBITDA (monthly) — multi-source with validation ───────────────────────
    # PRIORITY 1: stated EBITDA margin × revenue  (most reliable for fin stmts)
    ebitda_monthly: float | None = None
    ebitda_source = "unknown"

    if stated_em_pct and revenue_monthly:
        ebitda_monthly = revenue_monthly * (stated_em_pct / 100.0)
        ebitda_source  = "stated_ebitda_margin"

    # PRIORITY 2: ebitda_computed_zar (LLM computed from P&L components)
    if ebitda_monthly is None:
        ecomp = _f(parsed, "ebitda_computed_zar")
        if ecomp and rev_annual and ecomp < rev_annual:
            ebitda_monthly = ecomp / 12
            ebitda_source  = "ebitda_computed_zar"

    # PRIORITY 3: P&L components from the financial statement
    if ebitda_monthly is None:
        cogs   = _f(parsed, "cost_of_goods_sold_zar")
        opex   = _f(parsed, "operating_expenses_zar")
        if rev_annual and cogs and opex:
            ebitda_monthly = (rev_annual - cogs - opex) / 12
            ebitda_source  = "pl_components_cogs+opex"
        elif rev_annual and opex:
            ebitda_monthly = (rev_annual - opex) / 12
            ebitda_source  = "pl_components_opex_only"

    # PRIORITY 4: opex_monthly_zar from derived (bank statement path)
    if ebitda_monthly is None and revenue_monthly and derived.get("opex_monthly_zar") is not None:
        ebitda_monthly = revenue_monthly - float(derived["opex_monthly_zar"])
        ebitda_source  = "derived_opex"

    # PRIORITY 5: LLM-derived ebitda_monthly_zar — accept only if margin looks plausible
    if ebitda_monthly is None:
        _llm_em = _f(derived, "ebitda_monthly_zar")
        if _llm_em and revenue_monthly:
            llm_margin = _llm_em / revenue_monthly
            if 0.03 < llm_margin < 0.95:   # 3–95% is realistic
                ebitda_monthly = _llm_em
                ebitda_source  = "llm_derived_validated"
            else:
                info_notes.append(
                    f"⚠️  LLM EBITDA {_llm_em:,.0f} gives margin {llm_margin:.1%} — outside 3–95% "
                    "range, likely a malformed number (e.g. '58,56,000'). Recomputing from P&L."
                )

    # ── DSCR resolution (5-priority chain) ───────────────────────────────────
    dscr: float | None = None
    dscr_status: str   = "not_available"

    # P1: document's own "Key Financial Ratios" — most trustworthy
    if stated_dscr is not None:
        dscr = stated_dscr
        dscr_status = "stated_in_document"

    # P2: LLM derived — accept only if plausible (0.3–10 range)
    if dscr is None:
        _d = _f(derived, "dscr")
        if _d and 0.3 < _d < 10.0:
            dscr = _d
            dscr_status = "llm_derived"

    # P3: Python compute — EBITDA_monthly / debt_service_monthly
    if dscr is None and ebitda_monthly and debt_monthly:
        dscr = ebitda_monthly / debt_monthly
        dscr_status = f"computed ({ebitda_source}) / debt_service"

    # P4: if LLM value was suspicious, override with computed when available
    if dscr_status == "llm_derived" and ebitda_monthly and debt_monthly:
        computed = ebitda_monthly / debt_monthly
        # If they disagree significantly and stated is available, prefer stated/computed
        if stated_dscr is not None or abs(computed - dscr) / max(dscr, 0.001) > 0.3:
            dscr = computed if stated_dscr is None else stated_dscr
            dscr_status = "override_computed" if stated_dscr is None else "stated_in_document"

    if dscr is None:
        if ebitda_monthly is None:
            info_notes.append("DSCR unavailable: EBITDA not determinable — verify OPEX split.")
        else:
            info_notes.append("DSCR unavailable: debt service not found in document.")
        dscr_status = "not_available"

    if dscr is not None and dscr < 0.1:
        info_notes.append(
            f"⚠️  DSCR {dscr:.3f} is extremely low — likely a data extraction error. "
            "Underwriter must verify manually."
        )

    dscr_ok: bool | None = None
    if dscr is not None:
        dscr_ok = dscr >= dscr_min
        if not dscr_ok:
            hard_errors.append(f"DSCR {dscr:.2f} < minimum {dscr_min}.")

    # ── DTI: Total Monthly Debt / Monthly Revenue ─────────────────────────────
    dti: float | None = None
    dti_status = "not_available"

    # P1: stated DTI from document's own ratios section
    if stated_dti_pct is not None:
        dti = stated_dti_pct / 100.0
        dti_status = "stated_in_document"

    # P2: LLM derived
    if dti is None:
        _dti_llm = _f(derived, "dti_ratio")
        if _dti_llm:
            dti = _dti_llm
            dti_status = "llm_derived"
        else:
            dti_pct = derived.get("dti_percent")
            if dti_pct is not None:
                dti = float(dti_pct) / 100.0
                dti_status = "llm_derived_percent"

    # P3: compute from debt / revenue
    if dti is None:
        if revenue_monthly and debt_monthly is not None:
            dti = debt_monthly / revenue_monthly
            dti_status = f"computed debt({debt_monthly:,.0f})/revenue({revenue_monthly:,.0f})"
        else:
            info_notes.append("DTI unavailable: revenue or debt obligations not found.")

    dti_ok: bool | None = None
    if dti is not None:
        dti_ok = dti <= dti_max
        if not dti_ok:
            hard_errors.append(f"DTI {dti:.1%} > maximum {dti_max:.0%}.")

    # ── EBITDA margin ─────────────────────────────────────────────────────────
    def _ratio_or_none(src: dict, key: str) -> float | None:
        v = src.get(key)
        return float(v) if v is not None else None

    # Prefer stated margin, then compute from EBITDA/Revenue
    if stated_em_pct:
        ebitda_margin: float | None = round(stated_em_pct / 100.0, 4)
    elif ebitda_monthly and revenue_monthly:
        raw = ebitda_monthly / revenue_monthly
        ebitda_margin = round(raw, 4) if 0.01 < raw < 1.0 else None
    else:
        ebitda_margin = _ratio_or_none(derived, "ebitda_margin")

    # ── Net profit margin ─────────────────────────────────────────────────────
    net_income_ann = _f(parsed, "net_income_zar")
    if net_income_ann and rev_annual:
        net_profit_margin: float | None = round(net_income_ann / rev_annual, 4)
    else:
        avg_net = derived.get("avg_monthly_net_zar") or 0
        net_profit_margin = _ratio_or_none(derived, "net_profit_margin")
        if net_profit_margin is None and revenue_monthly and avg_net:
            raw_npm = avg_net / revenue_monthly
            net_profit_margin = round(raw_npm, 4) if abs(raw_npm) <= 1.0 else None

    # ── Balance sheet ratios ──────────────────────────────────────────────────
    def _ps(key: str) -> float | None:
        """Safe float from parsed document top-level."""
        try:
            v = parsed.get(key)
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    cur_assets = _ps("current_assets_zar")
    cur_liab   = _ps("current_liabilities_zar")
    tot_debt   = _ps("total_debt_zar")
    tot_equity = _ps("total_equity_zar")

    # Current Ratio = Current Assets / Current Liabilities
    current_ratio: float | None = (
        stated_cr
        or _ratio_or_none(derived, "current_ratio")
        or (round(cur_assets / cur_liab, 4) if cur_assets and cur_liab and cur_liab > 0 else None)
    )

    # Debt-to-Equity = Total Debt / Total Equity
    # Total Debt for financial stmt: use annual_debt_service or short-term debt EMIs
    if tot_debt is None:
        ann_ds = _ps("annual_debt_service_zar") or (ann_ds_parsed or ann_ds_derived)
        tot_debt = ann_ds  # use annual debt service as total debt proxy
    debt_to_equity: float | None = (
        _ratio_or_none(derived, "debt_to_equity")
        or (round(tot_debt / tot_equity, 4) if tot_debt and tot_equity and tot_equity > 0 else None)
    )

    # Years in Business — extract from derived or stated; no fallback for financial stmts
    years_in_biz: float | None = (
        _ratio_or_none(derived, "years_in_business")
        or _stated("years_in_business", lo=0, hi=200)
    )

    # ── DTI override from stated ratios ───────────────────────────────────────
    # If DTI from stated ratios section is more reliable, use it

    # Write computed values back into derived for downstream nodes
    if ebitda_monthly is not None:
        derived["ebitda_monthly_zar"] = ebitda_monthly
    if ebitda_margin is not None:
        derived["ebitda_margin"] = ebitda_margin
    if net_profit_margin is not None:
        derived["net_profit_margin"] = net_profit_margin

    ratios = {
        "dscr":                      round(dscr, 4) if dscr is not None else None,
        "dscr_min":                  dscr_min,
        "dscr_ok":                   dscr_ok,
        "dscr_status":               dscr_status,
        "dti":                       round(dti, 4) if dti is not None else None,
        "dti_max":                   dti_max,
        "dti_ok":                    dti_ok,
        "dti_status":                dti_status,
        "revenue_monthly_zar":       round(revenue_monthly, 2) if revenue_monthly else None,
        "ebitda_monthly_zar":        round(ebitda_monthly, 2) if ebitda_monthly else None,
        "debt_monthly_estimate_zar": round(debt_monthly, 2) if debt_monthly is not None else None,
        "annual_debt_service_zar":   derived.get("annual_debt_service_zar"),
        "ebitda_margin":             ebitda_margin,
        "net_profit_margin":         net_profit_margin,
        "current_ratio":             current_ratio,
        "debt_to_equity":            debt_to_equity,
        "years_in_business":         years_in_biz,
        "info_notes":                info_notes,
    }

    log.info("risk_calc_done")
    out: dict[str, Any] = {"ratios": ratios, "stage": "risk_calc"}
    if hard_errors:
        out["errors"] = hard_errors
    return out
