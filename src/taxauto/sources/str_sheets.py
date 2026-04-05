"""Short-term rental earnings source reader.

Phase 2: reads from a local XLSX file that mirrors the Google Sheets structure.
Live Google Sheets reader deferred to Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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


def total_net_payout_by_property(earnings: List[STREarning]) -> Dict[str, Decimal]:
    """Sum net payouts by property name."""
    totals: Dict[str, Decimal] = {}
    for e in earnings:
        totals[e.property_name] = totals.get(e.property_name, Decimal("0")) + e.net_payout
    return totals
