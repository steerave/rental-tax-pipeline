# Daily Status Log

## 2026-04-17

**Done:**
- Re-ran `reconcile_margarete_v2.py` after Margarete added missing STR expense entries to her 2025 sheet — 386 rows updated, match rate 72.1% (631/875)
- Diagnosed and reported 24 skipped rows in `build-str` (22 LTR utility rows now handled separately, 2 wrong-year entries fixed by Margarete)
- Fixed Unicode encoding crash in `build-str` print statement (`→` → `->`)
- Added `supplemental_ltr_expenses.yaml` + `src/taxauto/sources/supplemental_ltr.py` for direct-pay LTR expenses not in Rent QC; wired into `cmd_build`
- Reversed the supplemental LTR utility entries after confirming they were duplicates of STR water bills
- Added `taxauto build-report --year YYYY` command: fills `Rental-Properties.xlsx` template from STR + LTR generated workbooks; output is `{year} - Rental-Properties_generated.xlsx`
- Created `~/.claude/skills/rental-report/SKILL.md` for future reuse

**In Progress:**
- Margarete's 2025 sheet still has 1 blank-Type row (5/21, "supplies & maintenance") — needs property filled in

**Next:**
- Confirm August LTR utility gap with Margarete (no entries for Aug in her sheet)
- Re-run `build-str --year 2025` and `build-report --year 2025` after Margarete fills blank-Type row
- Add `build-ltr` command to prevent `build` from accidentally overwriting STR workbook with empty data
- Continue 2024 review: tag remaining ~244 untagged transactions, then `review pull → build → verify`

**Notes:**
- `build` overwrites the STR workbook with empty expenses when `resolved_decisions.json` is missing — always use `build-str` for STR, not `build`
- `supplemental_ltr_expenses.yaml` is the right place for any direct-pay LTR expenses not captured by Rent QC
- `Rental-Properties.xlsx` template lives in `years/2024/outputs/` and is never modified — always used read-only

## 2026-04-06

### Done
- **Phase 3 smart review workflow complete.**
- Review Sheet populated with ~878 vendor rows + 1,410 transaction rows.
- Sheet shared with steerave@gmail.com and mclaudy@gmail.com as editors.
- Dropdown validation: Category, Property (7 properties), Expense Type (24 categories).
- `verify` subcommand prints cell-by-cell comparison against filed 2024 XLSX.
- 130 tests passing, 0 failures.

### In Progress
- User review: tag ~878 vendor rows in the Google Sheet.

### Next
- After tagging: `taxauto review pull --year 2024` → `taxauto build --year 2024` → `taxauto verify --year 2024`
- Fill `interest_expense.yaml` with Form 1098 values.
- Run 2025 pipeline.

### Notes
- Review Sheet ID: `1l3pXIxVcb4NVjQO-oemSbnkkjU8JuJZF9Nz3BpDUgNM`
- Transaction-level overrides in the Transactions tab take precedence over vendor-level decisions.
- Service accounts on consumer Gmail can't create Drive files; the user pre-created the Sheet.

## 2026-04-05

### Done
- **Phase 2 complete** — full pipeline built and verified against real 2024 tax documents.
- 3 format-specific parsers: Chase Business Checking (12 statements, 861 txns), Chase Ink credit card (13 statements, 549 txns, 2 cardholders), Rent QC property manager (13 reports, 868 txns, 3 properties).
- All reconciliation guards passing (12 Chase checking + 13 Rent QC = 0 failures).
- eCheck double-count guard: 11 bank/PM collisions correctly identified and excluded.
- LTR pipeline verified: 59.5% of P&L cells within tolerance of filed 2024 values. Remaining deltas are accountant manual entries (Renovations) and timing differences.
- STR pipeline scaffolded (template + writer working), awaiting Google Sheets earnings data.
- 118 pytest tests passing, 0 failures.
- 68 vendors bootstrapped from Rent QC into vendor_mapping.yaml.
- Pushed to https://github.com/steerave/rental-tax-pipeline.

### In Progress
- Nothing — Phase 2 core complete.

### Next
- **User input needed:**
  1. STR Google Sheets earnings data (4 sheets, one per property) for STR revenue verification.
  2. `interest_expense.yaml` values from Form 1098 for all 7 properties.
  3. Review the Rent QC → LTR template category mapping (especially: is "Prepaid Rent" → "Sales revenue" correct, or should it be a separate line?).
- **Phase 3 backlog:**
  - Live Google Sheets reader (currently XLSX fixture only)
  - Bank/credit card categorization review workflow (1,410 transactions in the review queue)
  - Renovations / capital improvements manual override
  - STR expense property attribution (which STR property does each bank/CC charge belong to?)
  - 2025 tax year run

### Notes
- The 40.5% out-of-tolerance LTR cells are explained by: (a) Renovations — $25K manual entries with no Rent QC category, (b) Laundry/late-fee accountant manual adjustments, (c) small cross-year boundary timing differences.
- The pipeline correctly handles all 28 Rent QC categories, 3 LTR properties, the per-sheet row drift in the template, and the eCheck-reference-based double-count guard.
- Phase 2 discovery reports are at `years/2024/intermediate/discovery_*.md` for future reference.
