"""Reconciliation guard for Chase Business Complete Checking statements."""

from __future__ import annotations

from decimal import Decimal

from taxauto.parsers.chase_checking import ChaseCheckingStatement


class ChaseReconcileError(Exception):
    pass


_TOL = Decimal("0.02")


def reconcile_chase_checking(statement: ChaseCheckingStatement) -> None:
    """Raise ChaseReconcileError if parsed data doesn't match summary totals."""
    counts = statement.instance_counts

    # Instance count checks
    for section, field in [
        ("deposits", "deposits"),
        ("checks_paid", "checks_paid"),
        ("electronic_withdrawals", "electronic_withdrawals"),
    ]:
        expected = counts.get(section)
        actual = len(getattr(statement, field))
        if expected is not None and expected != actual:
            raise ChaseReconcileError(
                f"{section} count mismatch: parsed {actual}, summary {expected}"
            )

    # Balance formula
    if statement.beginning_balance is not None and statement.ending_balance is not None:
        all_txns = statement.deposits + statement.checks_paid + statement.electronic_withdrawals
        total = sum((t.amount for t in all_txns), Decimal("0"))
        expected_delta = statement.ending_balance - statement.beginning_balance
        if abs(total - expected_delta) > _TOL:
            raise ChaseReconcileError(
                f"balance formula: txn sum {total}, expected delta {expected_delta}"
            )
