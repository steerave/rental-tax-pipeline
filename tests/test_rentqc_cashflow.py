"""Tests for the Cash Flow 12-Month summary parser."""

from pathlib import Path
from decimal import Decimal

import pytest

from taxauto.parsers.rentqc_cashflow import parse_cashflow_summaries, CashFlowSummary


# Use the real rentqc-11 file for testing since the Cash Flow pages
# contain public category/amount data (no PII beyond property addresses
# which are already in the committed CLAUDE.md)
REAL_PDF = Path("years/2024/inputs/rentqc-11 novdec.pdf")


@pytest.mark.skipif(not REAL_PDF.exists(), reason="Real Rent QC PDF not available")
def test_parses_three_property_summaries() -> None:
    summaries = parse_cashflow_summaries(REAL_PDF)
    assert len(summaries) == 3
    names = {s.property_name for s in summaries}
    assert any("1015" in n for n in names)
    assert any("1210" in n or "College" in n for n in names)
    assert any("308" in n or "Lincoln" in n for n in names)


@pytest.mark.skipif(not REAL_PDF.exists(), reason="Real Rent QC PDF not available")
def test_extracts_income_totals() -> None:
    summaries = parse_cashflow_summaries(REAL_PDF)
    s1015 = next(s for s in summaries if "1015" in s.property_name)

    assert "Rent Income" in s1015.income
    # From the raw text: Rent Income Total = 96,781.63
    assert s1015.income["Rent Income"] == Decimal("96781.63")


@pytest.mark.skipif(not REAL_PDF.exists(), reason="Real Rent QC PDF not available")
def test_extracts_expense_totals() -> None:
    summaries = parse_cashflow_summaries(REAL_PDF)
    s1015 = next(s for s in summaries if "1015" in s.property_name)

    assert "Management Fees" in s1015.expenses
    assert s1015.expenses["Management Fees"] == Decimal("9678.17")

    # HVAC wraps across lines -- verify it's captured
    assert "HVAC (Heat, Ventilation, Air)" in s1015.expenses
    assert s1015.expenses["HVAC (Heat, Ventilation, Air)"] == Decimal("2932.57")


@pytest.mark.skipif(not REAL_PDF.exists(), reason="Real Rent QC PDF not available")
def test_captures_major_repairs_and_renovations() -> None:
    summaries = parse_cashflow_summaries(REAL_PDF)
    s1015 = next(s for s in summaries if "1015" in s.property_name)

    # This was the $23K missing from transaction-level parsing
    assert "Major Repairs and Renovations" in s1015.expenses
    assert s1015.expenses["Major Repairs and Renovations"] == Decimal("23325.00")


@pytest.mark.skipif(not REAL_PDF.exists(), reason="Real Rent QC PDF not available")
def test_captures_flooring_for_1210() -> None:
    summaries = parse_cashflow_summaries(REAL_PDF)
    s1210 = next(s for s in summaries if "1210" in s.property_name or "College" in s.property_name)

    assert "Flooring" in s1210.expenses
    assert s1210.expenses["Flooring"] == Decimal("1206.80")


@pytest.mark.skipif(not REAL_PDF.exists(), reason="Real Rent QC PDF not available")
def test_period_extracted() -> None:
    summaries = parse_cashflow_summaries(REAL_PDF)
    for s in summaries:
        assert "2024" in s.period
        assert "Jan" in s.period
        assert "Dec" in s.period


@pytest.mark.skipif(not REAL_PDF.exists(), reason="Real Rent QC PDF not available")
def test_total_income_expense_net() -> None:
    summaries = parse_cashflow_summaries(REAL_PDF)
    s1015 = next(s for s in summaries if "1015" in s.property_name)

    assert s1015.total_income == Decimal("99701.76")
    assert s1015.total_expense == Decimal("61606.44")
    assert s1015.net_income == Decimal("38095.32")


@pytest.mark.skipif(not REAL_PDF.exists(), reason="Real Rent QC PDF not available")
def test_308_lincoln_has_no_laundry() -> None:
    """308 Lincoln has no laundry or late fees."""
    summaries = parse_cashflow_summaries(REAL_PDF)
    s308 = next(s for s in summaries if "308" in s.property_name)

    assert "Laundry Income" not in s308.income
    assert "Late Fee" not in s308.income
    assert s308.income["Rent Income"] == Decimal("17600.00")
