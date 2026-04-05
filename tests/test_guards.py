"""Tests for reconciliation and duplicate guards."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from taxauto.guards.duplicates import DuplicateError, detect_duplicates
from taxauto.guards.reconcile import ReconcileError, reconcile_statement
from taxauto.parsers.bank import ParsedStatement, Transaction


def _txn(day: int, description: str, amount: str) -> Transaction:
    return Transaction(
        date=date(2025, 1, day),
        description=description,
        amount=Decimal(amount),
        balance=None,
        account="****1234",
    )


# --- reconcile ------------------------------------------------------------


def test_reconcile_passes_when_totals_agree() -> None:
    stmt = ParsedStatement(
        transactions=[_txn(1, "A", "100.00"), _txn(2, "B", "-40.00")],
        beginning_balance=Decimal("1000.00"),
        ending_balance=Decimal("1060.00"),
        total_deposits=Decimal("100.00"),
        total_withdrawals=Decimal("40.00"),
    )
    reconcile_statement(stmt)  # must not raise


def test_reconcile_fails_when_balance_delta_mismatch() -> None:
    stmt = ParsedStatement(
        transactions=[_txn(1, "A", "100.00")],
        beginning_balance=Decimal("1000.00"),
        ending_balance=Decimal("2000.00"),  # delta says 1000 but txns only total 100
        total_deposits=Decimal("100.00"),
        total_withdrawals=Decimal("0.00"),
    )
    with pytest.raises(ReconcileError):
        reconcile_statement(stmt)


def test_reconcile_tolerance_allows_penny_rounding() -> None:
    stmt = ParsedStatement(
        transactions=[_txn(1, "A", "100.00")],
        beginning_balance=Decimal("1000.00"),
        ending_balance=Decimal("1100.01"),  # 1 cent off
        total_deposits=Decimal("100.00"),
        total_withdrawals=Decimal("0.00"),
    )
    reconcile_statement(stmt, tolerance=Decimal("0.02"))


# --- duplicates -----------------------------------------------------------


def test_detect_duplicates_flags_same_date_amount_description() -> None:
    txns = [
        _txn(5, "HOME DEPOT", "-50.00"),
        _txn(5, "HOME DEPOT", "-50.00"),  # dupe
        _txn(6, "HOME DEPOT", "-50.00"),
    ]
    dupes = detect_duplicates(txns)
    assert len(dupes) == 1
    assert len(dupes[0]) == 2


def test_detect_duplicates_returns_empty_when_none() -> None:
    txns = [_txn(5, "A", "-10.00"), _txn(6, "B", "-20.00")]
    assert detect_duplicates(txns) == []


def test_detect_duplicates_raise_mode() -> None:
    txns = [_txn(5, "X", "-10.00"), _txn(5, "X", "-10.00")]
    with pytest.raises(DuplicateError):
        detect_duplicates(txns, raise_on_found=True)


