"""LTR Excel writer.

Fills the accountant's blank LTR template with:
1. Every entry from the property-manager report (authoritative).
2. Every bank transaction tagged ``LTR`` that does **not** collide with a
   PM-report line (double-count guard).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from taxauto.categorize.mapper import TaggedTransaction
from taxauto.guards.double_count import detect_double_counts
from taxauto.parsers.pm_ltr import PMEntry

from ._common import append_rows, copy_template


def write_ltr_workbook(
    *,
    template_path: Path,
    output_path: Path,
    tagged_transactions: Iterable[TaggedTransaction],
    pm_entries: Iterable[PMEntry],
    date_window_days: int = 3,
) -> Path:
    copy_template(template_path, output_path)

    pm_list: List[PMEntry] = list(pm_entries)
    ltr_bank = [tt for tt in tagged_transactions if tt.category == "LTR"]

    # Identify double-counts (bank txns that mirror PM lines) and drop them.
    collisions = detect_double_counts(
        [tt.transaction for tt in ltr_bank],
        pm_list,
        date_window_days=date_window_days,
    )
    collision_ids = {id(c.bank_transaction) for c in collisions}
    ltr_bank = [tt for tt in ltr_bank if id(tt.transaction) not in collision_ids]

    rows: List[list] = []

    for entry in pm_list:
        rows.append([entry.date, entry.description, float(entry.amount), entry.pm_category])

    for tt in ltr_bank:
        txn = tt.transaction
        rows.append([txn.date, txn.description, float(txn.amount), tt.category])

    append_rows(output_path, rows)
    return output_path
