"""Tests for the Rent QC reconciliation guard."""

from decimal import Decimal

import pytest

from taxauto.guards.rentqc_reconcile import RentQCReconcileError, reconcile_rent_qc_report
from taxauto.parsers.rent_qc import RentQCProperty, RentQCReport, RentQCTransaction
from pathlib import Path
from datetime import date


def _txn(cash_in=None, cash_out=None) -> RentQCTransaction:
    return RentQCTransaction(
        date=date(2024, 1, 15), payee="X", txn_type="Check",
        reference=None, description="test", cash_in=cash_in,
        cash_out=cash_out, balance=None, unit=None, category=None,
    )


def _prop(
    beginning=Decimal("2088.00"),
    cash_in=Decimal("7885.00"),
    cash_out=Decimal("-3474.32"),
    owner=Decimal("-4355.68"),
    ending=Decimal("2143.00"),
    transactions=None,
) -> RentQCProperty:
    txns = transactions or [
        _txn(cash_in=Decimal("7885.00")),
        _txn(cash_out=Decimal("7830.00")),  # includes owner disbursements in the table
    ]
    return RentQCProperty(
        name="1015 39th St",
        beginning_balance=beginning,
        cash_in=cash_in,
        cash_out=cash_out,
        owner_disbursements=owner,
        ending_balance=ending,
        total_cash_in_printed=Decimal("7885.00"),
        total_cash_out_printed=Decimal("7830.00"),
        transactions=txns,
    )


def _report(**kwargs) -> RentQCReport:
    prop = _prop(**kwargs)
    return RentQCReport(
        source_path=Path("test.pdf"),
        period_start=date(2024, 1, 13),
        period_end=date(2024, 2, 12),
        consolidated_beginning=prop.beginning_balance,
        consolidated_cash_in=prop.cash_in,
        consolidated_cash_out=prop.cash_out,
        consolidated_owner_disbursements=prop.owner_disbursements,
        consolidated_ending=prop.ending_balance,
        properties=[prop],
    )


def test_reconcile_passes_on_valid_report() -> None:
    reconcile_rent_qc_report(_report())


def test_reconcile_fails_on_balance_formula_mismatch() -> None:
    with pytest.raises(RentQCReconcileError):
        reconcile_rent_qc_report(_report(ending=Decimal("9999.99")))


def test_reconcile_fails_on_consolidated_sum_mismatch() -> None:
    report = _report()
    report.consolidated_beginning = Decimal("0")  # wrong
    with pytest.raises(RentQCReconcileError):
        reconcile_rent_qc_report(report)
