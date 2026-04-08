# rental-tax-pipeline

End-to-end Python pipeline that turns a rental business's raw bank statements and property-manager PDFs into accountant-ready Excel workbooks for tax filing — with a human-in-the-loop review step and cross-year learning that shrinks manual work every year.

Built for a real rental business with both **short-term rentals (STR)** and **long-term rentals (LTR)**. The same shared bank account mixes STR, LTR, and personal transactions, so human review is unavoidable — but the tool learns from every decision and auto-tags known vendors on the next run.

## Why this exists

Rental owners hand their accountant two spreadsheets every year: one for STR, one for LTR. Today that's assembled by hand from:

- Bank statements (PDF) — one shared account, mixed transactions.
- LTR property-manager reports (PDF) — pre-categorized, authoritative for rental income.
- STR has no PM — bank statements are the only source of truth.

This project automates everything except the irreducible judgment calls.

## Features

- **PDF ingestion** — auto-detects text vs. scanned PDFs; routes text PDFs through `pdfplumber` and scanned PDFs through Tesseract OCR. Input file classifier auto-routes Chase checking, Chase credit card, and Rent QC PDFs by filename pattern (supports both `rentqc-*` and `Owner packet` naming conventions).
- **Chase Business Checking parser** — handles multi-line ACH description blocks, instance-count reconciliation, and Chase-specific `*start*`/`*end*` pdfplumber anchor artifacts.
- **Chase Ink credit card parser** — dual-cardholder state machine (cards 1091 + 1109) extracting transactions from interleaved per-card sections across 13 monthly statements.
- **Rent QC property-manager parser** — x-coordinate column binning to reliably extract 28 expense/income categories across 3 properties per report, with 6-invariant reconciliation per property per report.
- **Rent QC Cash Flow 12-Month summary parser** — extracts pre-computed annual category totals from the appendix pages of Rent QC owner statements. These totals match the accountant's filed values much more closely than summing individual transactions, and capture "Major Repairs and Renovations" that were missing from transaction-level parsing.
- **Vendor categorizer** — applies `vendor_mapping.yaml`; known vendors auto-tag, unknown or ambiguous vendors go to review. Automatically skips STR income deposits (Airbnb/Vrbo), LTR owner disbursements (Rent QC), Etsy payouts, and credit card payment entries from the review queue since these are already captured by dedicated data sources.
- **Chase checking FEES section** — parses bank service fees as a separate section (distinct from Electronic Withdrawals) and handles OCR-dropped check numbers with a fallback regex.
- **Margarete sheet reconciliation** — matches review-queue transactions against a bookkeeper's manually-categorized expense worksheet by date + amount, then maps property names and expense descriptions to pipeline dropdown values. Pre-fills Category, Property, and Expense Type on both transaction and vendor rows in the review Sheet.
- **Google Sheets review roundtrip** — pushes unknowns to a Sheet with dropdown validation, pulls tagged decisions back. Year-specific tab names (e.g. "Vendors 2025") allow multiple years to coexist. Standalone formatting script applies dropdown validation (Category, Property, Expense Type), frozen/bold headers, column widths, currency formatting, editable-column highlighting, alternating row colors, and auto-filters.
- **Cross-year learning** — every human decision is written back to `vendor_mapping.yaml` with provenance. Ambiguous vendors (same vendor seen in multiple categories) are flagged forever and never auto-tagged.
- **Prior-year bootstrap** — mines completed filed spreadsheets and Rent QC reports to pre-populate the vendor map (68 vendors learned from 2024 Rent QC data).
- **Excel writers** — fill the accountant's existing P&L templates (`openpyxl`). STR writer uses hardcoded row positions; LTR writer dynamically scans column C per sheet to handle drifting layouts. All formula cells (totals, net income) are preserved.
- **Transactions audit tab** — appends a `{property}_txns` sheet to each output workbook showing every transaction that contributed to the P&L values.
- **Live Google Sheets STR reader** — reads STR earnings directly from 4 property Google Sheets via `gspread`, with fuzzy tab-name matching (`'24 earnings`, `2024 Earnings`, etc.), flexible date parsing, and automatic handling of cancelled bookings and dollar-sign formatting. Falls back to local XLSX if Sheets aren't configured.
- **Guards** — Chase checking reconciliation (4 invariants), Rent QC reconciliation (6 invariants), eCheck-reference-based LTR double-count guard (bank deposit vs. PM owner disbursement matching), STR platform-vs-bank reconciliation, and duplicate detection. All guards fail loudly.
- **Split property allocation** — tagging a vendor with Category "STR - Split" or "LTR - Split" in the review Sheet automatically divides the expense evenly across all 4 STR properties or all 3 LTR properties, useful for shared costs like advertising. No Property selection needed.
- **Property alias configuration** — maps variant property names (e.g., Rent QC's "308 S Lincoln Ave" to template's "308 Lincoln Ave").
- **Idempotent CLI** — every step is safe to re-run.

## Commands

All CLI commands accept `--year YYYY` and are idempotent.

```bash
# Mine a completed prior year to pre-populate vendor_mapping.yaml
taxauto bootstrap --year 2023

# Parse PDFs into normalized, cached transactions
taxauto extract --year 2025

# Apply vendor mapping; unknown vendors go to the review queue
taxauto categorize --year 2025

# Push review queue to Google Sheet
taxauto review push --year 2025

# Pull bookkeeper's tags back; update vendor_mapping.yaml
taxauto review pull --year 2025

# Run guards and fill accountant templates
taxauto build --year 2025

# Compare generated workbooks against filed originals
taxauto verify --year 2025

# Apply dropdown validation + visual formatting to review Sheet
python -m taxauto.sheets.format_review
```

## Tech stack

- Python 3.11+
- `pdfplumber` · `pytesseract` — PDF extraction
- `gspread` — Google Sheets roundtrip
- `openpyxl` — Excel template writing
- `PyYAML` · `python-dotenv` — config and secrets
- `pytest` — TDD

## Setup

```bash
# Clone
git clone https://github.com/steerave/rental-tax-pipeline.git
cd rental-tax-pipeline

# Create venv (Python 3.11+)
py -3.12 -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# or: .venv\Scripts\activate.bat  (cmd)

# Install
pip install -r requirements.txt

# Configure
cp .env.template .env
# fill in GOOGLE_SERVICE_ACCOUNT_JSON and REVIEW_SHEET_ID
```

Drop the accountant's blank templates into `templates/` and prior-year documents into `years/YYYY/inputs/` and `years/YYYY/outputs/`.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          INPUT SOURCES                          │
├───────────────┬───────────────┬──────────────┬─────────────────┤
│ Chase Bank    │ Chase Credit  │ Rent QC      │ STR Google      │
│ Statements    │ Card PDFs     │ Owner PDFs   │ Sheets (×4)     │
│ (12 PDFs/yr)  │ (13 PDFs/yr)  │ (13 PDFs/yr) │ earnings tabs   │
└───────┬───────┴───────┬───────┴──────┬───────┴────────┬────────┘
        │               │              │                │
        └───────────────┴──────────────┘                │
                        │  text / OCR                   │ gspread
               ┌────────▼────────┐                      │
               │    EXTRACT      │                      │
               │ pdfplumber +    │                      │
               │ Tesseract OCR   │                      │
               └────────┬────────┘                      │
                        │ normalized transactions        │
               ┌────────▼────────┐                      │
               │   CATEGORIZE    │                      │
               │ vendor_mapping  │◄─────────────────────┘
               │ auto-tag known  │   (STR revenue resolved here)
               └────┬───────┬────┘
                    │       │
              known │       │ unknown / ambiguous
                    │  ┌────▼────────────┐
                    │  │     REVIEW      │  ← Margarete's
                    │  │  Google Sheets  │    bookkeeper sheet
                    │  │  push / pull    │    pre-fills rows
                    │  │  cross-year     │
                    │  │  learning       │
                    │  └────┬────────────┘
                    │       │ human decisions written back
                    └───────┤   to vendor_mapping.yaml
                            │
               ┌────────────▼────────┐
               │       BUILD         │
               │ aggregate by prop.  │
               │ fill Excel templates│
               │ (STR + LTR P&L)     │
               └────────────┬────────┘
                            │
               ┌────────────▼────────┐
               │       VERIFY        │
               │ cell-by-cell diff   │
               │ vs. filed workbooks │
               └─────────────────────┘
```

## Project layout

```
rental-tax-pipeline/
├── config.yaml              # paths, categories, PM identities, bootstrap thresholds
├── vendor_mapping.yaml      # GLOBAL learned vendor → category map (grows over time)
├── templates/               # Accountant's blank XLSX templates
├── years/YYYY/              # Per-year inputs / intermediate / outputs
├── src/taxauto/             # Source package
│   ├── cli.py
│   ├── config.py
│   ├── pdf/                 # text/OCR extraction
│   ├── parsers/             # bank + pm_ltr
│   ├── categorize/          # mapper + learning
│   ├── bootstrap/           # learn from prior-year filings
│   ├── sheets/              # gspread push/pull
│   ├── reconcile/           # cross-source matching (Margarete sheet)
│   ├── writers/             # str + ltr Excel writers
│   └── guards/              # reconcile, duplicates, double-count
└── tests/
```

## Status

Pipeline is complete and running for both 2024 and 2025 tax years. 153 tests passing.

See `CHANGELOG.md` and `docs/status.md` for current progress.

## License

MIT — see `LICENSE`.
