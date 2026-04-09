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
