"""Tests for the vendor-aware review pull."""

from unittest.mock import MagicMock

from taxauto.sheets.pull import pull_review_decisions


def _mock_spreadsheet(vendor_rows, txn_rows):
    vendor_ws = MagicMock()
    vendor_ws.get_all_records.return_value = vendor_rows
    txn_ws = MagicMock()
    txn_ws.get_all_records.return_value = txn_rows
    spreadsheet = MagicMock()
    def ws_by_name(name):
        if name == "Vendors": return vendor_ws
        if name == "Transactions": return txn_ws
        raise Exception(f"No sheet {name}")
    spreadsheet.worksheet.side_effect = ws_by_name
    return spreadsheet


def test_pull_reads_vendor_decisions() -> None:
    vendor_rows = [
        {"Vendor": "mediacom", "Count": 52, "Category": "STR",
         "Property": "15 Belden", "Expense Type": "Utilities"},
        {"Vendor": "hy-vee", "Count": 30, "Category": "Personal",
         "Property": "", "Expense Type": ""},
    ]
    spreadsheet = _mock_spreadsheet(vendor_rows, [])
    decisions = pull_review_decisions(spreadsheet, year=2024)

    assert len(decisions["vendor_decisions"]) == 2
    assert decisions["vendor_decisions"]["mediacom"]["category"] == "STR"
    assert decisions["vendor_decisions"]["mediacom"]["property"] == "15 Belden"
    assert decisions["vendor_decisions"]["mediacom"]["expense_type"] == "Utilities"


def test_pull_reads_transaction_overrides() -> None:
    vendor_rows = [
        {"Vendor": "printify", "Count": 143, "Category": "STR",
         "Property": "15 Belden", "Expense Type": "Supplies"},
    ]
    txn_rows = [
        {"Row ID": "2024-0005", "Vendor": "printify", "Date": "2024-03-10",
         "Description": "PRINTIFY ORDER #99", "Amount": "-25.00",
         "Category": "STR", "Property": "27 Farmstead Dr", "Expense Type": "Supplies"},
    ]
    spreadsheet = _mock_spreadsheet(vendor_rows, txn_rows)
    decisions = pull_review_decisions(spreadsheet, year=2024)

    assert len(decisions["transaction_overrides"]) == 1
    assert decisions["transaction_overrides"]["2024-0005"]["property"] == "27 Farmstead Dr"


def test_pull_skips_untagged_vendors() -> None:
    vendor_rows = [
        {"Vendor": "mediacom", "Count": 52, "Category": "STR",
         "Property": "15 Belden", "Expense Type": "Utilities"},
        {"Vendor": "unknown co", "Count": 1, "Category": "",
         "Property": "", "Expense Type": ""},
    ]
    spreadsheet = _mock_spreadsheet(vendor_rows, [])
    decisions = pull_review_decisions(spreadsheet, year=2024)
    assert len(decisions["vendor_decisions"]) == 1
