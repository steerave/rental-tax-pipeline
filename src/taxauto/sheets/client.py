"""gspread client factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def get_sheets_client(service_account_json: Path) -> Any:
    """Return an authorized gspread client.

    Imports are local so modules that don't use Sheets don't pay the import
    cost and so tests can mock the client without Google deps.
    """
    import gspread

    return gspread.service_account(filename=str(service_account_json))
