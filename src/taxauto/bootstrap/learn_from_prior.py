"""Prior-year bootstrap learner.

Mines a completed, filed tax year's bank PDFs and accountant Excel workbooks
to seed ``vendor_mapping.yaml`` with high-confidence vendor → category rules
so that the first run of a new year starts with as much automation as
possible.

Phase 1 uses a conservative matcher: exact amount + date within ±N days +
fuzzy description similarity above a threshold. Phase 2 can widen this.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import openpyxl
from rapidfuzz import fuzz

from taxauto.categorize.mapper import normalize_vendor
from taxauto.parsers.bank import Transaction


@dataclass(frozen=True)
class PriorEntry:
    date: date
    description: str
    amount: Decimal
    category: str


@dataclass
class BootstrapReport:
    matched: int = 0
    unmatched_bank: int = 0
    unmatched_prior: int = 0
    new_vendors_learned: int = 0
    ambiguous: int = 0


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _to_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    return None


def read_prior_entries_xlsx(path: Path) -> List[PriorEntry]:
    """Read an accountant-filed XLSX as a list of ``PriorEntry`` rows.

    Expects the first row of each sheet to be headers containing (at least)
    ``Date``, ``Description``, ``Amount``, ``Category`` (case-insensitive).
    Sheets without those columns are skipped.
    """
    path = Path(path)
    wb = openpyxl.load_workbook(path, data_only=True)
    entries: List[PriorEntry] = []

    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
        try:
            i_date = header.index("date")
            i_desc = header.index("description")
            i_amt = header.index("amount")
            i_cat = header.index("category")
        except ValueError:
            continue

        for row in rows[1:]:
            if row is None:
                continue
            d = _to_date(row[i_date])
            desc = row[i_desc]
            amt = _to_decimal(row[i_amt])
            cat = row[i_cat]
            if d is None or desc is None or amt is None or cat is None:
                continue
            entries.append(
                PriorEntry(
                    date=d,
                    description=str(desc).strip(),
                    amount=amt,
                    category=str(cat).strip(),
                )
            )

    return entries


def _best_match(
    txn: Transaction,
    candidates: List[PriorEntry],
    *,
    date_window_days: int,
    fuzzy_threshold: float,
) -> Optional[PriorEntry]:
    best: Optional[PriorEntry] = None
    best_score = 0.0

    window = timedelta(days=date_window_days)
    # Normalize the bank description once to strip POS/ACH prefixes and store #s.
    txn_norm = normalize_vendor(txn.description)
    for entry in candidates:
        if entry.amount != txn.amount:
            continue
        if abs(entry.date - txn.date) > window:
            continue
        entry_norm = normalize_vendor(entry.description)
        # rapidfuzz returns 0..100
        score = fuzz.token_set_ratio(txn_norm, entry_norm) / 100.0
        if score >= fuzzy_threshold and score > best_score:
            best = entry
            best_score = score

    return best


def match_and_learn(
    bank_transactions: Iterable[Transaction],
    prior_entries: Iterable[PriorEntry],
    mapping: Dict[str, Any],
    *,
    year: int,
    date_window_days: int = 3,
    fuzzy_threshold: float = 0.72,
    confidence_on_match: float = 0.9,
) -> BootstrapReport:
    """Match bank transactions to prior-year filed entries and learn vendors."""
    bank_list = list(bank_transactions)
    prior_list = list(prior_entries)
    report = BootstrapReport()

    vendors = mapping.setdefault("vendors", {})
    consumed: set = set()  # indexes into prior_list

    for txn in bank_list:
        # Only search not-yet-consumed prior entries.
        candidates = [p for i, p in enumerate(prior_list) if i not in consumed]
        best = _best_match(
            txn,
            candidates,
            date_window_days=date_window_days,
            fuzzy_threshold=fuzzy_threshold,
        )
        if best is None:
            report.unmatched_bank += 1
            continue

        # Mark consumed.
        idx = prior_list.index(best)
        consumed.add(idx)
        report.matched += 1

        key = normalize_vendor(txn.description)
        if not key:
            continue

        entry = vendors.get(key)
        if entry is None:
            vendors[key] = {
                "category": best.category,
                "confidence": confidence_on_match,
                "occurrences": 1,
                "learned_from": [year],
                "ambiguous": False,
            }
            report.new_vendors_learned += 1
        else:
            entry["occurrences"] = int(entry.get("occurrences", 0)) + 1
            learned_from = entry.setdefault("learned_from", [])
            if year not in learned_from:
                learned_from.append(year)
            if entry.get("category") and entry["category"] != best.category:
                if not entry.get("ambiguous", False):
                    report.ambiguous += 1
                entry["ambiguous"] = True

    report.unmatched_prior = len(prior_list) - len(consumed)
    return report
