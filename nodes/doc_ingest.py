"""Upload / OCR via Unstructured-backed helper."""

from __future__ import annotations

from typing import Any

from services.config_loader import load_docs
from services.logger import get_logger
from services.ocr_service import build_ocr_segments
from models.graph_state import UnderwritingState

log = get_logger(__name__)


def run(state: UnderwritingState) -> dict[str, Any]:
    # If ocr_segments were pre-computed by the wizard, skip re-OCR
    if state.get("ocr_segments"):
        log.info("doc_ingest_using_cached_segments")
        return {"stage": "doc_ingest"}

    docs_cfg = load_docs()
    paths = state.get("uploaded_file_paths") or []
    hints = state.get("category_hints") or []
    mandatory = [c["id"] for c in docs_cfg.get("mandatory_categories", [])]
    errors: list[str] = []

    if not paths:
        errors.append("No uploaded documents; provide uploaded_file_paths.")

    max_mb = float(docs_cfg.get("validation", {}).get("max_file_size_mb", 25))
    for p in paths:
        try:
            from pathlib import Path

            sz = Path(p).stat().st_size / (1024 * 1024)
            if sz > max_mb:
                errors.append(f"File {p} exceeds max {max_mb} MB.")
        except OSError:
            errors.append(f"Cannot read file: {p}")

    segments = build_ocr_segments(paths, hints) if paths else []
    # Light check: mandatory categories can be satisfied by hints when provided
    covered = set(hints[: len(paths)])
    if mandatory and not errors:
        missing = [m for m in mandatory if m not in covered]
        if missing and set(hints) == {"unknown"}:
            errors.append(
                f"Category hints recommended for mandatory ids: {mandatory}; "
                f"OCR will still run.",
            )

    out: dict[str, Any] = {
        "ocr_segments": segments,
        "stage": "doc_ingest",
    }
    if errors:
        out["errors"] = errors
    return out
