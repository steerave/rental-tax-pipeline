# build-str Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `taxauto build-str --year YYYY` CLI command that builds the STR Excel workbook directly from Margarete's Google Sheet, bypassing the PDF extract/categorize/review pipeline.

**Architecture:** A new source module `margarete_expenses.py` contains all conversion logic (sheet rows → aggregation items). The new `cmd_build_str` function in `cli.py` orchestrates loading expenses, revenue, and interest expense, then writes the workbook using the existing `write_str_workbook`. No existing code is modified except `cli.py` (command wiring only).

**Tech Stack:** Python 3.11+, gspread (Google Sheets API), openpyxl, existing taxauto modules.

---

## File Structure

| Action | Path | Responsibility |
|---|---|---|
| Create | `src/taxauto/sources/margarete_expenses.py` | Convert Margarete sheet rows to `{property, template_category, amount}` items |
| Create | `tests/test_margarete_expenses.py` | Unit tests for row conversion logic |
| Modify | `src/taxauto/cli.py` | Add `cmd_build_str()` function + `build-str` subcommand |

---

### Task 1: Write failing tests for `_rows_to_items`

**Files:**
- Create: `tests/test_margarete_expenses.py`

The function `_rows_to_items(rows, year)` is the pure conversion core. Tests call it directly, no mocking or API calls needed.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_margarete_expenses.py`:

```python
from decimal import Decimal

import pytest

from taxauto.sources.margarete_expenses import _rows_to_items

STR_PROPS = ["15 Belden", "27 Farmstead Dr", "20 Valleywood Ln", "17 Oak Glen"]


def test_single_property_row():
    rows = [{"Date": "3/15/2025", "Cost": "100.00", "Type": "belden", "Description": "cleaning fees", "Source": "Chase"}]
    items = _rows_to_items(rows, year=2025)
    assert len(items) == 1
    assert items[0]["property"] == "15 Belden"
    assert items[0]["template_category"] == "Cleaning Fees"
    assert items[0]["amount"] == Decimal("100.00")


def test_split_row_expands_to_four():
    rows = [{"Date": "6/1/2025", "Cost": "400.00", "Type": "short term rentals", "Description": "supplies", "Source": "Chase"}]
    items = _rows_to_items(rows, year=2025)
    assert len(items) == 4
    assert {i["property"] for i in items} == set(STR_PROPS)
    for item in items:
        assert item["template_category"] == "Supplies"
        assert item["amount"] == Decimal("100.00")


def test_home_office_is_skipped():
    rows = [{"Date": "1/10/2025", "Cost": "50.00", "Type": "home office", "Description": "supplies", "Source": "Chase"}]
    items = _rows_to_items(rows, year=2025)
    assert items == []


def test_unknown_property_type_is_skipped():
    rows = [{"Date": "2/5/2025", "Cost": "75.00", "Type": "vacation cabin", "Description": "cleaning", "Source": "Chase"}]
    items = _rows_to_items(rows, year=2025)
    assert items == []


def test_unknown_description_maps_to_other():
    rows = [{"Date": "4/20/2025", "Cost": "60.00", "Type": "farmstead", "Description": "mystery expense", "Source": "Chase"}]
    items = _rows_to_items(rows, year=2025)
    assert len(items) == 1
    assert items[0]["template_category"] == "other"
    assert items[0]["property"] == "27 Farmstead Dr"


def test_wrong_year_is_skipped():
    rows = [
        {"Date": "12/15/2024", "Cost": "200.00", "Type": "belden", "Description": "utilities", "Source": "Chase"},
        {"Date": "1/5/2025",  "Cost": "100.00", "Type": "belden", "Description": "utilities", "Source": "Chase"},
    ]
    items = _rows_to_items(rows, year=2025)
    assert len(items) == 1
    assert items[0]["amount"] == Decimal("100.00")


def test_blank_cost_is_skipped():
    rows = [{"Date": "5/1/2025", "Cost": "", "Type": "belden", "Description": "cleaning", "Source": "Chase"}]
    items = _rows_to_items(rows, year=2025)
    assert items == []


def test_missing_date_row_is_included():
    """Rows with no parseable date are not year-filtered — included as-is."""
    rows = [{"Date": "", "Cost": "90.00", "Type": "valleywood", "Description": "hoa", "Source": "Chase"}]
    items = _rows_to_items(rows, year=2025)
    assert len(items) == 1
    assert items[0]["template_category"] == "HOA"


def test_multiple_properties():
    rows = [
        {"Date": "3/1/2025", "Cost": "150.00", "Type": "oak glen",  "Description": "pest control", "Source": "CC"},
        {"Date": "3/2/2025", "Cost": "200.00", "Type": "farmstead", "Description": "insurance",    "Source": "CC"},
    ]
    items = _rows_to_items(rows, year=2025)
    assert len(items) == 2
    props = {i["property"] for i in items}
    assert props == {"17 Oak Glen", "27 Farmstead Dr"}
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/Scripts/python.exe -m pytest tests/test_margarete_expenses.py -v
```

Expected: `ModuleNotFoundError: No module named 'taxauto.sources.margarete_expenses'`

---

### Task 2: Implement `margarete_expenses.py`

**Files:**
- Create: `src/taxauto/sources/margarete_expenses.py`

- [ ] **Step 1: Create the module**

Create `src/taxauto/sources/margarete_expenses.py`:

```python
"""STR expense loader from Margarete's Google Sheet.

Reads her expense worksheet and converts each row to an aggregation-ready
item: {property, template_category, amount (positive Decimal)}.

STR-Split rows are expanded to 4 items (amount ÷ 4 each).
Home Office and unknown property types are discarded.
Unknown descriptions fall back to "other" with a console warning.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

from taxauto.reconcile.margarete_sheet import (
    _map_expense_type,
    _map_property,
    _parse_amount,
    _parse_margarete_date,
    load_margarete_sheet,
)

_STR_PROPERTIES = [
    "15 Belden",
    "27 Farmstead Dr",
    "20 Valleywood Ln",
    "17 Oak Glen",
]


def _rows_to_items(rows: List[Dict[str, Any]], year: int) -> List[dict]:
    """Convert Margarete sheet rows to aggregation-ready expense items.

    Each item: {property: str, template_category: str, amount: Decimal}
    Amounts are positive (costs ready for aggregate_by_property).
    """
    items: List[dict] = []
    skipped = 0
    split_count = 0
    unmapped: Counter = Counter()

    for row in rows:
        # Year filter — skip rows whose date is from a different year
        raw_date = str(row.get("Date", ""))
        parsed_date = _parse_margarete_date(raw_date)
        if parsed_date is not None and parsed_date.year != year:
            skipped += 1
            continue

        amount = _parse_amount(row.get("Cost"))
        if amount is None:
            continue

        type_str = str(row.get("Type", ""))
        category, prop = _map_property(type_str)

        if category in ("Skip", None):
            skipped += 1
            continue

        desc_str = str(row.get("Description", ""))
        expense_type = _map_expense_type(desc_str)
        if not expense_type:
            expense_type = "other"
            unmapped[desc_str] += 1

        if category == "STR - Split":
            split_amount = amount / len(_STR_PROPERTIES)
            split_count += 1
            for split_prop in _STR_PROPERTIES:
                items.append({
                    "property": split_prop,
                    "template_category": expense_type,
                    "amount": split_amount,
                })
        else:
            items.append({
                "property": prop,
                "template_category": expense_type,
                "amount": amount,
            })

    total = len(rows)
    print(
        f"[build-str]   {total} rows read, {skipped} skipped, "
        f"{split_count} split rows expanded"
    )
    for desc, count in sorted(unmapped.items()):
        plural = "s" if count > 1 else ""
        print(
            f'[build-str] WARNING: unmapped description {desc!r} → '
            f'"other" ({count} occurrence{plural})'
        )

    return items


def load_str_expenses_from_margarete(
    service_account_json: Path,
    year: int,
    sheet_id: str = "14l3vIA_t5RVRTZBeGQeAU0HIkT5W33YXQkD5eXtfQQo",
    tab_name: str = "2025 tax info",
) -> List[dict]:
    """Fetch Margarete's sheet and return aggregation-ready expense items.

    Each item: {property: str, template_category: str, amount: Decimal}
    """
    rows = load_margarete_sheet(service_account_json, sheet_id=sheet_id, tab_name=tab_name)
    return _rows_to_items(rows, year)
```

- [ ] **Step 2: Run tests to verify they pass**

```
.venv/Scripts/python.exe -m pytest tests/test_margarete_expenses.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 3: Run full test suite to verify nothing broke**

```
.venv/Scripts/python.exe -m pytest -q
```

Expected: all existing tests + 9 new tests pass, 0 failures

- [ ] **Step 4: Commit**

```bash
git add src/taxauto/sources/margarete_expenses.py tests/test_margarete_expenses.py
git commit -m "feat: add margarete_expenses source module — convert sheet rows to STR expense items"
```

---

### Task 3: Write failing CLI test for `build-str`

**Files:**
- Create: `tests/test_build_str_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_build_str_cli.py`:

```python
"""Tests for the build-str CLI subcommand wiring."""

import pytest
from unittest.mock import MagicMock, patch
from taxauto.cli import main


def test_build_str_subcommand_is_wired(tmp_path):
    """build-str subcommand dispatches to cmd_build_str."""
    config_yaml = tmp_path / "config.yaml"
    config_yaml.write_text(
        "templates:\n  str: ''\n  ltr: ''\n"
        "year_paths:\n"
        "  root: 'years/{year}'\n"
        "  bank_inputs: 'years/{year}/inputs'\n"
        "  pm_ltr_inputs: 'years/{year}/inputs'\n"
        "  pm_str_inputs: 'years/{year}/inputs'\n"
        "  intermediate: 'years/{year}/intermediate'\n"
        "  outputs: 'years/{year}/outputs'\n"
        "  review_log: 'years/{year}/review_log.json'\n",
        encoding="utf-8",
    )
    with patch("taxauto.cli.cmd_build_str", return_value=0) as mock_cmd:
        result = main(["--config", str(config_yaml), "build-str", "--year", "2025"])
    assert result == 0
    mock_cmd.assert_called_once()
    cfg_arg, year_arg = mock_cmd.call_args.args
    assert year_arg == 2025
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv/Scripts/python.exe -m pytest tests/test_build_str_cli.py -v
```

Expected: FAIL — `error: argument command: invalid choice: 'build-str'`

---

### Task 4: Add `cmd_build_str` to `cli.py` and wire the subcommand

**Files:**
- Modify: `src/taxauto/cli.py`

Two changes needed: (1) add `cmd_build_str` function after `cmd_build`, (2) add subcommand to parser + dispatch in `main`.

- [ ] **Step 1: Add `cmd_build_str` function**

In `src/taxauto/cli.py`, insert the following function after `cmd_build` (after line ~670, before the `def cmd_verify` line):

```python
def cmd_build_str(cfg: Config, year: int) -> int:
    """Build the STR workbook directly from Margarete's expense sheet."""
    from taxauto.aggregate.by_property import aggregate_by_property
    from taxauto.sources.interest_expense import load_interest_expense
    from taxauto.sources.margarete_expenses import load_str_expenses_from_margarete
    from taxauto.sources.str_sheets import (
        load_str_earnings_from_gsheets,
        load_str_earnings_from_xlsx,
        total_net_payout_by_property,
    )
    from taxauto.writers.str_writer import write_str_workbook

    paths = cfg.paths_for_year(year)

    if not cfg.google_service_account_json:
        print("[build-str] ERROR: GOOGLE_SERVICE_ACCOUNT_JSON not set in .env")
        return 1
    sa_path = Path(cfg.google_service_account_json)
    if not sa_path.exists():
        print(f"[build-str] ERROR: service account not found at {sa_path}")
        return 1

    # 1. Expenses from Margarete's sheet
    print("[build-str] loading expenses from Margarete's sheet...")
    str_items = load_str_expenses_from_margarete(sa_path, year=year)

    # 2. Revenue from STR earnings sheets
    str_sheet_configs = cfg.raw.get("str_sheets") or {}
    if str_sheet_configs:
        print(f"[build-str] loading STR earnings from {len(str_sheet_configs)} Google Sheets...")
        str_earnings = load_str_earnings_from_gsheets(
            str_sheet_configs,
            service_account_json=sa_path,
            year=year,
        )
        str_by_property = total_net_payout_by_property(str_earnings)
        for prop, total in sorted(str_by_property.items()):
            print(f"[build-str]   {prop}: ${total:,.2f}")
    else:
        str_xlsx_path = paths.inputs / "str_earnings.xlsx"
        if str_xlsx_path.exists():
            str_earnings = load_str_earnings_from_xlsx(str_xlsx_path)
            str_by_property = total_net_payout_by_property(str_earnings)
        else:
            str_by_property = {}

    for prop_name, net in str_by_property.items():
        str_items.append({
            "property": prop_name,
            "template_category": "Sales revenue",
            "amount": net,
        })

    # 3. Interest expense
    interest_path = cfg.project_root / "interest_expense.yaml"
    print("[build-str] loading interest expense...")
    interest_by_property = load_interest_expense(interest_path, year=year)
    for prop, amount in interest_by_property.items():
        str_items.append({
            "property": prop,
            "template_category": "Interest expense",
            "amount": amount,
        })

    # 4. Aggregate and write workbook
    str_totals = aggregate_by_property(str_items)
    paths.outputs.mkdir(parents=True, exist_ok=True)

    str_template = cfg.template_str
    if not str_template.exists():
        print(f"[build-str] ERROR: STR template not found at {str_template}")
        return 1

    str_out = paths.outputs / f"{year} - STR - Income Expense summary_generated.xlsx"
    print(f"[build-str] writing STR workbook → {str_out}")
    write_str_workbook(
        template_path=str_template,
        output_path=str_out,
        per_property_totals=str_totals,
        year=year,
    )
    print("[build-str] done.")
    return 0
```

- [ ] **Step 2: Register `build-str` in `_build_parser`**

In `_build_parser()`, find this block:

```python
    add_year(sub.add_parser("extract"))
    add_year(sub.add_parser("categorize"))
    add_year(sub.add_parser("build"))
    add_year(sub.add_parser("verify"))
    add_year(sub.add_parser("bootstrap"))
```

Replace with:

```python
    add_year(sub.add_parser("extract"))
    add_year(sub.add_parser("categorize"))
    add_year(sub.add_parser("build"))
    add_year(sub.add_parser("build-str"))
    add_year(sub.add_parser("verify"))
    add_year(sub.add_parser("bootstrap"))
```

- [ ] **Step 3: Dispatch `build-str` in `main`**

Find this block in `main()`:

```python
    if args.command == "build":
        return cmd_build(cfg, year)
    if args.command == "verify":
```

Replace with:

```python
    if args.command == "build":
        return cmd_build(cfg, year)
    if args.command == "build-str":
        return cmd_build_str(cfg, year)
    if args.command == "verify":
```

- [ ] **Step 4: Run CLI test to verify it passes**

```
.venv/Scripts/python.exe -m pytest tests/test_build_str_cli.py -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite**

```
.venv/Scripts/python.exe -m pytest -q
```

Expected: all tests pass, 0 failures

- [ ] **Step 6: Commit**

```bash
git add src/taxauto/cli.py tests/test_build_str_cli.py
git commit -m "feat: add build-str command — build STR workbook from Margarete's sheet"
```

---

### Task 5: Smoke test against live data

- [ ] **Step 1: Run the command**

```
.venv/Scripts/python.exe -m taxauto build-str --year 2025
```

Expected console output:
```
[build-str] loading expenses from Margarete's sheet...
[build-str]   493 rows read, N skipped, N split rows expanded
[build-str] WARNING: unmapped description '...' → "other" (N occurrences)   ← if any
[build-str] loading STR earnings from 4 Google Sheets...
[build-str]   15 Belden: $X,XXX.XX
[build-str]   17 Oak Glen: $X,XXX.XX
[build-str]   20 Valleywood Ln: $X,XXX.XX
[build-str]   27 Farmstead Dr: $X,XXX.XX
[build-str] loading interest expense...
[build-str] writing STR workbook → years/2025/outputs/2025 - STR - Income Expense summary_generated.xlsx
[build-str] done.
```

- [ ] **Step 2: Open the generated workbook and sanity-check**

Open `years/2025/outputs/2025 - STR - Income Expense summary_generated.xlsx`. Verify:
- Each property tab has revenue in D5 (Sales revenue)
- Expense rows are populated with reasonable amounts
- No obvious zeros where there should be values
- Any WARNING descriptions in the console — review whether they need to be added to `_EXPENSE_TYPE_MAP` in `margarete_sheet.py`

- [ ] **Step 3: If unmapped descriptions need fixing**

For each WARNING, add the mapping to `_EXPENSE_TYPE_MAP` in `src/taxauto/reconcile/margarete_sheet.py`. Example — if "renovation" appears unmapped:

```python
# In _EXPENSE_TYPE_MAP in margarete_sheet.py:
"renovation": "Renovations",
"renovations": "Renovations",
```

Then re-run `taxauto build-str --year 2025` until no WARNINGs remain (or only truly ambiguous ones are left in "other").

- [ ] **Step 4: Commit final mapping fixes (if any)**

```bash
git add src/taxauto/reconcile/margarete_sheet.py
git commit -m "fix: add missing expense type mappings from 2025 Margarete sheet"
```

- [ ] **Step 5: Push**

```bash
git push
```
