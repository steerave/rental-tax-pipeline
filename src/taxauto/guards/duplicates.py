"""Duplicate transaction detection.

Two transactions are considered duplicates if they share date, amount, and
description. This catches the common case of a bank statement being parsed
twice or overlapping statement periods.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, List

from taxauto.parsers.bank import Transaction


class DuplicateError(Exception):
    """Raised in strict mode when duplicates are detected."""


def detect_duplicates(
    transactions: Iterable[Transaction],
    *,
    raise_on_found: bool = False,
) -> List[List[Transaction]]:
    """Group duplicate transactions. Returns a list of duplicate groups."""
    buckets: dict = defaultdict(list)
    for t in transactions:
        key = (t.date, t.amount, t.description.strip().lower())
        buckets[key].append(t)

    groups = [g for g in buckets.values() if len(g) > 1]
    if groups and raise_on_found:
        raise DuplicateError(f"{len(groups)} duplicate group(s) detected")
    return groups
