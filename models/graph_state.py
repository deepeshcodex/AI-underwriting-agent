"""LangGraph shared state — typed dict covering all phases."""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, Literal, TypedDict


class UnderwritingState(TypedDict, total=False):
    # Identity
    application_id: str

    # Inputs from form / submission
    applicant_submission: dict[str, Any]

    # Document pipeline
    uploaded_file_paths: list[str]
    category_hints: list[str]
    ocr_segments: list[dict[str, Any]]

    # LLM extraction
    extracted_records: list[dict[str, Any]]
    merged_applicant: dict[str, Any]

    # Deep bank-statement profile (from pass-2 LLM analysis)
    bank_profile: dict[str, Any]

    # OpenAI credit assessment result
    llm_credit_assessment: dict[str, Any]

    # Generic parsed financial document (transactions, summaries, derived metrics)
    parsed_document: dict[str, Any]

    # Pre-screen result
    pre_screen: dict[str, Any]

    # Delinquency + ML credit score (from bank statement)
    delinquency: dict[str, Any]

    # DSCR / DTI ratios
    ratios: dict[str, Any]

    # Bureau + combined credit check
    credit_result: dict[str, Any]

    # Legacy field (kept for backward compat with compute_risk / decide nodes)
    metrics: dict[str, Any]
    credit: dict[str, Any]
    ml: dict[str, Any]

    # Decision routing
    decision: Literal["STP", "MANUAL_REVIEW", "DECLINED"] | str
    review_reasons: list[str]

    # Underwriter preview pane
    policy_preview: dict[str, Any]

    # Generated policy document (base64 bytes)
    policy: dict[str, Any]

    # Accumulated error/warning messages (appended by each node)
    errors: Annotated[list[str], add]

    # Current pipeline stage name
    stage: str


DecisionLiteral = Literal["STP", "MANUAL_REVIEW", "DECLINED"]
