"""
SA Bank Structured Annuity — LangGraph workflow (fully config-driven).

Pipeline (per END-TO-END.md):
  pre_screen → doc_ingest → extract_data → delinquency_ml
            → risk_calc  → credit_check  → decision → policy_gen → END

Conditional edge after pre_screen: hard fail → DECLINED → END.
Conditional edge after decision: STP → policy_gen → END, MANUAL_REVIEW → policy_gen → END.
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from models.graph_state import UnderwritingState
from nodes import (
    credit_check,
    decision,
    delinquency_ml,
    doc_ingest,
    extract_data,
    policy_gen,
    pre_screen,
    risk_calc,
)
from services.observability import configure_tracing


# ---------------------------------------------------------------------------
# Routing helpers
# ---------------------------------------------------------------------------

def _route_pre_screen(state: UnderwritingState) -> Literal["declined", "continue"]:
    return "declined" if state.get("decision") == "DECLINED" else "continue"


def _route_decision(state: UnderwritingState) -> Literal["stp", "review"]:
    return "stp" if state.get("decision") == "STP" else "review"


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------

def build_graph():
    configure_tracing()
    g = StateGraph(UnderwritingState)

    # Register nodes
    g.add_node("pre_screen",      pre_screen.run)
    g.add_node("doc_ingest",      doc_ingest.run)
    g.add_node("extract_data",    extract_data.run)
    g.add_node("delinquency_ml",  delinquency_ml.run)
    g.add_node("risk_calc",       risk_calc.run)
    g.add_node("credit_check",    credit_check.run)
    g.add_node("decision",        decision.run)
    g.add_node("policy_gen",      policy_gen.run)

    # Edges
    g.add_edge(START, "pre_screen")

    g.add_conditional_edges(
        "pre_screen",
        _route_pre_screen,
        {"declined": END, "continue": "doc_ingest"},
    )

    g.add_edge("doc_ingest",     "extract_data")
    g.add_edge("extract_data",   "delinquency_ml")
    g.add_edge("delinquency_ml", "risk_calc")
    g.add_edge("risk_calc",      "credit_check")
    g.add_edge("credit_check",   "decision")

    # Both STP and MANUAL_REVIEW go to policy_gen (STP generates auto-approved PDF)
    g.add_edge("decision",   "policy_gen")
    g.add_edge("policy_gen", END)

    return g.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_application(initial: dict[str, Any]) -> UnderwritingState:
    """Run the full underwriting graph. Returns final state."""
    graph = build_graph()
    return graph.invoke(initial)  # type: ignore[return-value]


if __name__ == "__main__":
    demo = run_application(
        {
            "application_id": "demo-001",
            "applicant_submission": {
                "proposed_annuity_premium_zar": 120_000,
                "date_of_birth": "1978-04-10",
            },
            "uploaded_file_paths": [],
            "category_hints": [],
            "errors": [],
        },
    )
    import json

    print("Decision:", demo.get("decision"))
    print("Stage:   ", demo.get("stage"))
    print("Errors:  ", demo.get("errors"))
    if demo.get("policy"):
        print("Policy PDF generated:", demo["policy"].get("filename"), demo["policy"].get("size_kb"), "KB")
