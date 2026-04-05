"""Tests for the PDF extraction layer.

The extractor must:
- Return text from text-based PDFs without touching OCR.
- Detect scanned PDFs (no extractable text) and route them through OCR.
- Produce a deterministic list of page strings.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from taxauto.pdf import extractor as extractor_module
from taxauto.pdf.extractor import ExtractedDocument, extract_pdf, is_scanned


def _make_text_pdf(path: Path, pages: list[str]) -> None:
    """Build a tiny text PDF using reportlab."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    for page_text in pages:
        text_obj = c.beginText(72, 720)
        for line in page_text.splitlines() or [page_text]:
            text_obj.textLine(line)
        c.drawText(text_obj)
        c.showPage()
    c.save()


def _make_image_pdf(path: Path, pages: int = 1) -> None:
    """Build a PDF whose pages contain only a rasterized image (no text layer)."""
    from PIL import Image, ImageDraw

    images = []
    for _ in range(pages):
        img = Image.new("RGB", (400, 200), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 80), "scanned page", fill="black")
        images.append(img)
    images[0].save(path, "PDF", resolution=100.0, save_all=True, append_images=images[1:])


def test_extract_text_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "text.pdf"
    _make_text_pdf(pdf, ["Hello world", "Page two here"])

    doc = extract_pdf(pdf)

    assert isinstance(doc, ExtractedDocument)
    assert doc.method == "text"
    assert len(doc.pages) == 2
    assert "Hello world" in doc.pages[0]
    assert "Page two" in doc.pages[1]


def test_is_scanned_detects_image_only_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    _make_image_pdf(pdf)

    assert is_scanned(pdf) is True


def test_is_scanned_false_for_text_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "text.pdf"
    _make_text_pdf(pdf, ["some readable text"])

    assert is_scanned(pdf) is False


def test_extract_routes_scanned_pdf_through_ocr(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    _make_image_pdf(pdf, pages=2)

    # We don't require tesseract to be installed on the test machine.
    # Patch the OCR function with a deterministic stub.
    def fake_ocr(pdf_path: Path) -> list[str]:
        return ["OCR page 1", "OCR page 2"]

    with patch.object(extractor_module, "ocr_pdf", side_effect=fake_ocr):
        doc = extract_pdf(pdf)

    assert doc.method == "ocr"
    assert doc.pages == ["OCR page 1", "OCR page 2"]


def test_extract_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        extract_pdf(tmp_path / "nope.pdf")
