"""Prepare dashboard payload for Streamlit underwriter pane (no UI here)."""

from __future__ import annotations

from typing import Any

from models.graph_state import UnderwritingState


def run(state: UnderwritingState) -> dict[str, Any]:
    preview = dict(state.get("policy_preview") or {})
    preview["decision"] = state.get("decision")
    preview["application_id"] = state.get("application_id")
    preview["metrics"] = state.get("metrics") or {}
    return {"policy_preview": preview, "stage": "ui_pane"}
