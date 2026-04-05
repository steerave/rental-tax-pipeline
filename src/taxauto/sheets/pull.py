"""Pull tagged review decisions from the Google Sheet."""

from __future__ import annotations

from typing import Any, Dict, List


REQUIRED_COLUMNS = {"row_id", "date", "description", "amount", "category"}


def pull_review_decisions(
    client: Any,
    *,
    sheet_id: str,
    year: int,
) -> List[Dict[str, Any]]:
    """Return a list of decision dicts for rows where ``category`` is filled in.

    Each decision dict matches the format consumed by
    ``taxauto.categorize.learning.record_review_decisions``:

        {"row_id", "description", "category", "amount", "date", "year"}
    """
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.worksheet(f"review_{year}")
    rows = worksheet.get_all_records()

    if rows:
        missing = REQUIRED_COLUMNS - set(rows[0].keys())
        if missing:
            raise ValueError(
                f"review sheet for year {year} is missing required columns: {sorted(missing)}"
            )

    decisions: List[Dict[str, Any]] = []
    for row in rows:
        category = str(row.get("category") or "").strip()
        if not category:
            continue
        decisions.append(
            {
                "row_id": row.get("row_id"),
                "description": row.get("description", ""),
                "amount": str(row.get("amount", "")),
                "date": row.get("date", ""),
                "category": category,
                "year": year,
            }
        )

    return decisions
