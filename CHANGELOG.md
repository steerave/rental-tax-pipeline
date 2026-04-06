# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Live Google Sheets STR earnings reader via `gspread` with fuzzy tab-name matching, flexible date parsing, and data-quality handling (cancelled bookings, dollar signs, missing-year dates).
- `str_sheets` config section mapping property names to Google Sheet IDs.
- CLI `build` command now reads STR revenue from live Google Sheets when configured, with XLSX fallback.
- Live integration test for Oak Glen Google Sheet reader.
- `review push` reuses a pre-created Google Sheet when `REVIEW_SHEET_ID` env var or cached `review_sheet_id.txt` is present (required for service accounts on free GCP projects with zero Drive storage).

## [0.2.0] - 2026-04-05

### Added
- Chase Business Complete Checking parser with multi-line ACH block handling and instance-count reconciliation.
- Chase Ink Business credit card parser with dual-cardholder state machine (cards 1091 + 1109).
- Rent QC property-manager owner statement parser with x-coordinate column binning and 28-category vocabulary.
- Input file classifier: filename-pattern routing for Chase checking, Chase credit card, and Rent QC PDFs.
- Chase text pre-cleaner: strips pdfplumber `*start*`/`*end*` anchor artifacts.
- Chase checking reconciliation guard (4 invariants including instance-count crosscheck).
- Rent QC reconciliation guard (6 invariants per property per report).
- eCheck-reference-based LTR double-count guard matching bank deposits to Rent QC owner disbursements.
- STR platform-vs-bank reconciliation guard.
- STR earnings XLSX reader (Google Sheets live reader deferred to Phase 3).
- Interest expense per-property YAML loader (sourced from Form 1098).
- Per-property category aggregator.
- Rent QC → LTR template category mapping configuration (28 categories → template row labels).
- STR writer v2: fills real accountant P&L template with hardcoded row positions.
- LTR writer v2: per-sheet dynamic column-C row scanning for drifting template layouts.
- Per-property transactions audit tab for output traceability.
- Phase 2 CLI wiring: extract, categorize, review, build, bootstrap subcommands all connected to new parsers and writers.
- Bootstrap v2: learns vendor→category mappings from Rent QC reports.
- Property alias configuration for Rent QC→template property name normalization.

### Changed
- Replaced Phase 1 bank parser, PM parser, reconcile guard, double-count guard, and both writers with format-specific Phase 2 implementations grounded in real 2024 document formats.

## [0.1.0] - 2026-04-05

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
- STR writer v2: fills real accountant P&L template with hardcoded row positions, forces `C33="other"`, preserves formula cells.
- LTR writer v2: fills real accountant P&L template with per-sheet dynamic row scanning (handles drifting row positions and case-insensitive label matching).
- Per-property transactions audit tab appended to output workbooks for traceability.
- Command-line interface (`taxauto`) with `extract`, `categorize`, `review`, `build`, and `bootstrap` subcommands.
- Full pytest suite covering all modules plus an end-to-end synthetic-fixture integration test.
