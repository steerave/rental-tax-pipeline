"""Tests for the vendor-grouped review push."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from taxauto.categorize.mapper import TaggedTransaction
from taxauto.parsers.bank import Transaction
from taxauto.sheets.push import group_by_vendor, push_review_queue


def _tagged(description: str, amount: str = "-50.00", account: str = "CHK") -> TaggedTransaction:
    return TaggedTransaction(
        transaction=Transaction(
            date=date(2024, 3, 10), description=description,
            amount=Decimal(amount), balance=None, account=account,
        ),
        category="", confidence=0.0, source="unknown",
    )


def test_group_by_vendor_aggregates_correctly() -> None:
    items = [
        _tagged("POS PURCHASE HOME DEPOT #123", "-50.00"),
        _tagged("POS PURCHASE HOME DEPOT #456", "-75.00"),
        _tagged("AMAZON.COM*AB12C", "-30.00"),
    ]
    groups = group_by_vendor(items)
    hd_key = next(k for k in groups if "home depot" in k)
    assert groups[hd_key]["count"] == 2
    assert len(groups[hd_key]["transactions"]) == 2
    amz_key = next(k for k in groups if "amazon" in k)
    assert groups[amz_key]["count"] == 1


def test_group_by_vendor_sums_absolute_amounts() -> None:
    items = [_tagged("MEDIACOM", "-100.00"), _tagged("MEDIACOM", "-50.00")]
    groups = group_by_vendor(items)
    key = next(iter(groups))
    assert groups[key]["total_amount"] == Decimal("150.00")


def test_group_sorted_by_count_descending() -> None:
    items = [
        _tagged("RARE VENDOR", "-10.00"),
        _tagged("FREQUENT VENDOR", "-20.00"),
        _tagged("FREQUENT VENDOR", "-30.00"),
        _tagged("FREQUENT VENDOR", "-40.00"),
    ]
    groups = group_by_vendor(items)
    keys = list(groups.keys())
    assert groups[keys[0]]["count"] > groups[keys[1]]["count"]


def test_push_creates_two_tabs() -> None:
    spreadsheet = MagicMock()
    vendor_ws = MagicMock()
    txn_ws = MagicMock()
    spreadsheet.add_worksheet.side_effect = [vendor_ws, txn_ws]
    spreadsheet.worksheet.side_effect = Exception("not found")

    items = [_tagged("MEDIACOM", "-100.00")]
    push_review_queue(
        spreadsheet, tagged_transactions=items,
        categories=["STR", "LTR"], properties=["15 Belden"],
        expense_types=["Utilities"], year=2024,
    )

    assert spreadsheet.add_worksheet.call_count == 2
    assert vendor_ws.update.called or vendor_ws.append_row.called
    assert txn_ws.update.called or txn_ws.append_row.called


def test_push_returns_counts() -> None:
    spreadsheet = MagicMock()
    spreadsheet.add_worksheet.return_value = MagicMock()
    spreadsheet.worksheet.side_effect = Exception("not found")

    items = [_tagged("MEDIACOM", "-100.00"), _tagged("MEDIACOM", "-50.00"), _tagged("HOME DEPOT", "-75.00")]
    result = push_review_queue(
        spreadsheet, tagged_transactions=items,
        categories=["STR"], properties=["15 Belden"],
        expense_types=["Utilities"], year=2024,
    )
    assert result["vendor_count"] == 2
    assert result["txn_count"] == 3


def test_push_empty_queue() -> None:
    spreadsheet = MagicMock()
    result = push_review_queue(
        spreadsheet, tagged_transactions=[],
        categories=["STR"], properties=[], expense_types=[], year=2024,
    )
    assert result["vendor_count"] == 0
    assert result["txn_count"] == 0
