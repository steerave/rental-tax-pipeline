"""Tests for Google Sheet creation and sharing."""

from unittest.mock import MagicMock

from taxauto.sheets.create import create_and_share_sheet


def test_creates_sheet_with_correct_title() -> None:
    client = MagicMock()
    spreadsheet = MagicMock()
    client.create.return_value = spreadsheet
    spreadsheet.id = "SHEET_123"
    spreadsheet.url = "https://docs.google.com/spreadsheets/d/SHEET_123"

    result = create_and_share_sheet(
        client, title="rental-tax-review-2024", editor_emails=["user@example.com"],
    )

    client.create.assert_called_once_with("rental-tax-review-2024")
    assert result.id == "SHEET_123"


def test_shares_with_all_editor_emails() -> None:
    client = MagicMock()
    spreadsheet = MagicMock()
    client.create.return_value = spreadsheet
    spreadsheet.id = "SHEET_123"
    spreadsheet.url = "https://docs.google.com/spreadsheets/d/SHEET_123"

    create_and_share_sheet(
        client, title="review-2024",
        editor_emails=["a@example.com", "b@example.com"],
    )

    spreadsheet.share.assert_any_call("a@example.com", perm_type="user", role="writer")
    spreadsheet.share.assert_any_call("b@example.com", perm_type="user", role="writer")
