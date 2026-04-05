# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Initial project scaffolding: `.gitignore`, `.env.template`, `config.yaml`, `vendor_mapping.yaml`, `README.md`, `CHANGELOG.md`.
- `src/taxauto` package skeleton.
- Config loader (`src/taxauto/config.py`) with YAML + dotenv support.
- PDF extractor with auto-detection between text (pdfplumber) and scanned (pytesseract) PDFs.
- Bank statement parser producing normalized transaction rows.
- Vendor mapper and learning module backed by `vendor_mapping.yaml`.
- Prior-year bootstrap module that mines filed Excel workbooks and bank PDFs to seed vendor mappings.
- LTR property manager report parser.
- Google Sheets review push/pull roundtrip using `gspread`.
- Reconciliation, duplicate, and LTR double-count guards.
- STR and LTR Excel writers that fill the accountant's blank templates.
- Command-line interface (`taxauto`) with `extract`, `categorize`, `review`, `build`, and `bootstrap` subcommands.
- Full pytest suite covering all modules plus an end-to-end synthetic-fixture integration test.
