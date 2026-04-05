"""STR Excel writer.

Fills the accountant's blank STR template with every transaction the
categorizer tagged (or a reviewer confirmed) as ``STR``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from taxauto.categorize.mapper import TaggedTransaction

from ._common import append_rows, copy_template


def write_str_workbook(
    *,
    template_path: Path,
    output_path: Path,
    tagged_transactions: Iterable[TaggedTransaction],
) -> Path:
    """Copy the template and append every STR transaction."""
    copy_template(template_path, output_path)

    rows = []
    for tt in tagged_transactions:
        if tt.category != "STR":
            continue
        txn = tt.transaction
        rows.append([txn.date, txn.description, float(txn.amount), tt.category])

    append_rows(output_path, rows)
    return output_path
