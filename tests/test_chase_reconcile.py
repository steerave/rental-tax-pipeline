"""Tests for the Chase Business Checking reconciliation guard."""

from datetime import date
from decimal import Decimal

import pytest

from taxauto.guards.chase_reconcile import ChaseReconcileError, reconcile_chase_checking
from taxauto.parsers.chase_checking import ChaseCheckingStatement, ChaseTransaction


def _txn(amount: str, section: str) -> ChaseTransaction:
    return ChaseTransaction(
        date=date(2024, 1, 5), description="X",
        amount=Decimal(amount), account="XXXX9999", section=section,
    )


def test_reconcile_passes() -> None:
    s = ChaseCheckingStatement(account="XXXX9999")
    s.beginning_balance = Decimal("1000.00")
    s.ending_balance = Decimal("1080.00")
    s.instance_counts = {"deposits": 1, "checks_paid": 1, "electronic_withdrawals": 0, "total": 2}
    s.deposits = [_txn("100.00", "deposits")]
    s.checks_paid = [_txn("-20.00", "checks_paid")]
    s.electronic_withdrawals = []
    reconcile_chase_checking(s)  # no raise


def test_reconcile_fails_on_count_mismatch() -> None:
    s = ChaseCheckingStatement(account="XXXX9999")
    s.beginning_balance = Decimal("1000.00")
    s.ending_balance = Decimal("1100.00")
    s.instance_counts = {"deposits": 2, "checks_paid": 0, "electronic_withdrawals": 0, "total": 2}
    s.deposits = [_txn("100.00", "deposits")]  # only 1, but count says 2
    with pytest.raises(ChaseReconcileError):
        reconcile_chase_checking(s)


def test_reconcile_fails_on_balance_formula() -> None:
    s = ChaseCheckingStatement(account="XXXX9999")
    s.beginning_balance = Decimal("1000.00")
    s.ending_balance = Decimal("2000.00")  # wrong
    s.instance_counts = {"deposits": 1, "checks_paid": 0, "electronic_withdrawals": 0, "total": 1}
    s.deposits = [_txn("100.00", "deposits")]
    with pytest.raises(ChaseReconcileError):
        reconcile_chase_checking(s)
