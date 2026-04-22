"""Structured extraction output — field names align with config/rules.yaml."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExtractedApplicant(BaseModel):
    model_config = ConfigDict(extra="allow")

    applicant_full_name: str | None = None
    date_of_birth: str | None = None
    gross_monthly_income: float | None = None
    monthly_debt_payments: float | None = None
    noi: float | None = None
    debt_service: float | None = None
    proposed_annuity_premium_zar: float | None = None
    life_expectancy_years: float | None = None
    spouse_benefit_percent: float | None = None
    employer_name: str | None = None
    account_last4: str | None = None


def merged_dict(*records: dict) -> dict:
    """Merge dicts, preferring later non-null values."""
    out: dict = {}
    for r in records:
        for k, v in r.items():
            if v is None:
                continue
            out[k] = v
    return out
