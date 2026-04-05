"""Auto-routing PDF extractor.

Detects whether a PDF has a real text layer. If so, uses pdfplumber.
Otherwise, routes to Tesseract OCR.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from .ocr import ocr_pdf
from .text import extract_text_pages


@dataclass(frozen=True)
class ExtractedDocument:
    path: Path
    method: str  # "text" or "ocr"
    pages: List[str]

    @property
    def full_text(self) -> str:
        return "\n".join(self.pages)


# Heuristic: a page is "text-bearing" if its extracted text has at least this
# many non-whitespace characters. Tuned low so we don't miss sparse bank
# statement pages, high enough to catch an accidental stray glyph on a scan.
_MIN_TEXT_CHARS_PER_PAGE = 10


def is_scanned(pdf_path: Path) -> bool:
    """Return True if the PDF appears to be a scanned image with no text layer."""
    pages = extract_text_pages(Path(pdf_path))
    if not pages:
        return True
    total_chars = sum(len((p or "").strip()) for p in pages)
    # A scanned PDF typically has zero or near-zero extractable text.
    return total_chars < _MIN_TEXT_CHARS_PER_PAGE


def extract_pdf(pdf_path: Path) -> ExtractedDocument:
    """Extract every page of a PDF as a list of strings, auto-routing text vs OCR."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if is_scanned(pdf_path):
        pages = ocr_pdf(pdf_path)
        return ExtractedDocument(path=pdf_path, method="ocr", pages=pages)

    pages = extract_text_pages(pdf_path)
    return ExtractedDocument(path=pdf_path, method="text", pages=pages)
