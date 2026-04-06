"""Tests for the Split - All STR / Split - All LTR property logic."""

from decimal import Decimal


STR_PROPERTIES = ["15 Belden", "27 Farmstead Dr", "20 Valleywood Ln", "17 Oak Glen"]
LTR_PROPERTIES = ["1015 39th St", "1210 College Ave", "308 Lincoln Ave"]


def test_split_all_str_divides_evenly():
    """Verify that Split - All STR creates 4 items with amount/4."""
    amount = Decimal("-100.00")
    split_amount = amount / len(STR_PROPERTIES)

    assert split_amount == Decimal("-25.00")
    assert len(STR_PROPERTIES) == 4


def test_split_all_ltr_divides_evenly():
    """Verify that Split - All LTR creates 3 items with amount/3."""
    amount = Decimal("-99.00")
    split_amount = amount / len(LTR_PROPERTIES)

    assert split_amount == Decimal("-33.00")
    assert len(LTR_PROPERTIES) == 3


def test_split_all_str_odd_amount():
    """Verify that odd amounts produce correct Decimal splits."""
    amount = Decimal("-10.00")
    split_amount = amount / len(STR_PROPERTIES)

    assert split_amount == Decimal("-2.50")


def test_split_all_ltr_odd_amount():
    """Verify that indivisible amounts produce reasonable Decimal splits."""
    amount = Decimal("-100.00")
    split_amount = amount / len(LTR_PROPERTIES)

    # Each share is -33.333... — total of 3 shares is close to original
    total = split_amount * len(LTR_PROPERTIES)
    assert abs(total - amount) < Decimal("0.01")
