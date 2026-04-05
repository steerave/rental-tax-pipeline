"""Text-layer PDF extraction using pdfplumber."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pdfplumber


def extract_text_pages(pdf_path: Path) -> List[str]:
    """Return one string per page. Empty string for pages with no text layer."""
    pdf_path = Path(pdf_path)
    pages: List[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return pages
