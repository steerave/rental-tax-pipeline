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


def test_home_office_splits_as_other():
    rows = [{"Date": "1/10/2025", "Cost": "80.00", "Type": "home office", "Description": "supplies", "Source": "Chase"}]
    items = _rows_to_items(rows, year=2025)
    assert len(items) == 4
    assert {i["property"] for i in items} == set(STR_PROPS)
    for item in items:
        assert item["template_category"] == "other"
        assert item["amount"] == Decimal("20.00")


def test_storefront_splits_as_advertising():
    rows = [{"Date": "3/5/2025", "Cost": "400.00", "Type": "storefront", "Description": "service", "Source": "Chase"}]
    items = _rows_to_items(rows, year=2025)
    assert len(items) == 4
    assert {i["property"] for i in items} == set(STR_PROPS)
    for item in items:
        assert item["template_category"] == "Advertising"
        assert item["amount"] == Decimal("100.00")


def test_transportation_splits_as_travel():
    rows = [{"Date": "7/4/2025", "Cost": "120.00", "Type": "transportation", "Description": "gas", "Source": "Chase"}]
    items = _rows_to_items(rows, year=2025)
    assert len(items) == 4
    for item in items:
        assert item["template_category"] == "Travel"
        assert item["amount"] == Decimal("30.00")


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
