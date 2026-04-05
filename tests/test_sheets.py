"""Tests for the Google Sheets review roundtrip.

gspread is fully mocked — these tests verify our push/pull logic without
touching the network.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from taxauto.categorize.mapper import TaggedTransaction
from taxauto.parsers.bank import Transaction
from taxauto.sheets.pull import pull_review_decisions
from taxauto.sheets.push import push_review_queue


def _tagged(description: str, source: str = "unknown") -> TaggedTransaction:
    return TaggedTransaction(
        transaction=Transaction(
            date=date(2025, 3, 10),
            description=description,
            amount=Decimal("-123.45"),
            balance=None,
            account="****1234",
        ),
        category="",
        confidence=0.0,
        source=source,
    )


# --- push -----------------------------------------------------------------


def test_push_writes_header_and_rows_and_returns_row_ids() -> None:
    # Mock gspread client → spreadsheet → worksheet
    worksheet = MagicMock()
    spreadsheet = MagicMock()
    spreadsheet.worksheet.return_value = worksheet
    # Simulate "worksheet not found" first so the code creates it
    spreadsheet.add_worksheet.return_value = worksheet
    client = MagicMock()
    client.open_by_key.return_value = spreadsheet

    tagged = [_tagged("HOME DEPOT #123"), _tagged("AMAZON.COM*A1")]
    categories = ["STR", "LTR", "Personal", "Skip", "Split"]

    row_ids = push_review_queue(
        client,
        sheet_id="SHEET_ID",
        tagged_transactions=tagged,
        categories=categories,
        year=2025,
    )

    # We expect one row ID per pushed transaction.
    assert len(row_ids) == 2
    assert all(isinstance(r, str) and r for r in row_ids)

    # update or append_rows should have been called with header + data rows.
    # Accept either pattern; just check one of them fired.
    assert worksheet.update.called or worksheet.append_rows.called or worksheet.append_row.called


def test_push_empty_queue_is_noop() -> None:
    client = MagicMock()
    row_ids = push_review_queue(
        client,
        sheet_id="SHEET_ID",
        tagged_transactions=[],
        categories=["STR", "LTR", "Personal"],
        year=2025,
    )
    assert row_ids == []
    client.open_by_key.assert_not_called()


# --- pull -----------------------------------------------------------------


def test_pull_parses_tagged_rows() -> None:
    # Simulate worksheet.get_all_records() output.
    fake_rows = [
        {
            "row_id": "2025-0001",
            "date": "2025-03-10",
            "description": "HOME DEPOT #123",
            "amount": "-123.45",
            "account": "****1234",
            "category": "STR",
        },
        {
            "row_id": "2025-0002",
            "date": "2025-03-10",
            "description": "AMAZON.COM",
            "amount": "-99.99",
            "account": "****1234",
            "category": "Personal",
        },
        {
            "row_id": "2025-0003",
            "date": "2025-03-10",
            "description": "UNTAGGED ROW",
            "amount": "-10.00",
            "account": "****1234",
            "category": "",  # not yet reviewed
        },
    ]
    worksheet = MagicMock()
    worksheet.get_all_records.return_value = fake_rows
    spreadsheet = MagicMock()
    spreadsheet.worksheet.return_value = worksheet
    client = MagicMock()
    client.open_by_key.return_value = spreadsheet

    decisions = pull_review_decisions(client, sheet_id="SHEET_ID", year=2025)

    # Only tagged rows return.
    assert len(decisions) == 2
    assert decisions[0]["category"] == "STR"
    assert decisions[0]["description"] == "HOME DEPOT #123"
    assert decisions[0]["year"] == 2025
    assert decisions[1]["category"] == "Personal"


def test_pull_raises_if_rows_missing_required_columns() -> None:
    worksheet = MagicMock()
    worksheet.get_all_records.return_value = [{"foo": "bar"}]
    spreadsheet = MagicMock()
    spreadsheet.worksheet.return_value = worksheet
    client = MagicMock()
    client.open_by_key.return_value = spreadsheet

    import pytest

    with pytest.raises(ValueError):
        pull_review_decisions(client, sheet_id="SHEET_ID", year=2025)
