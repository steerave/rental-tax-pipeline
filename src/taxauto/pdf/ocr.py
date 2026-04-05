"""OCR fallback using pytesseract + pdf2image.

Only imported when a scanned PDF is detected so that missing Tesseract/
poppler binaries don't break text-only workflows.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List


def ocr_pdf(pdf_path: Path, *, dpi: int = 300) -> List[str]:
    """Render each page to an image and run Tesseract OCR. One string per page."""
    # Local imports so that missing OCR binaries don't break import time.
    import pytesseract
    from pdf2image import convert_from_path

    tesseract_cmd = os.environ.get("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    images = convert_from_path(str(pdf_path), dpi=dpi)
    return [pytesseract.image_to_string(img) for img in images]
