"""Push the review queue to a Google Sheet.

The queue is written to a worksheet named ``review_{year}``. Each row gets a
deterministic ``row_id`` so the subsequent pull can match decisions back to
their source transactions.

Dropdown validation for the ``category`` column is attempted via
``worksheet.add_validation`` (newer gspread) but silently skipped if that API
is unavailable — the sheet still functions, it just lacks the dropdown UI.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Sequence

from taxauto.categorize.mapper import TaggedTransaction


HEADERS = ["row_id", "date", "description", "amount", "account", "source_hint", "category"]


def _row_id(year: int, index: int) -> str:
    return f"{year}-{index + 1:04d}"


def _get_or_create_worksheet(spreadsheet: Any, title: str) -> Any:
    try:
        return spreadsheet.worksheet(title)
    except Exception:
        # gspread raises WorksheetNotFound, but we catch broadly so MagicMocks
        # in tests don't need to simulate the exact exception type.
        return spreadsheet.add_worksheet(title=title, rows=1000, cols=len(HEADERS))


def push_review_queue(
    client: Any,
    *,
    sheet_id: str,
    tagged_transactions: Iterable[TaggedTransaction],
    categories: Sequence[str],
    year: int,
) -> List[str]:
    """Write the review queue to the Sheet and return the list of row IDs."""
    items = list(tagged_transactions)
    if not items:
        return []

    spreadsheet = client.open_by_key(sheet_id)
    worksheet = _get_or_create_worksheet(spreadsheet, f"review_{year}")

    rows: List[List[Any]] = [list(HEADERS)]
    row_ids: List[str] = []
    for i, tt in enumerate(items):
        rid = _row_id(year, i)
        row_ids.append(rid)
        txn = tt.transaction
        rows.append(
            [
                rid,
                txn.date.isoformat(),
                txn.description,
                str(txn.amount),
                txn.account,
                tt.source,  # "unknown" or "ambiguous"
                "",  # category — bookkeeper fills this in
            ]
        )

    # Single batch write. Uses A1 range starting at A1.
    try:
        worksheet.update("A1", rows)
    except Exception:
        # Fallback path for older gspread or odd mocks.
        worksheet.clear()
        for row in rows:
            worksheet.append_row(row)

    # Optional: add dropdown validation for the category column. Best-effort.
    try:
        category_col = HEADERS.index("category") + 1
        worksheet.set_basic_filter()  # no-op on failure
        # Newer gspread: worksheet.add_validation (if available on the build)
        add_validation = getattr(worksheet, "add_validation", None)
        if callable(add_validation):
            add_validation(
                f"{chr(64 + category_col)}2:{chr(64 + category_col)}{len(rows)}",
                "ONE_OF_LIST",
                list(categories),
            )
    except Exception:
        pass

    return row_ids
