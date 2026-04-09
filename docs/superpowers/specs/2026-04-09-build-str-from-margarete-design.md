# Design: `taxauto build-str` — Build 2025 STR Workbook from Margarete's Sheet

**Date:** 2026-04-09  
**Status:** Approved

## Background

For 2025, Margarete has completed a Google Sheet (`14l3vIA_t5RVRTZBeGQeAU0HIkT5W33YXQkD5eXtfQQo`, tab `2025 tax info`) that is the complete record of all STR expenses. It contains Date, Cost, Source, Description (free-form), and Type (property). This replaces the full extract → categorize → review → pull workflow for STR expenses in 2025.

LTR for 2025 is already complete and must not be touched.

## Goal

Add a new `taxauto build-str --year YYYY` CLI command that builds the STR Excel workbook directly from Margarete's sheet, bypassing all PDF parsing and review queue steps. The command is fully standalone — no dependency on intermediate JSON caches.

## Data Sources

| Source | What it provides | Existing code |
|---|---|---|
| Margarete's expense sheet | All STR expenses, per-property or split | `load_margarete_sheet()` in `margarete_sheet.py` |
| 4 STR earnings Google Sheets | Revenue per property (`Sales revenue`) | `load_str_earnings_from_gsheets()` in `str_sheets.py` |
| `interest_expense.yaml` | `Interest expense` per property | `load_interest_expense()` in `interest_expense.py` |

## Data Flow

```
Margarete's sheet
  └─ load_margarete_sheet()
  └─ For each row:
       • Parse Date, Cost (positive Decimal)
       • _map_property(Type) → (category, property)
           - category="Skip" (home office, etc.)  → discard row
           - category="STR - Split"               → divide Cost ÷ 4, emit 4 items (one per STR property)
           - category="STR"                        → emit 1 item for that property
       • _map_expense_type(Description)           → template_category
           - known description                    → exact template label (e.g. "Cleaning Fees")
           - unknown description                  → "other" + console warning

4 STR earnings sheets
  └─ load_str_earnings_from_gsheets()
  └─ total_net_payout_by_property()
  └─ Each property → item(template_category="Sales revenue", amount=net_payout)

interest_expense.yaml
  └─ load_interest_expense(year=YYYY)
  └─ Each property → item(template_category="Interest expense", amount=value)

All items → aggregate_by_property() → write_str_workbook()
```

## New Module

**`src/taxauto/sources/margarete_expenses.py`**

Single public function:

```python
def load_str_expenses_from_margarete(
    service_account_json: Path,
    year: int,
    sheet_id: str = "14l3vIA_t5RVRTZBeGQeAU0HIkT5W33YXQkD5eXtfQQo",
    tab_name: str = "2025 tax info",
) -> List[dict]:
    """Read Margarete's sheet and return aggregation-ready items.

    Each item has: {property, template_category, amount (positive Decimal)}
    STR-Split rows are expanded to 4 items (amount ÷ 4 each).
    Skip rows are discarded.
    Unknown descriptions map to "other" and emit a console warning.
    """
```

Reuses: `load_margarete_sheet()`, `_map_property()`, `_map_expense_type()` from `margarete_sheet.py`.

## CLI Addition

**In `cli.py`:** new `cmd_build_str(cfg, year)` function + `build-str` subcommand.

Steps:
1. Call `load_str_expenses_from_margarete(sa_path, year)` → expense items
2. Call `load_str_earnings_from_gsheets(...)` → revenue items (same as existing `cmd_build`)
3. Call `load_interest_expense(interest_path, year)` → interest items
4. Combine all items → `aggregate_by_property()`
5. Call `write_str_workbook(template_path, output_path, per_property_totals, year)`

Output path: `years/YYYY/outputs/YYYY - STR - Income Expense summary_generated.xlsx`

Template path: `cfg.template_str` (same config key used by existing `cmd_build`).

## Console Output

```
[build-str] loading expenses from Margarete's sheet...
[build-str]   493 rows read, 12 skipped (home office), 47 split rows expanded
[build-str] WARNING: unmapped description "service fee" → mapped to "other" (3 occurrences)
[build-str] loading STR earnings from 4 Google Sheets...
[build-str]   15 Belden: $XX,XXX.XX
[build-str]   27 Farmstead Dr: $XX,XXX.XX
[build-str]   20 Valleywood Ln: $XX,XXX.XX
[build-str]   17 Oak Glen: $XX,XXX.XX
[build-str] loading interest expense...
[build-str] writing STR workbook → years/2025/outputs/2025 - STR - Income Expense summary_generated.xlsx
[build-str] done.
```

## What is NOT changed

- `cmd_build` (LTR + full pipeline) — unchanged
- `margarete_sheet.py` — reused as-is, not modified
- Review workflow (push/pull) — unchanged

## Out of Scope

- `verify` support for this new command (can be added later if needed)
- Handling years other than 2025 (the sheet tab name is "2025 tax info"; future years may differ)
