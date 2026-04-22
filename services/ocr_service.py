"""Document ingestion: Unstructured partition with safe fallbacks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.logger import get_logger

log = get_logger(__name__)


def _extract_pdf_pypdf(path: Path) -> str:
    """Extract text from a PDF using pypdf (preferred fallback when unstructured unavailable)."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    except Exception as e:
        log.info("pypdf_fallback_failed", extra={"path": str(path), "error": str(e)})
        return ""


def partition_file_to_text(path: str | Path) -> str:
    """Extract text from pdf/image/office via unstructured; fallback to pypdf then utf-8."""
    path = Path(path)
    if not path.is_file():
        return ""
    suffix = path.suffix.lower()

    # Primary: Unstructured
    try:
        from unstructured.partition.auto import partition

        elements = partition(filename=str(path))
        text = "\n".join(str(el) for el in elements).strip()
        if text:
            return text
    except Exception as e:
        log.info("ocr_unstructured_fallback", extra={"path": str(path), "error": str(e)})

    # Secondary: pypdf for PDFs (much better than raw UTF-8 read)
    if suffix == ".pdf":
        text = _extract_pdf_pypdf(path)
        if text:
            return text

    # Tertiary: plain text files
    if suffix in {".txt", ".csv", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")

    # Last resort: try as text (may produce garbage for binary PDFs)
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def build_ocr_segments(
    file_paths: list[str],
    category_hints: list[str] | None,
) -> list[dict[str, Any]]:
    """Zip files with optional category labels for downstream extraction."""
    hints = category_hints or ["unknown"] * len(file_paths)
    if len(hints) < len(file_paths):
        hints = hints + ["unknown"] * (len(file_paths) - len(hints))
    out: list[dict[str, Any]] = []
    for i, fp in enumerate(file_paths):
        text = partition_file_to_text(fp)
        out.append(
            {
                "path": fp,
                "category_hint": hints[i],
                "ocr_text": text,
            },
        )
    return out
