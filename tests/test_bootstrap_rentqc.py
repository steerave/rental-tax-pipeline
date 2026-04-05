"""Tests for the Rent QC bootstrap learner."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from taxauto.bootstrap.learn_from_rentqc import (
    BootstrapReport,
    learn_vendors_from_rentqc,
)
from taxauto.parsers.rent_qc import RentQCProperty, RentQCReport, RentQCTransaction


def _txn(payee: str, category: str, cash_out: str = "100.00") -> RentQCTransaction:
    return RentQCTransaction(
        date=date(2024, 1, 15), payee=payee, txn_type="Check",
        reference="ABCD-1234", description=f"102 - {category} - details",
        cash_in=None, cash_out=Decimal(cash_out), balance=None,
        unit="102", category=category,
    )


def _report(txns: list) -> RentQCReport:
    prop = RentQCProperty(name="1015 39th St", transactions=txns)
    return RentQCReport(
        source_path=Path("test.pdf"),
        period_start=date(2024, 1, 13),
        period_end=date(2024, 2, 12),
        properties=[prop],
    )


def test_learns_new_vendors() -> None:
    txns = [
        _txn("QC Mow and Snow", "Lawn and Snow Care", "150.00"),
        _txn("QC Mow and Snow", "Lawn and Snow Care", "25.00"),
        _txn("Iowa American Water", "Water", "200.00"),
    ]
    mapping: dict = {"vendors": {}}
    report = learn_vendors_from_rentqc([_report(txns)], mapping, year=2024)

    assert isinstance(report, BootstrapReport)
    assert report.vendors_learned == 2
    assert report.total_transactions == 3

    from taxauto.categorize.mapper import normalize_vendor
    key = normalize_vendor("QC Mow and Snow")
    assert key in mapping["vendors"]
    assert mapping["vendors"][key]["category"] == "Lawn and Snow Care"
    assert mapping["vendors"][key]["occurrences"] == 2
    assert 2024 in mapping["vendors"][key]["learned_from"]


def test_flags_ambiguous_vendor() -> None:
    txns = [
        _txn("MidAmerican Energy", "Electricity & Gas", "100.00"),
        _txn("MidAmerican Energy", "Water", "50.00"),  # different category!
    ]
    mapping: dict = {"vendors": {}}
    learn_vendors_from_rentqc([_report(txns)], mapping, year=2024)

    from taxauto.categorize.mapper import normalize_vendor
    entry = mapping["vendors"][normalize_vendor("MidAmerican Energy")]
    assert entry["ambiguous"] is True


def test_empty_reports_returns_zero_report() -> None:
    mapping: dict = {"vendors": {}}
    report = learn_vendors_from_rentqc([], mapping, year=2024)
    assert report.total_transactions == 0
    assert report.vendors_learned == 0
