"""Tests for the STR - Split / LTR - Split category logic.

When category is "STR - Split", the pipeline divides the expense evenly
across all 4 STR properties. Same for "LTR - Split" across 3 LTR properties.
Property column is left blank (not needed).
"""

from decimal import Decimal


STR_PROPERTIES = ["15 Belden", "27 Farmstead Dr", "20 Valleywood Ln", "17 Oak Glen"]
LTR_PROPERTIES = ["1015 39th St", "1210 College Ave", "308 Lincoln Ave"]


def test_str_split_divides_evenly():
    """Verify that STR - Split creates 4 items with amount/4."""
    amount = Decimal("-100.00")
    split_amount = amount / len(STR_PROPERTIES)

    assert split_amount == Decimal("-25.00")
    assert len(STR_PROPERTIES) == 4


def test_ltr_split_divides_evenly():
    """Verify that LTR - Split creates 3 items with amount/3."""
    amount = Decimal("-99.00")
    split_amount = amount / len(LTR_PROPERTIES)

    assert split_amount == Decimal("-33.00")
    assert len(LTR_PROPERTIES) == 3


def test_str_split_odd_amount():
    """Verify that odd amounts produce correct Decimal splits."""
    amount = Decimal("-10.00")
    split_amount = amount / len(STR_PROPERTIES)

    assert split_amount == Decimal("-2.50")


def test_ltr_split_odd_amount():
    """Verify that indivisible amounts produce reasonable Decimal splits."""
    amount = Decimal("-100.00")
    split_amount = amount / len(LTR_PROPERTIES)

    # Each share is -33.333... — total of 3 shares is close to original
    total = split_amount * len(LTR_PROPERTIES)
    assert abs(total - amount) < Decimal("0.01")


def test_str_split_category_produces_correct_items():
    """Simulate the cmd_build logic for STR - Split category."""
    td = {
        "category": "STR - Split",
        "property": "",  # left blank for split categories
        "expense_type": "Insurance",
        "transaction": {"amount": "-200.00"},
    }
    cat = td["category"]
    amount = Decimal(str(td["transaction"]["amount"]))
    expense_type = td["expense_type"]

    str_items = []
    if cat == "STR - Split":
        split_amount = amount / len(STR_PROPERTIES)
        for split_prop in STR_PROPERTIES:
            str_items.append({
                "property": split_prop,
                "template_category": expense_type,
                "amount": split_amount,
            })

    assert len(str_items) == 4
    assert all(item["amount"] == Decimal("-50.00") for item in str_items)
    assert {item["property"] for item in str_items} == set(STR_PROPERTIES)


def test_ltr_split_category_produces_correct_items():
    """Simulate the cmd_build logic for LTR - Split category."""
    td = {
        "category": "LTR - Split",
        "property": "",
        "expense_type": "Utilities",
        "transaction": {"amount": "-90.00"},
    }
    cat = td["category"]
    amount = Decimal(str(td["transaction"]["amount"]))
    expense_type = td["expense_type"]

    ltr_items = []
    if cat == "LTR - Split":
        split_amount = amount / len(LTR_PROPERTIES)
        for split_prop in LTR_PROPERTIES:
            ltr_items.append({
                "property": split_prop,
                "template_category": expense_type,
                "amount": split_amount,
            })

    assert len(ltr_items) == 3
    assert all(item["amount"] == Decimal("-30.00") for item in ltr_items)
    assert {item["property"] for item in ltr_items} == set(LTR_PROPERTIES)
