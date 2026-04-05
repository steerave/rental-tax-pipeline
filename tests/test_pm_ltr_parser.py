"""Tests for the LTR property-manager report parser.

Phase 1 format is intentionally a clean, columnar text layout similar to
what most PM portals produce. Phase 2 will adapt this once the real PM's
exact report shape is known.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from taxauto.parsers.pm_ltr import PMEntry, parse_pm_ltr_text


SAMPLE_PM_REPORT = """\
ACME PROPERTY MANAGEMENT
Owner Statement — 123 Main St
Period: 01/01/2025 - 12/31/2025

Date        Description                          Category            Amount
01/05/2025  Rent Received - Tenant A              Rental Income        2,500.00
02/05/2025  Rent Received - Tenant A              Rental Income        2,500.00
02/15/2025  Plumbing Repair                       Repairs               -450.00
03/05/2025  Rent Received - Tenant A              Rental Income        2,500.00
03/31/2025  Management Fee (10%)                  Management Fee        -250.00
04/10/2025  HVAC Service                          Maintenance           -180.00

Total Income: 7,500.00
Total Expenses: -880.00
Net to Owner: 6,620.00
"""


def test_parses_all_pm_entries() -> None:
    result = parse_pm_ltr_text(SAMPLE_PM_REPORT, property_id="123 Main St")

    assert len(result.entries) == 6
    first = result.entries[0]
    assert isinstance(first, PMEntry)
    assert first.date == date(2025, 1, 5)
    assert first.description == "Rent Received - Tenant A"
    assert first.pm_category == "Rental Income"
    assert first.amount == Decimal("2500.00")
    assert first.property_id == "123 Main St"


def test_pm_totals_extracted_for_reconciliation() -> None:
    result = parse_pm_ltr_text(SAMPLE_PM_REPORT, property_id="123 Main St")

    assert result.total_income == Decimal("7500.00")
    assert result.total_expenses == Decimal("-880.00")
    assert result.net_to_owner == Decimal("6620.00")


def test_pm_reconciliation_matches_entries() -> None:
    result = parse_pm_ltr_text(SAMPLE_PM_REPORT, property_id="123 Main St")
    income_sum = sum((e.amount for e in result.entries if e.amount > 0), Decimal("0"))
    expense_sum = sum((e.amount for e in result.entries if e.amount < 0), Decimal("0"))
    assert income_sum == result.total_income
    assert expense_sum == result.total_expenses


def test_ignores_unrelated_lines() -> None:
    noisy = SAMPLE_PM_REPORT + "\nQuestions? Call us at 555-1212.\nPage 1 of 1\n"
    result = parse_pm_ltr_text(noisy, property_id="123 Main St")
    assert len(result.entries) == 6
