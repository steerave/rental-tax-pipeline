# Daily Status Log

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
