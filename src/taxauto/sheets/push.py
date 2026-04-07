"""Push the review queue to a Google Sheet with vendor-grouped two-tab layout.

Tab 1 "Vendors": one row per unique vendor (~200 rows), sorted by frequency.
Tab 2 "Transactions": all transactions, grouped by vendor then date.

The user tags ~200 vendor rows; the pull step propagates those decisions
to all matching transactions.
"""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence

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


def _set_dropdown(spreadsheet: Any, worksheet: Any, col_index: int, num_rows: int, values: Sequence[str]) -> None:
    """Set dropdown validation using the raw Sheets API batch_update."""
    from taxauto.sheets.format_review import set_dropdown_validation

    try:
        set_dropdown_validation(spreadsheet, worksheet, col_index, num_rows, values)
    except Exception:
        pass  # best-effort — formatting script can always re-apply


def push_review_queue(
    spreadsheet: Any,
    *,
    tagged_transactions: Iterable[TaggedTransaction],
    categories: Sequence[str],
    properties: Sequence[str],
    expense_types: Sequence[str],
    year: int,
    prefills: Optional[Dict[int, Dict[str, str]]] = None,
    vendor_tab_name: str = "Vendors",
    txn_tab_name: str = "Transactions",
) -> Dict[str, int]:
    """Write vendor-grouped review queue to two tabs on the spreadsheet.

    If *prefills* is provided (keyed by review-queue index), matching
    transactions will have their Category / Property / Expense Type columns
    pre-populated from Margarete's expense worksheet.

    Tab names can be overridden to allow year-specific tabs (e.g.
    "Vendors 2025", "Transactions 2025") on a shared spreadsheet.

    Returns {"vendor_count": N, "txn_count": M, "prefilled": P}.
    """
    items = list(tagged_transactions)
    if not items:
        return {"vendor_count": 0, "txn_count": 0, "prefilled": 0}

    prefills = prefills or {}

    groups = group_by_vendor(items)

    # Build a mapping from each TaggedTransaction to its original review-queue
    # index so we can look up prefills after vendor grouping reorders them.
    # We use id() since the same TaggedTransaction object is in both lists.
    item_to_qi: Dict[int, int] = {id(tt): qi for qi, tt in enumerate(items)}

    # Compute per-vendor prefill consensus: if ALL transactions for a vendor
    # share the same prefill category/property/expense_type, apply it to the
    # vendor row too.
    vendor_prefills: Dict[str, Dict[str, str]] = {}
    for vendor_key, g in groups.items():
        vendor_cats = set()
        vendor_props = set()
        vendor_exps = set()
        has_prefill = False
        for tt in g["transactions"]:
            qi = item_to_qi.get(id(tt))
            if qi is not None and qi in prefills:
                pf = prefills[qi]
                vendor_cats.add(pf.get("category", ""))
                vendor_props.add(pf.get("property", ""))
                vendor_exps.add(pf.get("expense_type", ""))
                has_prefill = True
        if has_prefill and len(vendor_cats) == 1 and len(vendor_props) == 1 and len(vendor_exps) == 1:
            vendor_prefills[vendor_key] = {
                "category": vendor_cats.pop(),
                "property": vendor_props.pop(),
                "expense_type": vendor_exps.pop(),
            }

    # --- Vendors tab ---
    try:
        vendor_ws = spreadsheet.worksheet(vendor_tab_name)
        vendor_ws.clear()
    except Exception:
        vendor_ws = spreadsheet.add_worksheet(
            title=vendor_tab_name, rows=len(groups) + 10, cols=len(VENDOR_HEADERS)
        )

    vendor_rows: List[List[Any]] = [VENDOR_HEADERS]
    for vendor_key, g in groups.items():
        vpf = vendor_prefills.get(vendor_key, {})
        vendor_rows.append([
            g["vendor"],
            g["count"],
            float(g["total_amount"]),
            g["sample_description"],
            float(g["sample_amount"]),
            ", ".join(sorted(g["accounts"])),
            vpf.get("category", ""),
            vpf.get("property", ""),
            vpf.get("expense_type", ""),
            "",  # Notes
        ])

    try:
        vendor_ws.update("A1", vendor_rows)
    except Exception:
        for row in vendor_rows:
            vendor_ws.append_row(row)

    num_vendors = len(groups)
    _set_dropdown(spreadsheet, vendor_ws, 6, num_vendors, categories)
    _set_dropdown(spreadsheet, vendor_ws, 7, num_vendors, properties)
    _set_dropdown(spreadsheet, vendor_ws, 8, num_vendors, expense_types)

    # --- Transactions tab ---
    try:
        txn_ws = spreadsheet.worksheet(txn_tab_name)
        txn_ws.clear()
    except Exception:
        txn_ws = spreadsheet.add_worksheet(
            title=txn_tab_name, rows=len(items) + 10, cols=len(TXN_HEADERS)
        )

    txn_rows: List[List[Any]] = [TXN_HEADERS]
    prefilled_count = 0
    idx = 0
    for vendor_key, g in groups.items():
        for tt in sorted(g["transactions"], key=lambda t: t.transaction.date):
            txn = tt.transaction
            qi = item_to_qi.get(id(tt))
            pf = prefills.get(qi, {}) if qi is not None else {}
            if pf.get("category") or pf.get("property") or pf.get("expense_type"):
                prefilled_count += 1
            txn_rows.append([
                _row_id(year, idx),
                txn.date.isoformat(),
                vendor_key,
                txn.description,
                float(txn.amount),
                txn.account,
                pf.get("category", ""),
                pf.get("property", ""),
                pf.get("expense_type", ""),
                "",  # Notes
            ])
            idx += 1

    try:
        txn_ws.update("A1", txn_rows)
    except Exception:
        for row in txn_rows:
            txn_ws.append_row(row)

    _set_dropdown(spreadsheet, txn_ws, 6, len(items), categories)
    _set_dropdown(spreadsheet, txn_ws, 7, len(items), properties)
    _set_dropdown(spreadsheet, txn_ws, 8, len(items), expense_types)

    # Delete default "Sheet1" if it exists
    try:
        spreadsheet.del_worksheet(spreadsheet.worksheet("Sheet1"))
    except Exception:
        pass

    return {"vendor_count": len(groups), "txn_count": len(items), "prefilled": prefilled_count}
