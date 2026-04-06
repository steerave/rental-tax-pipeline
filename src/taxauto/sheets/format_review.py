"""Apply dropdown validation and visual formatting to the review Sheet.

Run standalone:
    python -m taxauto.sheets.format_review

Uses raw Google Sheets API via gspread's batch_update — no extra packages.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SHEET_ID = "1l3pXIxVcb4NVjQO-oemSbnkkjU8JuJZF9Nz3BpDUgNM"
SERVICE_ACCOUNT = Path(
    r"C:\Users\steerave\Desktop\Claude Projects\Job Search Tool\service_account.json"
)

CATEGORIES = ["STR", "LTR", "Personal", "Skip", "Split"]
PROPERTIES = [
    "15 Belden",
    "27 Farmstead Dr",
    "20 Valleywood Ln",
    "17 Oak Glen",
    "1015 39th St",
    "1210 College Ave",
    "308 Lincoln Ave",
]
EXPENSE_TYPES = [
    "Advertising",
    "Appliances",
    "Bank Charges",
    "Cleaning Fees",
    "Commissions/Service Fees",
    "Furniture and equipment",
    "Insurance",
    "Interest expense",
    "Landscaping",
    "Lawn and Snow Care",
    "Licenses and Fees",
    "Management Fees",
    "Pest Control",
    "Plumbing",
    "Postages",
    "Rent Expense",
    "Renovations",
    "Repairs and Maintenance",
    "legal expenses",
    "Supplies",
    "Travel",
    "Utilities",
    "HOA",
    "other",
]

# Column widths: (column_index, pixel_width)
VENDOR_COL_WIDTHS = [
    (0, 250),   # Vendor
    (1, 60),    # Count
    (2, 100),   # Total Amount
    (3, 300),   # Sample Description
    (4, 100),   # Sample Amount
    (5, 120),   # Accounts
    (6, 80),    # Category
    (7, 150),   # Property
    (8, 160),   # Expense Type
    (9, 200),   # Notes
]

TXN_COL_WIDTHS = [
    (0, 90),    # Row ID
    (1, 90),    # Date
    (2, 200),   # Vendor
    (3, 350),   # Description
    (4, 100),   # Amount
    (5, 200),   # Account
    (6, 80),    # Category
    (7, 150),   # Property
    (8, 160),   # Expense Type
    (9, 200),   # Notes
]

# Light yellow for editable columns G, H, I (indices 6, 7, 8)
HIGHLIGHT_COLOR = {"red": 1.0, "green": 0.976, "blue": 0.769}  # #FFF9C4
ALT_ROW_COLOR = {"red": 0.961, "green": 0.961, "blue": 0.961}  # #F5F5F5
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dropdown_request(
    sheet_id: int, col_index: int, num_rows: int, values: Sequence[str]
) -> Dict[str, Any]:
    """Build a setDataValidation request for a single column."""
    return {
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": num_rows + 1,
                "startColumnIndex": col_index,
                "endColumnIndex": col_index + 1,
            },
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": v} for v in values],
                },
                "showCustomUi": True,
                "strict": False,
            },
        }
    }


def _freeze_header_request(sheet_id: int) -> Dict[str, Any]:
    return {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    }


def _bold_header_request(sheet_id: int, num_cols: int) -> Dict[str, Any]:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": num_cols,
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                }
            },
            "fields": "userEnteredFormat(textFormat,backgroundColor)",
        }
    }


def _col_width_requests(
    sheet_id: int, col_widths: List[tuple]
) -> List[Dict[str, Any]]:
    reqs = []
    for col_index, px in col_widths:
        reqs.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": col_index,
                        "endIndex": col_index + 1,
                    },
                    "properties": {"pixelSize": px},
                    "fields": "pixelSize",
                }
            }
        )
    return reqs


def _highlight_columns_request(
    sheet_id: int, col_start: int, col_end: int, num_rows: int, color: Dict
) -> Dict[str, Any]:
    """Apply a background color to a range of columns (data rows only)."""
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": num_rows + 1,
                "startColumnIndex": col_start,
                "endColumnIndex": col_end,
            },
            "cell": {
                "userEnteredFormat": {"backgroundColor": color}
            },
            "fields": "userEnteredFormat.backgroundColor",
        }
    }


def _alternating_rows_request(
    sheet_id: int, num_rows: int, num_cols: int
) -> List[Dict[str, Any]]:
    """Color even data rows with a light gray (skip highlighted cols 6-8)."""
    reqs = []
    # Left block: columns 0-5
    for row in range(1, num_rows + 1):
        if row % 2 == 0:
            reqs.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row,
                            "endRowIndex": row + 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 6,
                        },
                        "cell": {
                            "userEnteredFormat": {"backgroundColor": ALT_ROW_COLOR}
                        },
                        "fields": "userEnteredFormat.backgroundColor",
                    }
                }
            )
            # Right block: column 9 (Notes)
            if num_cols > 9:
                reqs.append(
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": row,
                                "endRowIndex": row + 1,
                                "startColumnIndex": 9,
                                "endColumnIndex": num_cols,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "backgroundColor": ALT_ROW_COLOR
                                }
                            },
                            "fields": "userEnteredFormat.backgroundColor",
                        }
                    }
                )
    return reqs


def _currency_format_request(
    sheet_id: int, col_index: int, num_rows: int
) -> Dict[str, Any]:
    """Format a column as number with 2 decimal places."""
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": num_rows + 1,
                "startColumnIndex": col_index,
                "endColumnIndex": col_index + 1,
            },
            "cell": {
                "userEnteredFormat": {
                    "numberFormat": {
                        "type": "CURRENCY",
                        "pattern": "$#,##0.00",
                    }
                }
            },
            "fields": "userEnteredFormat.numberFormat",
        }
    }


def _autofilter_request(
    sheet_id: int, num_rows: int, num_cols: int
) -> Dict[str, Any]:
    return {
        "setBasicFilter": {
            "filter": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": num_rows + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": num_cols,
                }
            }
        }
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def apply_formatting(spreadsheet: Any) -> None:
    """Apply all dropdown validation and visual formatting."""
    vendors_ws = spreadsheet.worksheet("Vendors")
    txn_ws = spreadsheet.worksheet("Transactions")

    vendor_sheet_id = vendors_ws.id
    txn_sheet_id = txn_ws.id

    # Get row counts from actual data
    vendor_rows = len(vendors_ws.get_all_values()) - 1  # minus header
    txn_rows = len(txn_ws.get_all_values()) - 1

    num_vendor_cols = len(VENDOR_COL_WIDTHS)
    num_txn_cols = len(TXN_COL_WIDTHS)

    print(f"Vendors tab: {vendor_rows} data rows, sheet_id={vendor_sheet_id}")
    print(f"Transactions tab: {txn_rows} data rows, sheet_id={txn_sheet_id}")

    requests: List[Dict[str, Any]] = []

    # --- Dropdowns (both tabs) ---
    for sid, nrows in [(vendor_sheet_id, vendor_rows), (txn_sheet_id, txn_rows)]:
        requests.append(_dropdown_request(sid, 6, nrows, CATEGORIES))
        requests.append(_dropdown_request(sid, 7, nrows, PROPERTIES))
        requests.append(_dropdown_request(sid, 8, nrows, EXPENSE_TYPES))

    # --- Freeze + bold headers ---
    for sid, ncols in [
        (vendor_sheet_id, num_vendor_cols),
        (txn_sheet_id, num_txn_cols),
    ]:
        requests.append(_freeze_header_request(sid))
        requests.append(_bold_header_request(sid, ncols))

    # --- Column widths ---
    requests.extend(_col_width_requests(vendor_sheet_id, VENDOR_COL_WIDTHS))
    requests.extend(_col_width_requests(txn_sheet_id, TXN_COL_WIDTHS))

    # --- Highlight editable columns (G, H, I = indices 6, 7, 8) ---
    for sid, nrows in [(vendor_sheet_id, vendor_rows), (txn_sheet_id, txn_rows)]:
        requests.append(
            _highlight_columns_request(sid, 6, 9, nrows, HIGHLIGHT_COLOR)
        )

    # --- Alternating row colors on Vendors tab only ---
    # Use banding instead of per-row requests for efficiency
    requests.append(
        {
            "addBanding": {
                "bandedRange": {
                    "range": {
                        "sheetId": vendor_sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": vendor_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 6,  # non-highlighted columns only
                    },
                    "rowProperties": {
                        "headerColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                        "firstBandColor": WHITE,
                        "secondBandColor": ALT_ROW_COLOR,
                    },
                }
            }
        }
    )
    # Banding for Notes column (9) on Vendors tab
    requests.append(
        {
            "addBanding": {
                "bandedRange": {
                    "range": {
                        "sheetId": vendor_sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": vendor_rows + 1,
                        "startColumnIndex": 9,
                        "endColumnIndex": 10,
                    },
                    "rowProperties": {
                        "headerColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                        "firstBandColor": WHITE,
                        "secondBandColor": ALT_ROW_COLOR,
                    },
                }
            }
        }
    )

    # --- Currency format for amount columns ---
    # Vendors: Total Amount (col 2), Sample Amount (col 4)
    requests.append(_currency_format_request(vendor_sheet_id, 2, vendor_rows))
    requests.append(_currency_format_request(vendor_sheet_id, 4, vendor_rows))
    # Transactions: Amount (col 4)
    requests.append(_currency_format_request(txn_sheet_id, 4, txn_rows))

    # --- Auto-filter on both tabs ---
    requests.append(
        _autofilter_request(vendor_sheet_id, vendor_rows, num_vendor_cols)
    )
    requests.append(
        _autofilter_request(txn_sheet_id, txn_rows, num_txn_cols)
    )

    print(f"Sending {len(requests)} formatting requests...")
    spreadsheet.batch_update({"requests": requests})
    print("Done! Formatting applied successfully.")


def set_dropdown_validation(
    spreadsheet: Any,
    worksheet: Any,
    col_index: int,
    num_rows: int,
    values: Sequence[str],
) -> None:
    """Set dropdown validation on a column using the raw Sheets API.

    This is the reliable replacement for the old _try_set_dropdown approach.
    Can be called from push.py for future pushes.
    """
    sheet_id = worksheet.id
    request = _dropdown_request(sheet_id, col_index, num_rows, values)
    spreadsheet.batch_update({"requests": [request]})


def main() -> None:
    import gspread

    print("Connecting to Google Sheets...")
    gc = gspread.service_account(filename=str(SERVICE_ACCOUNT))
    spreadsheet = gc.open_by_key(SHEET_ID)
    print(f"Opened: {spreadsheet.title}")

    # Remove any existing banded ranges first to avoid duplicates
    sheet_meta = spreadsheet.fetch_sheet_metadata()
    clear_requests = []
    for sheet in sheet_meta.get("sheets", []):
        for banding in sheet.get("bandedRanges", []):
            clear_requests.append(
                {"deleteBanding": {"bandedRangeId": banding["bandedRangeId"]}}
            )
    if clear_requests:
        print(f"Removing {len(clear_requests)} existing banded ranges...")
        spreadsheet.batch_update({"requests": clear_requests})

    # Also clear existing basic filters to avoid conflicts
    for tab_name in ["Vendors", "Transactions"]:
        try:
            ws = spreadsheet.worksheet(tab_name)
            clear_filter = {
                "clearBasicFilter": {"sheetId": ws.id}
            }
            spreadsheet.batch_update({"requests": [clear_filter]})
        except Exception:
            pass

    apply_formatting(spreadsheet)

    # --- Verify dropdowns were set ---
    print("\nVerifying dropdown validation...")
    sheet_meta = spreadsheet.fetch_sheet_metadata()
    for sheet in sheet_meta.get("sheets", []):
        title = sheet["properties"]["title"]
        if title in ("Vendors", "Transactions"):
            cols_with_validation = set()
            for col_data in sheet.get("data", [{}]):
                for row_data in col_data.get("rowData", []):
                    for i, cell in enumerate(row_data.get("values", [])):
                        if cell.get("dataValidation"):
                            cols_with_validation.add(i)
            print(f"  {title}: validation on column indices {sorted(cols_with_validation)}")


if __name__ == "__main__":
    main()
