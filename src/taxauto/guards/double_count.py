"""Double-count guard for LTR bookkeeping.

The LTR PM report is authoritative for PM-paid expenses and rental income.
If a bank transaction corresponds to the same event as a PM-report line
(e.g., the PM's monthly owner draw shows up both as a bank deposit and as a
PM-report net-to-owner line), we must not count it twice.

Matching rule: same signed amount and date within a small window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable, List

from taxauto.parsers.bank import Transaction
from taxauto.parsers.pm_ltr import PMEntry


class DoubleCountError(Exception):
    """Raised in strict mode when a bank/PM double-count is detected."""


@dataclass(frozen=True)
class DoubleCountCollision:
    bank_transaction: Transaction
    pm_entry: PMEntry


def detect_double_counts(
    bank_transactions: Iterable[Transaction],
    pm_entries: Iterable[PMEntry],
    *,
    date_window_days: int = 3,
    raise_on_found: bool = False,
) -> List[DoubleCountCollision]:
    pm_list = list(pm_entries)
    window = timedelta(days=date_window_days)
    collisions: List[DoubleCountCollision] = []

    for txn in bank_transactions:
        for entry in pm_list:
            if entry.amount != txn.amount:
                continue
            if abs(entry.date - txn.date) > window:
                continue
            collisions.append(DoubleCountCollision(bank_transaction=txn, pm_entry=entry))
            break

    if collisions and raise_on_found:
        raise DoubleCountError(f"{len(collisions)} bank/PM double-count(s) detected")
    return collisions
