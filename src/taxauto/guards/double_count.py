"""eCheck-reference based LTR double-count guard.

Prevents counting the same cash movement twice: once from the Rent QC
owner statement and once from the Chase bank deposit that represents
the same owner disbursement payment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from taxauto.parsers.chase_checking import ChaseTransaction
from taxauto.parsers.rent_qc import RentQCTransaction


class DoubleCountError(Exception):
    pass


@dataclass(frozen=True)
class DoubleCountCollision:
    bank_transaction: ChaseTransaction
    rentqc_transactions: List[RentQCTransaction]
    echeck_reference: str
    rentqc_sum: Decimal


def _group_owner_disbursements(
    rentqc_transactions: Iterable[RentQCTransaction],
) -> Dict[str, List[RentQCTransaction]]:
    """Group owner disbursement transactions by eCheck reference."""
    groups: Dict[str, List[RentQCTransaction]] = {}
    for t in rentqc_transactions:
        if t.category != "Owner Distributions / S corp Distributions":
            continue
        if t.reference is None:
            continue
        groups.setdefault(t.reference, []).append(t)
    return groups


def detect_double_counts(
    bank_deposits: Iterable[ChaseTransaction],
    rentqc_transactions: Iterable[RentQCTransaction],
    *,
    date_window_days: int = 5,
    amount_tolerance: Decimal = Decimal("0.50"),
    raise_on_found: bool = False,
) -> List[DoubleCountCollision]:
    """Find bank deposits that match Rent QC owner disbursement groups."""
    groups = _group_owner_disbursements(rentqc_transactions)
    window = timedelta(days=date_window_days)

    # Pre-compute group sums
    group_sums: Dict[str, Decimal] = {
        ref: sum((t.cash_out for t in txns if t.cash_out), Decimal("0"))
        for ref, txns in groups.items()
    }

    collisions: List[DoubleCountCollision] = []
    used_refs: set = set()

    for deposit in bank_deposits:
        if deposit.amount <= 0:
            continue
        # Only consider deposits that look like Rent QC payments
        desc_lower = deposit.description.lower()
        if "rent qc" not in desc_lower:
            continue

        for ref, txns in groups.items():
            if ref in used_refs:
                continue
            group_sum = group_sums[ref]
            if abs(deposit.amount - group_sum) > amount_tolerance:
                continue
            # Check date proximity
            if any(abs(deposit.date - t.date) <= window for t in txns):
                collisions.append(
                    DoubleCountCollision(
                        bank_transaction=deposit,
                        rentqc_transactions=list(txns),
                        echeck_reference=ref,
                        rentqc_sum=group_sum,
                    )
                )
                used_refs.add(ref)
                break

    if collisions and raise_on_found:
        raise DoubleCountError(
            f"{len(collisions)} bank/PM double-count(s) detected"
        )
    return collisions
