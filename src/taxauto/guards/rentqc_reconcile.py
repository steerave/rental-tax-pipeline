"""Reconciliation guard for Rent QC owner statement reports."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from taxauto.parsers.rent_qc import RentQCReport


class RentQCReconcileError(Exception):
    pass


_TOL = Decimal("0.02")


def _check(label: str, a: Optional[Decimal], b: Optional[Decimal]) -> None:
    if a is None or b is None:
        return
    if abs(a - b) > _TOL:
        raise RentQCReconcileError(f"{label}: {a} != {b} (delta {a - b})")


def reconcile_rent_qc_report(report: RentQCReport) -> None:
    """Raise RentQCReconcileError if any invariant fails."""
    for prop in report.properties:
        # Invariant 5: balance formula
        if prop.beginning_balance is not None and prop.ending_balance is not None:
            cash_in = prop.cash_in or Decimal("0")
            cash_out = prop.cash_out or Decimal("0")
            owner = prop.owner_disbursements or Decimal("0")
            expected_ending = prop.beginning_balance + cash_in + cash_out + owner
            _check(f"{prop.name}: balance formula", expected_ending, prop.ending_balance)

        # Invariant 3: printed Total Cash In vs summary Cash In
        if prop.total_cash_in_printed is not None and prop.cash_in is not None:
            _check(f"{prop.name}: total_cash_in vs summary", prop.total_cash_in_printed, prop.cash_in)

        # Invariant 4: printed Total Cash Out vs -(summary Cash Out + Owner Disbursements)
        if prop.total_cash_out_printed is not None and prop.cash_out is not None:
            owner = prop.owner_disbursements or Decimal("0")
            expected_total_out = -(prop.cash_out + owner)
            _check(f"{prop.name}: total_cash_out", expected_total_out, prop.total_cash_out_printed)

        # Invariants 1-2 (transaction sums vs printed totals)
        txn_cash_in = sum((t.cash_in for t in prop.transactions if t.cash_in), Decimal("0"))
        txn_cash_out = sum((t.cash_out for t in prop.transactions if t.cash_out), Decimal("0"))
        _check(f"{prop.name}: txn sum cash_in", txn_cash_in, prop.total_cash_in_printed)
        _check(f"{prop.name}: txn sum cash_out", txn_cash_out, prop.total_cash_out_printed)

    # Invariant 6: consolidated sums
    def _sum_attr(attr: str) -> Decimal:
        total = Decimal("0")
        for p in report.properties:
            val = getattr(p, attr, None)
            if val is not None:
                total += val
        return total

    for attr, consolidated in [
        ("beginning_balance", report.consolidated_beginning),
        ("cash_in", report.consolidated_cash_in),
        ("cash_out", report.consolidated_cash_out),
        ("owner_disbursements", report.consolidated_owner_disbursements),
        ("ending_balance", report.consolidated_ending),
    ]:
        if consolidated is not None:
            _check(f"consolidated.{attr}", _sum_attr(attr), consolidated)
