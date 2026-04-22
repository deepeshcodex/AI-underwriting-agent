"""
SA Policy PDF generator — ReportLab, all template text config-driven.
Falls back to plaintext bytes if ReportLab is not installed.
"""

from __future__ import annotations

import base64
import io
from datetime import date
from typing import Any

from services.config_loader import load_underwriting
from services.logger import get_logger
from models.graph_state import UnderwritingState

log = get_logger(__name__)


def _try_reportlab(doc: dict[str, Any]) -> bytes | None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        return None

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("SA Bank — Structured Annuity Policy", styles["Title"]))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"Reference: {doc['reference']}", styles["Normal"]))
    story.append(Paragraph(f"Date: {doc['policy_date']}", styles["Normal"]))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Applicant Details", styles["Heading2"]))
    applicant = doc.get("applicant") or {}
    app_table = [[k.replace("_", " ").title(), str(v)] for k, v in applicant.items() if v]
    if app_table:
        t = Table([["Field", "Value"]] + app_table, colWidths=[70 * mm, 100 * mm])
        t.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]),
        )
        story.append(t)
        story.append(Spacer(1, 6 * mm))

    # ── Underwriting Metrics ────────────────────────────────────────────────
    story.append(Paragraph("Underwriting Metrics", styles["Heading2"]))
    metrics = doc.get("underwriting_metrics") or {}
    met_rows = [[k.replace("_", " ").title(), str(v)] for k, v in metrics.items() if v and v != "—"]
    if met_rows:
        tm = Table([["Metric", "Value"]] + met_rows, colWidths=[70 * mm, 100 * mm])
        tm.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#004488")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.lightblue, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(tm)
        story.append(Spacer(1, 6 * mm))

    # ── Loan Eligibility ────────────────────────────────────────────────────
    story.append(Paragraph("Loan Eligibility Assessment", styles["Heading2"]))
    elig = doc.get("loan_eligibility") or {}
    elig_summary = elig.get("eligibility_summary", "")
    if elig_summary:
        story.append(Paragraph(elig_summary, styles["Normal"]))
        story.append(Spacer(1, 3 * mm))
    elig_rows = []
    for k, v in elig.items():
        if k == "eligibility_summary":
            continue
        if isinstance(v, bool):
            display = "✓ PASS" if v else "✗ FAIL"
        elif v is None:
            display = "N/A"
        else:
            display = str(v)
        elig_rows.append([k.replace("_", " ").title(), display])
    if elig_rows:
        te = Table([["Check", "Result"]] + elig_rows, colWidths=[90 * mm, 80 * mm])
        te.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#005500")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.lightgreen, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(te)
        story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Annuity Terms", styles["Heading2"]))
    terms = doc.get("terms") or {}
    terms_table = [[k.replace("_", " ").title(), str(v)] for k, v in terms.items() if v]
    if terms_table:
        t2 = Table([["Term", "Value"]] + terms_table, colWidths=[70 * mm, 100 * mm])
        t2.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#555500")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.lightyellow, colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]),
        )
        story.append(t2)
        story.append(Spacer(1, 6 * mm))

    schedule = doc.get("premium_schedule") or []
    if schedule:
        story.append(Paragraph("Premium Schedule", styles["Heading2"]))
        rows = [["Year", "Annual Premium (ZAR)", "Cumulative (ZAR)"]] + [
            [str(r["year"]), f"R {r['annual']:,.0f}", f"R {r['cumulative']:,.0f}"]
            for r in schedule
        ]
        t3 = Table(rows, colWidths=[30 * mm, 80 * mm, 80 * mm])
        t3.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.lightyellow, colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]),
        )
        story.append(t3)

    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        "This policy is issued subject to the terms and conditions of SA Bank's Structured Annuity product. "
        "Generated by the SA Underwriting Agent.",
        styles["Italic"],
    ))

    pdf.build(story)
    return buf.getvalue()


def _plaintext_policy(doc: dict[str, Any]) -> bytes:
    lines = [
        "SA BANK — STRUCTURED ANNUITY POLICY",
        "=" * 45,
        f"Reference  : {doc['reference']}",
        f"Date       : {doc['policy_date']}",
        "",
        "APPLICANT DETAILS",
        "-" * 30,
    ]
    for k, v in (doc.get("applicant") or {}).items():
        lines.append(f"  {k:<30}: {v}")
    lines += ["", "UNDERWRITING METRICS", "-" * 30]
    for k, v in (doc.get("underwriting_metrics") or {}).items():
        lines.append(f"  {k:<30}: {v}")
    lines += ["", "LOAN ELIGIBILITY", "-" * 30]
    elig = doc.get("loan_eligibility") or {}
    if elig.get("eligibility_summary"):
        lines.append(f"  {elig['eligibility_summary']}")
        lines.append("")
    for k, v in elig.items():
        if k == "eligibility_summary":
            continue
        display = ("PASS" if v else "FAIL") if isinstance(v, bool) else ("N/A" if v is None else str(v))
        lines.append(f"  {k:<30}: {display}")
    lines += ["", "ANNUITY TERMS", "-" * 30]
    for k, v in (doc.get("terms") or {}).items():
        lines.append(f"  {k:<30}: {v}")
    lines += ["", "PREMIUM SCHEDULE", "-" * 30]
    for r in doc.get("premium_schedule") or []:
        lines.append(f"  Year {r['year']:>2}: R {r['annual']:>12,.0f}   Cumul: R {r['cumulative']:>14,.0f}")
    return "\n".join(lines).encode("utf-8")


def run(state: UnderwritingState) -> dict[str, Any]:
    cfg         = load_underwriting()
    merged      = state.get("merged_applicant") or {}
    ratios      = state.get("ratios") or {}
    credit      = state.get("credit_result") or {}
    parsed      = state.get("parsed_document") or {}
    assess      = state.get("llm_credit_assessment") or {}
    app_id      = state.get("application_id") or "SA-000"
    decision    = state.get("decision") or "MANUAL_REVIEW"
    review_rsns = state.get("review_reasons") or []

    premium = float(merged.get("proposed_annuity_premium_zar") or cfg.get("rules", {}).get("min_premium", 50000))
    years   = 10
    schedule = [
        {"year": y + 1, "annual": premium, "cumulative": premium * (y + 1)}
        for y in range(years)
    ]

    eligibility = (parsed.get("loan_eligibility") or {})
    derived     = (parsed.get("derived") or {})

    doc = {
        "reference":   app_id,
        "policy_date": str(date.today()),
        "applicant": {
            "name":                   merged.get("applicant_full_name") or parsed.get("entity_name") or "—",
            "date_of_birth":          merged.get("date_of_birth") or "—",
            "employer":               merged.get("employer_name") or derived.get("employer_name") or "—",
            "account_number":         merged.get("account_last4") or parsed.get("account_number_masked") or "—",
            "spouse_benefit_percent": merged.get("spouse_benefit_percent") or "—",
        },
        "underwriting_metrics": {
            "dscr":         ratios.get("dscr") or "—",
            "dti":          f"{ratios.get('dti', 0):.1%}" if ratios.get("dti") is not None else "—",
            "credit_score": credit.get("combined_score") or "—",
            "credit_grade": assess.get("credit_grade") or "—",
            "monthly_income": f"R {derived.get('avg_monthly_income_zar', 0):,.0f}" if derived.get("avg_monthly_income_zar") else "—",
            "monthly_debt":   f"R {derived.get('loan_repayment_monthly_zar', 0):,.0f}" if derived.get("loan_repayment_monthly_zar") else "—",
        },
        "loan_eligibility": {
            "dscr_pass":           eligibility.get("dscr_pass"),
            "dti_pass":            eligibility.get("dti_pass"),
            "delinquency_free":    eligibility.get("delinquency_free"),
            "premium_affordable":  eligibility.get("premium_affordable"),
            "eligibility_summary": eligibility.get("eligibility_summary") or (
                "Approved — all checks passed." if decision == "STP" else
                f"Review required: {'; '.join(review_rsns[:2])}" if review_rsns else
                "Manual review required."
            ),
            "ai_recommendation":   assess.get("recommendation"),
        },
        "terms": {
            "annual_premium_zar": f"R {premium:,.0f}",
            "decision":           decision,
            "currency":           cfg.get("currency", "ZAR"),
        },
        "premium_schedule": schedule,
    }

    pdf_bytes = _try_reportlab(doc) or _plaintext_policy(doc)
    is_pdf = pdf_bytes[:4] == b"%PDF"

    policy = {
        "bytes_b64": base64.b64encode(pdf_bytes).decode("ascii"),
        "is_pdf": is_pdf,
        "filename": f"{app_id}_SA_policy.{'pdf' if is_pdf else 'txt'}",
        "size_kb": round(len(pdf_bytes) / 1024, 1),
    }

    log.info("policy_generated")
    return {"policy": policy, "stage": "policy_gen"}
