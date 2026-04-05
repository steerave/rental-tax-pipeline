"""Tests for the Rent QC owner statement parser."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from taxauto.parsers.rent_qc import (
    RentQCProperty,
    RentQCReport,
    RentQCTransaction,
    parse_rent_qc_pdf,
)


FIXTURE = Path(__file__).parent / "fixtures" / "rent_qc" / "sample_janfeb_2024.pdf"


@pytest.fixture()
def report() -> RentQCReport:
    return parse_rent_qc_pdf(FIXTURE)


def test_parses_statement_period(report: RentQCReport) -> None:
    assert report.period_start == date(2024, 1, 13)
    assert report.period_end == date(2024, 2, 12)


def test_parses_at_least_one_property(report: RentQCReport) -> None:
    assert len(report.properties) >= 1
    assert any("1015" in p.name for p in report.properties)


def test_parses_per_property_summary(report: RentQCReport) -> None:
    prop = next(p for p in report.properties if "1015" in p.name)
    assert prop.beginning_balance is not None
    assert prop.ending_balance is not None
    assert prop.cash_in is not None
    assert prop.cash_out is not None


def test_parses_transactions_with_cash_in_out_separated(report: RentQCReport) -> None:
    prop = next(p for p in report.properties if "1015" in p.name)
    assert len(prop.transactions) >= 5
    cash_in = [t for t in prop.transactions if t.cash_in is not None and t.cash_in > 0]
    cash_out = [t for t in prop.transactions if t.cash_out is not None and t.cash_out > 0]
    assert len(cash_in) >= 1
    assert len(cash_out) >= 1
    # Exactly one of cash_in or cash_out must be populated per transaction.
    for t in prop.transactions:
        populated = [x for x in (t.cash_in, t.cash_out) if x is not None]
        assert len(populated) == 1


def test_extracts_unit_and_category_from_description(report: RentQCReport) -> None:
    """Example: '102 - Rent Income - January 2024' -> unit='102', category='Rent Income'."""
    prop = next(p for p in report.properties if "1015" in p.name)
    rent_income = [t for t in prop.transactions if t.category == "Rent Income"]
    assert len(rent_income) >= 1
    assert any(t.unit is not None for t in rent_income)


def test_identifies_management_fee_category(report: RentQCReport) -> None:
    prop = next(p for p in report.properties if "1015" in p.name)
    mgmt = [t for t in prop.transactions if t.category == "Management Fees"]
    assert len(mgmt) >= 1


def test_identifies_owner_disbursement(report: RentQCReport) -> None:
    prop = next(p for p in report.properties if "1015" in p.name)
    owner = [
        t for t in prop.transactions
        if t.category == "Owner Distributions / S corp Distributions"
    ]
    assert len(owner) >= 1
    # Owner disbursements always have a reference (the eCheck hash)
    for t in owner:
        assert t.reference is not None
        assert t.cash_out is not None and t.cash_out > 0


def test_stops_at_cash_flow_appendix(report: RentQCReport) -> None:
    """The parser must not include appendix 'Cash Flow - 12 Month' data
    as transactions."""
    for prop in report.properties:
        # All transaction dates should fall within or near the report period.
        for t in prop.transactions:
            # Allow a generous boundary (the report period + 2 months cushion)
            assert abs((t.date - report.period_start).days) < 90
