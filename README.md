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

- **PDF ingestion** — auto-detects text vs. scanned PDFs; routes text PDFs through `pdfplumber` and scanned PDFs through Tesseract OCR.
- **Bank parser** — normalizes every statement into `{date, description, amount, balance, account}` rows with reconciliation against statement totals.
- **LTR PM parser** — extracts pre-categorized entries from property-manager reports.
- **Vendor categorizer** — applies `vendor_mapping.yaml`; known vendors auto-tag, unknown or ambiguous vendors go to review.
- **Google Sheets review roundtrip** — pushes unknowns to a Sheet with dropdown validation, pulls tagged decisions back.
- **Cross-year learning** — every human decision is written back to `vendor_mapping.yaml` with provenance. Ambiguous vendors (same vendor seen in multiple categories) are flagged forever and never auto-tagged.
- **Prior-year bootstrap** — mines completed filed spreadsheets to pre-populate the vendor map before the first real run.
- **Excel writers** — fill the accountant's existing blank templates (`openpyxl`), merging PM-report entries with bank transactions for LTR.
- **Guards** — reconciliation, duplicate detection, and LTR double-count prevention (bank txn vs. PM line item). All guards fail loudly.
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
│   ├── writers/             # str + ltr Excel writers
│   └── guards/              # reconcile, duplicates, double-count
└── tests/
```

## Status

Phase 1 — building core pipeline against synthetic test fixtures. Phase 2 regroups after the first run against real bank and PM documents.

See `CHANGELOG.md` and `docs/status.md` for current progress.

## License

MIT — see `LICENSE`.
