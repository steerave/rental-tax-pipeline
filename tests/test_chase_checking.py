"""Tests for the Chase Business Complete Checking (account 7552) parser."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from taxauto.parsers.chase_checking import (
    ChaseCheckingStatement,
    ChaseTransaction,
    parse_chase_checking,
)


FIXTURE = Path(__file__).parent / "fixtures" / "chase_checking" / "sample_jan_2024.txt"


@pytest.fixture()
def statement() -> ChaseCheckingStatement:
    text = FIXTURE.read_text(encoding="utf-8")
    return parse_chase_checking(text, account_label="XXXX9999")


def test_parses_statement_period(statement: ChaseCheckingStatement) -> None:
    assert statement.period_start == date(2023, 12, 30)
    assert statement.period_end == date(2024, 1, 31)


def test_parses_checking_summary_totals(statement: ChaseCheckingStatement) -> None:
    assert statement.beginning_balance == Decimal("37969.40")
    assert statement.ending_balance is not None
    # Instance counts tracked for reconcile guard:
    assert statement.instance_counts["deposits"] is not None
    assert statement.instance_counts["checks_paid"] is not None
    assert statement.instance_counts["electronic_withdrawals"] is not None


def test_parses_deposits_section(statement: ChaseCheckingStatement) -> None:
    assert len(statement.deposits) >= 3
    vrbo = [t for t in statement.deposits if "Vrbo" in t.description]
    assert len(vrbo) >= 1
    first_vrbo = vrbo[0]
    assert first_vrbo.amount > Decimal("0")
    # The multi-line ACH block must be folded into one description.
    assert "Orig CO Name:Vrbo" in first_vrbo.description
    # Continuation fragments should have been joined:
    assert "Descr:Payment" in first_vrbo.description or "Ind Name" in first_vrbo.description


def test_parses_airbnb_deposit(statement: ChaseCheckingStatement) -> None:
    airbnb = [t for t in statement.deposits if "Airbnb" in t.description]
    assert len(airbnb) >= 1
    assert airbnb[0].amount > Decimal("0")


def test_parses_checks_paid_section(statement: ChaseCheckingStatement) -> None:
    assert len(statement.checks_paid) >= 1
    for t in statement.checks_paid:
        assert t.amount < Decimal("0")   # checks paid are withdrawals
        assert t.check_number is not None


def test_parses_electronic_withdrawals(statement: ChaseCheckingStatement) -> None:
    assert len(statement.electronic_withdrawals) >= 3
    # Single-line Online Payment
    online = [t for t in statement.electronic_withdrawals if "Online Payment" in t.description]
    assert len(online) >= 1
    # Multi-line ACH (any vendor)
    multiline = [t for t in statement.electronic_withdrawals if "Orig CO Name" in t.description]
    assert len(multiline) >= 1


def test_all_transactions_assigned_correct_year(statement: ChaseCheckingStatement) -> None:
    """Period ends in 2024, so every transaction's year must be 2024 (never 2023).
    Even if the period starts in Dec 2023, no real transactions posted on 12/30/23
    or 12/31/23 in this fixture."""
    all_txns = statement.deposits + statement.checks_paid + statement.electronic_withdrawals
    for t in all_txns:
        assert t.date.year == 2024


def test_transaction_has_account_label(statement: ChaseCheckingStatement) -> None:
    for t in statement.deposits:
        assert t.account == "XXXX9999"


def test_does_not_double_count_section_total_rows(statement: ChaseCheckingStatement) -> None:
    """The 'Total Deposits and Additions $X' subtotal line must NOT become a
    transaction row."""
    for t in statement.deposits:
        assert "Total Deposits" not in t.description
