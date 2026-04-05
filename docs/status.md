# Daily Status Log

## 2026-04-05

### Done
- Scaffolded `rental-tax-pipeline`: `.gitignore`, `.env.template`, `config.yaml`, `vendor_mapping.yaml`, `README.md`, `CHANGELOG.md`, `LICENSE`, `pyproject.toml`, `requirements.txt`.
- Python 3.12 venv created; all dependencies installed (pdfplumber, pytesseract, gspread, openpyxl, PyYAML, python-dotenv, rapidfuzz, reportlab, pytest).
- **Phase 1 complete** — full pipeline built end-to-end with TDD:
  - `config.py` — YAML + dotenv loader with per-year path resolution.
  - `pdf/` — auto-routing extractor (pdfplumber for text PDFs, pytesseract fallback for scans).
  - `parsers/bank.py` — normalizes bank statements to `{date, description, amount, balance, account}` + statement totals.
  - `parsers/pm_ltr.py` — LTR property-manager report parser with dual-mode regex (multi-space and pdfplumber-collapsed single-space via known-categories splitter).
  - `categorize/mapper.py` + `learning.py` — vendor normalization, auto-tag/ambiguous/unknown bucketing, cross-year learning with ambiguity detection.
  - `bootstrap/learn_from_prior.py` — mines prior-year filed XLSX + bank PDFs to seed `vendor_mapping.yaml` via amount+date+fuzzy match.
  - `sheets/` — gspread-backed push/pull review roundtrip (fully mockable in tests).
  - `guards/` — reconcile, duplicate, and LTR double-count guards that fail loudly.
  - `writers/str_writer.py` + `ltr_writer.py` — fill accountant templates; LTR merges PM + bank with double-count dropping.
  - `cli.py` — `taxauto extract|categorize|review push|review pull|build|bootstrap` subcommands, all idempotent and `--year`-scoped.
- 50/50 pytest passing including an end-to-end test that drives real reportlab-generated PDFs through the whole pipeline.
- Initial commit pushed to https://github.com/steerave/rental-tax-pipeline.

### In Progress
- Nothing — Phase 1 complete.

### Next
- **Phase 2 (post-document-review planning round):** once real bank and PM PDFs are dropped into `years/2023/inputs/`, regroup to:
  - Validate bank parser against the real statement format(s).
  - Validate PM parser against the real PM report format.
  - Assess OCR quality on any scanned PDFs.
  - Map accountant template cell layouts (the writers currently assume a simple header row + appended rows).
  - Decide whether a dedicated Split workflow is needed.
  - Run `taxauto bootstrap --year 2023` and verify the vendor mapping populates with reasonable entries.

### Notes
- Phase 1 uses synthetic fixtures throughout; no real tax data has touched the repo.
- The PM parser's `known_categories` list is a Phase 1 convenience — Phase 2 will move it into `config.yaml` once real categories are observed.
- Double-count guard caught a real regression in the e2e test (bank rent deposit mirroring a PM "Rent Received" line), confirming the design.
