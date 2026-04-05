"""Aggregate tagged items by (property, template_category).

The aggregator takes a flat list of categorized items — from bank/credit
transactions, Rent QC entries, and STR earnings — and produces per-property
totals ready for the Excel writers.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable

PropertyTotals = Dict[str, Dict[str, Decimal]]


def aggregate_by_property(items: Iterable[dict]) -> PropertyTotals:
    """Sum amounts by (property, template_category).

    Expense amounts are accepted as negative (matching bank convention) and
    flipped to positive for display in the accountant template. Revenue
    amounts are accepted as positive and stored as positive.
    """
    totals: PropertyTotals = {}
    for item in items:
        prop = item.get("property")
        cat = item.get("template_category")
        amount = item.get("amount")
        if not prop or not cat or amount is None:
            continue
        display_amount = -amount if amount < 0 else amount
        totals.setdefault(prop, {}).setdefault(cat, Decimal("0"))
        totals[prop][cat] += display_amount
    return totals
