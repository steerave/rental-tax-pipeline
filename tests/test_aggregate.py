from decimal import Decimal

from taxauto.aggregate.by_property import aggregate_by_property


def test_sums_by_property_and_category() -> None:
    tagged = [
        {"property": "15 Belden", "template_category": "Utilities", "amount": Decimal("-100.00")},
        {"property": "15 Belden", "template_category": "Utilities", "amount": Decimal("-50.00")},
        {"property": "15 Belden", "template_category": "Cleaning Fees", "amount": Decimal("-200.00")},
        {"property": "27 Farmstead Dr", "template_category": "Utilities", "amount": Decimal("-80.00")},
    ]
    totals = aggregate_by_property(tagged)
    assert totals["15 Belden"]["Utilities"] == Decimal("150.00")
    assert totals["15 Belden"]["Cleaning Fees"] == Decimal("200.00")
    assert totals["27 Farmstead Dr"]["Utilities"] == Decimal("80.00")


def test_ignores_unmapped_items() -> None:
    tagged = [
        {"property": "15 Belden", "template_category": "", "amount": Decimal("-10.00")},
        {"property": "", "template_category": "Utilities", "amount": Decimal("-10.00")},
    ]
    totals = aggregate_by_property(tagged)
    assert totals == {}
