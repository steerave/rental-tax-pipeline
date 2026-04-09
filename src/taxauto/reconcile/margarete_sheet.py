"""Reconcile review-queue transactions against Margarete's expense worksheet.

Reads the Google Sheet and matches transactions by date + amount, then maps
her property/expense labels to pipeline dropdown values.

The result is a dict keyed by (date_iso, amount_str) -> prefill info that the
push step uses to pre-populate Category / Property / Expense Type columns.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from taxauto.sheets.client import get_sheets_client


# ---------------------------------------------------------------------------
# Margarete's label -> pipeline dropdown mappings
# ---------------------------------------------------------------------------

_PROPERTY_MAP: Dict[str, str] = {
    "belden": "15 Belden",
    "valleywood": "20 Valleywood Ln",
    "oak glen": "17 Oak Glen",
    "farmstead": "27 Farmstead Dr",
}

_SKIP_TYPES = {"home office"}
_SPLIT_TYPES = {"short term rentals"}

_EXPENSE_TYPE_MAP: Dict[str, str] = {
    "cleaning fees": "Cleaning Fees",
    "cleaning": "Cleaning Fees",
    "utility": "Utilities",
    "utilities": "Utilities",
    "supplies": "Supplies",
    "insurance": "Insurance",
    "pest control": "Pest Control",
    "landscaping": "Landscaping",
    "lawn": "Landscaping",
    "advertising": "Advertising",
    "travel": "Travel",
    "repairs": "Repairs and Maintenance",
    "maintenance": "Repairs and Maintenance",
    "repair": "Repairs and Maintenance",
    "hoa": "HOA",
    "service": "Commissions/Service Fees",
    "renovation": "Renovations",
    "renovations": "Renovations",
}

# Ambiguous — leave blank for manual review
_AMBIGUOUS_EXPENSE: set = set()


def parse_margarete_date(raw: str) -> Optional[date]:
    """Parse M/D/YY or M/D/YYYY date strings."""
    raw = raw.strip()
    if not raw:
        return None
    parts = raw.split("/")
    if len(parts) != 3:
        return None
    try:
        m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
        if y < 100:
            y += 2000
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def parse_amount(raw: Any) -> Optional[Decimal]:
    """Parse amount from Margarete's sheet (may be int, float, or string)."""
    if raw is None or raw == "":
        return None
    try:
        s = str(raw).replace(",", "").replace("$", "").strip()
        return Decimal(s)
    except Exception:
        return None


def map_property(type_str: str) -> Tuple[Optional[str], Optional[str]]:
    """Map Margarete's Type column to (category, property).

    Returns (category, property) tuple.  category=None means use default STR.
    """
    key = type_str.strip().lower()
    if key in _SKIP_TYPES:
        return ("Skip", None)
    if key in _SPLIT_TYPES:
        return ("STR - Split", None)
    prop = _PROPERTY_MAP.get(key)
    if prop:
        return ("STR", prop)
    return (None, None)


def map_expense_type(desc_str: str) -> str:
    """Map Margarete's Description column to an Expense Type."""
    key = desc_str.strip().lower()
    if key in _AMBIGUOUS_EXPENSE:
        return ""
    # Try exact match first
    if key in _EXPENSE_TYPE_MAP:
        return _EXPENSE_TYPE_MAP[key]
    # Try substring match for compound descriptions
    for pattern, mapped in _EXPENSE_TYPE_MAP.items():
        if pattern in key:
            return mapped
    return ""


def _description_similarity(a: str, b: str) -> float:
    """Simple string similarity for tiebreaking duplicate date+amount matches."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def load_margarete_sheet(
    service_account_json: Path,
    sheet_id: str = "14l3vIA_t5RVRTZBeGQeAU0HIkT5W33YXQkD5eXtfQQo",
    tab_name: str = "2025 tax info",
) -> List[Dict[str, Any]]:
    """Fetch all rows from Margarete's expense worksheet."""
    client = get_sheets_client(service_account_json)
    spreadsheet = client.open_by_key(sheet_id)
    ws = spreadsheet.worksheet(tab_name)
    return ws.get_all_records()


def reconcile_against_margarete(
    review_queue: List[Dict[str, Any]],
    margarete_rows: List[Dict[str, Any]],
    amount_tolerance: Decimal = Decimal("0.50"),
) -> Dict[int, Dict[str, str]]:
    """Match review-queue items to Margarete's rows and return pre-fill data.

    Returns a dict of {review_queue_index: {category, property, expense_type}}.
    """
    # Build an index of Margarete rows by date for fast lookup
    marg_by_date: Dict[date, List[Tuple[int, Dict[str, Any]]]] = {}
    for i, row in enumerate(margarete_rows):
        d = parse_margarete_date(str(row.get("Date", "")))
        if d is None:
            continue
        amt = parse_amount(row.get("Cost"))
        if amt is None:
            continue
        marg_by_date.setdefault(d, []).append((i, row))

    # Track which Margarete rows have already been consumed (1:1 matching)
    used_marg: set = set()

    prefills: Dict[int, Dict[str, str]] = {}

    for qi, item in enumerate(review_queue):
        txn = item.get("transaction", {})
        txn_date_str = txn.get("date", "")
        try:
            txn_date = date.fromisoformat(txn_date_str)
        except (ValueError, TypeError):
            continue

        txn_amount = parse_amount(txn.get("amount"))
        if txn_amount is None:
            continue

        # Bank amounts are negative for expenses; Margarete's are positive
        abs_txn_amount = abs(txn_amount)
        txn_desc = txn.get("description", "")

        # Look for matches on the same date
        candidates = marg_by_date.get(txn_date, [])
        best_match = None
        best_similarity = -1.0

        for mi, mrow in candidates:
            if mi in used_marg:
                continue
            marg_amt = parse_amount(mrow.get("Cost"))
            if marg_amt is None:
                continue
            if abs(abs_txn_amount - marg_amt) > amount_tolerance:
                continue
            # Candidate match. Use description similarity as tiebreaker.
            marg_source = str(mrow.get("Source", ""))
            sim = _description_similarity(txn_desc, marg_source)
            if best_match is None or sim > best_similarity:
                best_match = (mi, mrow)
                best_similarity = sim

        if best_match is None:
            continue

        mi, mrow = best_match
        used_marg.add(mi)

        # Map her labels to our pipeline values
        type_str = str(mrow.get("Type", ""))
        desc_str = str(mrow.get("Description", ""))

        category, prop = map_property(type_str)
        expense_type = map_expense_type(desc_str)

        if category is None:
            # Unknown property type — still fill expense type if available
            category = ""

        prefills[qi] = {
            "category": category,
            "property": prop or "",
            "expense_type": expense_type,
            "margarete_source": str(mrow.get("Source", "")),
            "margarete_type": type_str,
            "margarete_desc": desc_str,
        }

    return prefills
