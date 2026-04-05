"""Reconciliation guard.

Verifies that the sum of parsed bank transactions matches the balance delta
and, where present, the header deposits/withdrawals totals.
"""

from __future__ import annotations

from decimal import Decimal

from taxauto.parsers.bank import ParsedStatement


class ReconcileError(Exception):
    """Raised when a statement's parsed transactions don't match its header totals."""


def reconcile_statement(
    statement: ParsedStatement,
    *,
    tolerance: Decimal = Decimal("0.02"),
) -> None:
    """Raise ReconcileError if the statement doesn't reconcile within tolerance."""
    txn_sum = sum((t.amount for t in statement.transactions), Decimal("0"))

    if statement.beginning_balance is not None and statement.ending_balance is not None:
        expected_delta = statement.ending_balance - statement.beginning_balance
        if abs(txn_sum - expected_delta) > tolerance:
            raise ReconcileError(
                f"balance delta mismatch: transactions sum to {txn_sum}, "
                f"ending - beginning = {expected_delta}"
            )

    if statement.total_deposits is not None and statement.total_withdrawals is not None:
        deposits = sum((t.amount for t in statement.transactions if t.amount > 0), Decimal("0"))
        withdrawals = sum((t.amount for t in statement.transactions if t.amount < 0), Decimal("0"))
        # total_withdrawals in header is usually reported as a positive magnitude.
        expected_withdrawals = -statement.total_withdrawals
        if abs(deposits - statement.total_deposits) > tolerance:
            raise ReconcileError(
                f"deposits mismatch: transactions {deposits} vs header {statement.total_deposits}"
            )
        if abs(withdrawals - expected_withdrawals) > tolerance:
            raise ReconcileError(
                f"withdrawals mismatch: transactions {withdrawals} vs header {expected_withdrawals}"
            )
