"""Push the review queue to a Google Sheet with vendor-grouped two-tab layout.

Tab 1 "Vendors": one row per unique vendor (~200 rows), sorted by frequency.
Tab 2 "Transactions": all transactions, grouped by vendor then date.

The user tags ~200 vendor rows; the pull step propagates those decisions
to all matching transactions.
"""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Sequence

from taxauto.categorize.mapper import TaggedTransaction, normalize_vendor


VENDOR_HEADERS = [
    "Vendor", "Count", "Total Amount", "Sample Description",
    "Sample Amount", "Accounts", "Category", "Property", "Expense Type", "Notes",
]

TXN_HEADERS = [
    "Row ID", "Date", "Vendor", "Description", "Amount",
    "Account", "Category", "Property", "Expense Type", "Notes",
]


def group_by_vendor(
    tagged_transactions: Iterable[TaggedTransaction],
) -> Dict[str, Dict[str, Any]]:
    """Group transactions by normalized vendor key.

    Returns an OrderedDict sorted by count descending.
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for tt in tagged_transactions:
        key = normalize_vendor(tt.transaction.description)
        if not key:
            key = "(unknown)"
        if key not in groups:
            groups[key] = {
                "vendor": key,
                "count": 0,
                "total_amount": Decimal("0"),
                "sample_description": tt.transaction.description,
                "sample_amount": tt.transaction.amount,
                "accounts": set(),
                "transactions": [],
            }
        g = groups[key]
        g["count"] += 1
        g["total_amount"] += abs(tt.transaction.amount)
        g["accounts"].add(tt.transaction.account)
        g["transactions"].append(tt)

    return OrderedDict(
        sorted(groups.items(), key=lambda kv: kv[1]["count"], reverse=True)
    )


def _row_id(year: int, index: int) -> str:
    return f"{year}-{index + 1:04d}"


def _try_set_dropdown(worksheet: Any, col_letter: str, num_rows: int, values: Sequence[str]) -> None:
    """Best-effort dropdown validation."""
    try:
        add_validation = getattr(worksheet, "add_validation", None)
        if callable(add_validation):
            range_str = f"{col_letter}2:{col_letter}{num_rows + 1}"
            add_validation(range_str, "ONE_OF_LIST", list(values))
    except Exception:
        pass


def push_review_queue(
    spreadsheet: Any,
    *,
    tagged_transactions: Iterable[TaggedTransaction],
    categories: Sequence[str],
    properties: Sequence[str],
    expense_types: Sequence[str],
    year: int,
) -> Dict[str, int]:
    """Write vendor-grouped review queue to two tabs on the spreadsheet.

    Returns {"vendor_count": N, "txn_count": M}.
    """
    items = list(tagged_transactions)
    if not items:
        return {"vendor_count": 0, "txn_count": 0}

    groups = group_by_vendor(items)

    # --- Vendors tab ---
    try:
        vendor_ws = spreadsheet.worksheet("Vendors")
        vendor_ws.clear()
    except Exception:
        vendor_ws = spreadsheet.add_worksheet(
            title="Vendors", rows=len(groups) + 10, cols=len(VENDOR_HEADERS)
        )

    vendor_rows: List[List[Any]] = [VENDOR_HEADERS]
    for vendor_key, g in groups.items():
        vendor_rows.append([
            g["vendor"],
            g["count"],
            float(g["total_amount"]),
            g["sample_description"],
            float(g["sample_amount"]),
            ", ".join(sorted(g["accounts"])),
            "",  # Category
            "",  # Property
            "",  # Expense Type
            "",  # Notes
        ])

    try:
        vendor_ws.update("A1", vendor_rows)
    except Exception:
        for row in vendor_rows:
            vendor_ws.append_row(row)

    num_vendors = len(groups)
    _try_set_dropdown(vendor_ws, "G", num_vendors, categories)
    _try_set_dropdown(vendor_ws, "H", num_vendors, properties)
    _try_set_dropdown(vendor_ws, "I", num_vendors, expense_types)

    # --- Transactions tab ---
    try:
        txn_ws = spreadsheet.worksheet("Transactions")
        txn_ws.clear()
    except Exception:
        txn_ws = spreadsheet.add_worksheet(
            title="Transactions", rows=len(items) + 10, cols=len(TXN_HEADERS)
        )

    txn_rows: List[List[Any]] = [TXN_HEADERS]
    idx = 0
    for vendor_key, g in groups.items():
        for tt in sorted(g["transactions"], key=lambda t: t.transaction.date):
            txn = tt.transaction
            txn_rows.append([
                _row_id(year, idx),
                txn.date.isoformat(),
                vendor_key,
                txn.description,
                float(txn.amount),
                txn.account,
                "",  # Category
                "",  # Property
                "",  # Expense Type
                "",  # Notes
            ])
            idx += 1

    try:
        txn_ws.update("A1", txn_rows)
    except Exception:
        for row in txn_rows:
            txn_ws.append_row(row)

    _try_set_dropdown(txn_ws, "G", len(items), categories)
    _try_set_dropdown(txn_ws, "H", len(items), properties)
    _try_set_dropdown(txn_ws, "I", len(items), expense_types)

    # Delete default "Sheet1" if it exists
    try:
        spreadsheet.del_worksheet(spreadsheet.worksheet("Sheet1"))
    except Exception:
        pass

    return {"vendor_count": len(groups), "txn_count": len(items)}
