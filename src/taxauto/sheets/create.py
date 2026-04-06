"""Create and share a Google Sheet for the review workflow."""

from __future__ import annotations

from typing import Any, Sequence


def create_and_share_sheet(
    client: Any,
    *,
    title: str,
    editor_emails: Sequence[str],
) -> Any:
    """Create a new Google Sheet and share with editors.

    Returns the gspread Spreadsheet object.
    """
    spreadsheet = client.create(title)
    for email in editor_emails:
        spreadsheet.share(email, perm_type="user", role="writer")
    return spreadsheet
