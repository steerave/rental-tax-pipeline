"""Pull vendor-level and transaction-level review decisions from the Google Sheet."""

from __future__ import annotations

from typing import Any, Dict


def pull_review_decisions(
    spreadsheet: Any,
    *,
    year: int,
) -> Dict[str, Any]:
    """Read the Vendors and Transactions tabs and return structured decisions.

    Tries year-specific tab names first (e.g. "Vendors 2025"), then falls
    back to legacy names ("Vendors") for backward compatibility.

    Returns:
        {
            "vendor_decisions": {vendor_key: {category, property, expense_type, count, year}},
            "transaction_overrides": {row_id: {row_id, date, vendor, description, amount, category, property, expense_type, year}},
            "year": year,
        }
    """
    # Read Vendors tab — try year-specific name first
    try:
        vendor_ws = spreadsheet.worksheet(f"Vendors {year}")
    except Exception:
        vendor_ws = spreadsheet.worksheet("Vendors")
    vendor_rows = vendor_ws.get_all_records()

    vendor_decisions: Dict[str, Dict[str, Any]] = {}
    for row in vendor_rows:
        vendor = str(row.get("Vendor", "")).strip()
        category = str(row.get("Category", "")).strip()
        if not vendor or not category:
            continue
        vendor_decisions[vendor] = {
            "category": category,
            "property": str(row.get("Property", "")).strip(),
            "expense_type": str(row.get("Expense Type", "")).strip(),
            "count": row.get("Count", 0),
            "year": year,
        }

    # Read Transactions tab for overrides — try year-specific name first
    transaction_overrides: Dict[str, Dict[str, Any]] = {}
    try:
        try:
            txn_ws = spreadsheet.worksheet(f"Transactions {year}")
        except Exception:
            txn_ws = spreadsheet.worksheet("Transactions")
        txn_rows = txn_ws.get_all_records()
        for row in txn_rows:
            row_id = str(row.get("Row ID", "")).strip()
            category = str(row.get("Category", "")).strip()
            if not row_id or not category:
                continue
            transaction_overrides[row_id] = {
                "row_id": row_id,
                "date": str(row.get("Date", "")),
                "vendor": str(row.get("Vendor", "")),
                "description": str(row.get("Description", "")),
                "amount": str(row.get("Amount", "")),
                "category": category,
                "property": str(row.get("Property", "")).strip(),
                "expense_type": str(row.get("Expense Type", "")).strip(),
                "year": year,
            }
    except Exception:
        pass

    return {
        "vendor_decisions": vendor_decisions,
        "transaction_overrides": transaction_overrides,
        "year": year,
    }
