"""Generate the Rent QC sample fixture PDF.

Run once from the repo root:

    .venv/Scripts/python.exe tests/fixtures/rent_qc/_build_fixture.py

The output at tests/fixtures/rent_qc/sample_janfeb_2024.pdf is committed.
All names, addresses, amounts, and references are synthetic.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


# Column x-positions modeled on real Rent QC statements (see discovery_rentqc.md).
# These are absolute x positions in points (72pt = 1 inch). The real reports use
# a ~540pt wide layout; we reuse the same positions so the parser's x-binning
# thresholds work on both synthetic and real PDFs.
COL_DATE = 43
COL_PAYEE = 90
COL_TYPE = 156
COL_REF = 191
COL_DESC = 249
# Amount columns are right-aligned in the real report. For the synthetic fixture
# we use left-aligned text at column-start anchors that fall cleanly inside the
# Cash In vs Cash Out x ranges the parser expects. Column boundaries (used by
# the parser): Cash In <= 490 < Cash Out <= 528 < Balance.
COL_CASH_IN = 460      # center of Cash In column (~455-490 in real PDFs)
COL_CASH_OUT = 500     # center of Cash Out column (~495-528 in real PDFs)
COL_BAL = 535


def _draw_row(c: canvas.Canvas, y: float, cells: dict[int, str]) -> None:
    """Draw one text row by placing each (x, text) at the given y."""
    for x, text in cells.items():
        c.drawString(x, y, text)


def build(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    # Use Helvetica 8pt to mimic the proportional font used by real Rent QC PDFs;
    # Courier is too wide and causes adjacent columns to visually collide, which
    # makes pdfplumber merge tokens across column boundaries.
    c.setFont("Helvetica", 8)

    height = letter[1]  # 792

    def yy(top: float) -> float:
        """Convert a top-down 'y=...' coordinate (like pdfplumber's) to reportlab's bottom-up."""
        return height - top

    # ---- PAGE 1: Header + Consolidated Summary ----
    c.drawString(100, yy(50), "Rent QC, LLC")
    c.drawString(100, yy(65), "Owner Statement")
    c.drawString(100, yy(80), "Sample Holdings LLC,  Jan 13, 2024 - Feb 12, 2024")

    c.drawString(40, yy(120), "Consolidated Summary (3 properties)")
    _draw_row(c, yy(145), {43: "Beginning Balance", 530: "2,143.00"})
    _draw_row(c, yy(160), {43: "Cash In", 530: "2,555.50"})
    _draw_row(c, yy(175), {43: "Cash Out", 525: "-612.95"})
    _draw_row(c, yy(190), {43: "Owner Disbursements", 525: "-1,800.55"})
    _draw_row(c, yy(205), {43: "Ending Cash Balance", 530: "2,285.00"})

    # Property section header on same page
    c.drawString(100, yy(260), "SW 1015 39th St. Bettendorf - 1015 39th St., Bettendorf, IA 52722")
    c.drawString(40, yy(290), "Property Cash Summary")
    _draw_row(c, yy(310), {43: "Beginning Balance", 530: "2,143.00"})
    _draw_row(c, yy(325), {43: "Cash In", 530: "2,555.50"})
    _draw_row(c, yy(340), {43: "Cash Out", 525: "-612.95"})
    _draw_row(c, yy(355), {43: "Owner Disbursements", 525: "-1,800.55"})
    _draw_row(c, yy(370), {43: "Ending Cash Balance", 530: "2,285.00"})
    _draw_row(c, yy(385), {43: "Property Reserve", 525: "-1,200.00"})
    _draw_row(c, yy(400), {43: "Prepayments", 525: "-1,085.00"})
    _draw_row(c, yy(415), {43: "Net Owner Funds", 545: "0.00"})

    # Transactions table header
    c.drawString(40, yy(445), "Transactions")
    _draw_row(
        c,
        yy(465),
        {
            COL_DATE: "Date",
            COL_PAYEE: "Payee / Payer",
            COL_TYPE: "Type",
            COL_REF: "Reference",
            COL_DESC: "Description",
            455: "Cash In",
            495: "Cash Out",
            COL_BAL: "Balance",
        },
    )
    _draw_row(c, yy(480), {COL_DESC: "Beginning Cash Balance as of 01/13/2024", COL_BAL: "2,143.00"})

    # ---- Transaction rows ----
    # Row 1: simple single-line, unit-prefixed Rent Income (Cash In)
    _draw_row(
        c,
        yy(500),
        {
            COL_DATE: "01/17/2024",
            COL_PAYEE: "John Smith",
            COL_TYPE: "eCheck",
            COL_REF: "302E-CBC0",
            COL_DESC: "102 - Rent Income - January 2024",
            COL_CASH_IN: "250.00",
            COL_BAL: "2,393.00",
        },
    )
    # "receipt" type continuation below
    _draw_row(c, yy(510), {COL_TYPE: "receipt"})

    # Row 2: Payee wraps (continuation ABOVE), Supply and Materials (Cash Out), unit 204
    _draw_row(c, yy(525), {COL_PAYEE: "Jane"})
    _draw_row(
        c,
        yy(535),
        {
            COL_DATE: "01/23/2024",
            COL_PAYEE: "Doe",
            COL_TYPE: "Check",
            COL_REF: "6854",
            COL_DESC: "204 - Supply and Materials - sample",
            COL_CASH_OUT: "42.95",
            COL_BAL: "2,350.05",
        },
    )
    # Description wrap BELOW
    _draw_row(c, yy(545), {COL_DESC: "materials for unit"})

    # Row 3: Laundry Income (bare category, no unit)
    _draw_row(
        c,
        yy(565),
        {
            COL_DATE: "01/24/2024",
            COL_PAYEE: "Laundry",
            COL_TYPE: "Receipt",
            COL_REF: "LC-001",
            COL_DESC: "Laundry Income - Laundry coins",
            COL_CASH_IN: "55.50",
            COL_BAL: "2,405.55",
        },
    )

    # Row 4: 1/2 upper unit (the slash-space token) -- this covers 308 Lincoln style
    # Kept on 1015 section for simplicity; the parser only cares about the regex.
    _draw_row(
        c,
        yy(585),
        {
            COL_DATE: "01/25/2024",
            COL_PAYEE: "Alex R.",
            COL_TYPE: "eCheck",
            COL_REF: "AB12-CD34",
            COL_DESC: "301 - Late Fee - Late Fee for Jan 2024",
            COL_CASH_IN: "2,250.00",
            COL_BAL: "4,655.55",
        },
    )

    # Row 5: Management Fees (bare category, Cash Out)
    _draw_row(
        c,
        yy(605),
        {
            COL_DATE: "01/31/2024",
            COL_PAYEE: "Rent QC, LLC",
            COL_TYPE: "Check",
            COL_REF: "6766",
            COL_DESC: "Management Fees - Management Fees for 01/2024",
            COL_CASH_OUT: "570.00",
            COL_BAL: "4,085.55",
        },
    )

    # Row 6: Owner Disbursement (the eCheck double-count key row)
    _draw_row(c, yy(625), {COL_PAYEE: "Sample"})
    _draw_row(
        c,
        yy(635),
        {
            COL_DATE: "01/12/2024",
            COL_TYPE: "eCheck",
            COL_REF: "65D1-A640",
            COL_DESC: "Owner Distributions / S corp Distributions - Owner payment",
            COL_CASH_OUT: "1,800.55",
            COL_BAL: "2,285.00",
        },
    )
    _draw_row(c, yy(645), {COL_PAYEE: "Holdings LLC", COL_DESC: "for 01/2024"})

    # Ending + Total lines
    _draw_row(c, yy(670), {COL_DESC: "Ending Cash Balance", COL_BAL: "2,285.00"})
    _draw_row(c, yy(685), {COL_DATE: "Total", 454: "2,555.50", 495: "2,413.50"})

    c.showPage()

    # ---- PAGE 2: Appendix (stop marker) ----
    c.setFont("Helvetica", 8)
    c.drawString(40, yy(60), "Cash Flow - 12 Month")
    c.drawString(40, yy(80), "Account Name  Jan 2024  Feb 2024  Total")
    c.drawString(40, yy(95), "Total Operating  2,555.50  2,555.50  5,111.00")
    c.save()


if __name__ == "__main__":
    out = Path(__file__).parent / "sample_janfeb_2024.pdf"
    build(out)
    print(f"Wrote {out}")
