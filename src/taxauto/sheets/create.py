"""Create and share a Google Sheet for the review workflow."""

from __future__ import annotations

from typing import Any, Optional, Sequence


def create_and_share_sheet(
    client: Any,
    *,
    title: str,
    editor_emails: Sequence[str],
    existing_sheet_id: Optional[str] = None,
) -> Any:
    """Create a new Google Sheet (or reuse an existing one) and share with editors.

    If *existing_sheet_id* is provided, opens that spreadsheet instead of
    creating a new one.  This is necessary when the service account has zero
    Drive storage quota (common on free GCP projects).

    Returns the gspread Spreadsheet object.
    """
    if existing_sheet_id:
        spreadsheet = client.open_by_key(existing_sheet_id)
        # Rename to the expected title
        try:
            spreadsheet.update_title(title)
        except Exception:
            pass  # title update is best-effort
    else:
        spreadsheet = client.create(title)
        for email in editor_emails:
            spreadsheet.share(email, perm_type="user", role="writer")
    return spreadsheet
