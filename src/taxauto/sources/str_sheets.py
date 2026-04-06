"""Short-term rental earnings source reader.

Supports two backends:
  1. Live Google Sheets via gspread (primary — Phase 3)
  2. Local XLSX fallback (Phase 2 legacy)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional

import openpyxl


COLUMN_ALTERNATIVES = {
    "stay_start": ["stay_start", "check in", "checkin", "arrival"],
    "stay_end": ["stay_end", "check out", "checkout", "departure"],
    "platform": ["platform", "source", "channel"],
    "gross": ["gross", "gross amount", "booking total"],
    "fees": ["fees", "host fees", "service fee"],
    "net_payout": ["net_payout", "net", "payout", "net payout"],
}


@dataclass(frozen=True)
class STREarning:
    property_name: str
    stay_start: Optional[date]
    stay_end: Optional[date]
    platform: str
    gross: Optional[Decimal]
    fees: Optional[Decimal]
    net_payout: Decimal


def _to_decimal(v) -> Optional[Decimal]:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _to_date(v) -> Optional[date]:
    if isinstance(v, date):
        return v
    return None


def _find_column(header: List[str], alternatives: List[str]) -> Optional[int]:
    header_lower = [h.lower() if h else "" for h in header]
    for alt in alternatives:
        if alt.lower() in header_lower:
            return header_lower.index(alt.lower())
    return None


def load_str_earnings_from_xlsx(path: Path) -> List[STREarning]:
    """Load STR earnings from a local XLSX with one sheet per property."""
    wb = openpyxl.load_workbook(Path(path), data_only=True)
    out: List[STREarning] = []
    for sheet in wb.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if len(rows) < 2:
            continue
        header = [str(h) if h else "" for h in rows[0]]
        cols = {k: _find_column(header, alts) for k, alts in COLUMN_ALTERNATIVES.items()}
        if cols.get("net_payout") is None:
            continue
        for row in rows[1:]:
            if row is None:
                continue
            net = _to_decimal(row[cols["net_payout"]])
            if net is None:
                continue
            out.append(
                STREarning(
                    property_name=sheet.title,
                    stay_start=_to_date(row[cols["stay_start"]]) if cols["stay_start"] is not None else None,
                    stay_end=_to_date(row[cols["stay_end"]]) if cols["stay_end"] is not None else None,
                    platform=str(row[cols["platform"]]) if cols["platform"] is not None and row[cols["platform"]] is not None else "",
                    gross=_to_decimal(row[cols["gross"]]) if cols["gross"] is not None else None,
                    fees=_to_decimal(row[cols["fees"]]) if cols["fees"] is not None else None,
                    net_payout=net,
                )
            )
    return out


def _parse_date_flexible(raw: str, year: int) -> Optional[date]:
    """Parse dates in M/D/YY, M/D/YYYY, or M/D (infer year) formats."""
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    # Try M/D/YYYY
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    # Try M/D (no year) — infer from the year parameter
    m = re.match(r"^(\d{1,2})/(\d{1,2})$", raw)
    if m:
        try:
            return date(year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


def _clean_decimal(raw: str) -> Optional[Decimal]:
    """Strip $, commas, whitespace; return Decimal or None."""
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def load_str_earnings_from_gsheets(
    sheet_configs: Dict[str, str],
    *,
    service_account_json: Path,
    year: int,
) -> List[STREarning]:
    """Load STR earnings from Google Sheets.

    sheet_configs maps property names to Google Sheet IDs.
    Each sheet should have a tab matching the year pattern (e.g., "'24 earnings").
    """
    import gspread

    gc = gspread.service_account(filename=str(service_account_json))
    yy = str(year)[-2:]
    yyyy = str(year)

    # Tab name candidates in priority order
    tab_candidates = [
        f"'{yy} earnings",
        f"'{yy} Earnings",
        f"{yyyy} earnings",
        f"{yyyy} Earnings",
    ]

    out: List[STREarning] = []
    for prop_name, sheet_id in sheet_configs.items():
        sh = gc.open_by_key(sheet_id)

        # Find the right tab via fuzzy matching
        worksheet = None
        ws_titles = [ws.title for ws in sh.worksheets()]
        for candidate in tab_candidates:
            if candidate in ws_titles:
                worksheet = sh.worksheet(candidate)
                break
        if worksheet is None:
            # Try case-insensitive matching as last resort
            for title in ws_titles:
                title_lower = title.lower().strip()
                for candidate in tab_candidates:
                    if title_lower == candidate.lower():
                        worksheet = sh.worksheet(title)
                        break
                if worksheet:
                    break

        if worksheet is None:
            print(f"[str_sheets] WARNING: no matching tab for {prop_name} in {ws_titles}")
            continue

        rows = worksheet.get_all_values()
        if len(rows) < 2:
            continue

        # Schema: Start Date (0), End Date (1), Payout (2), Source (3)
        # Skip header row
        for row in rows[1:]:
            if len(row) < 3:
                continue
            # Skip blank rows
            if all(not cell.strip() for cell in row[:3]):
                continue

            net = _clean_decimal(row[2])
            if net is None:
                continue  # cancelled, blank, header repeat, etc.

            stay_start = _parse_date_flexible(row[0], year)
            stay_end = _parse_date_flexible(row[1], year) if len(row) > 1 else None
            platform = row[3].strip() if len(row) > 3 and row[3].strip() else ""

            out.append(STREarning(
                property_name=prop_name,
                stay_start=stay_start,
                stay_end=stay_end,
                platform=platform,
                gross=None,
                fees=None,
                net_payout=net,
            ))

    return out


def total_net_payout_by_property(earnings: List[STREarning]) -> Dict[str, Decimal]:
    """Sum net payouts by property name."""
    totals: Dict[str, Decimal] = {}
    for e in earnings:
        totals[e.property_name] = totals.get(e.property_name, Decimal("0")) + e.net_payout
    return totals
