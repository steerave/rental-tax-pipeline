"""Tests for the bank statement parser.

Phase 1 parses a synthetic but realistic text format. Phase 2 adapts to real
statements once we see them. The synthetic format below is intentionally close
to what most US bank statements look like after pdfplumber extraction:

    MM/DD  DESCRIPTION ... AMOUNT BALANCE

with optional signs, commas in numbers, and a header that carries summary
totals used for reconciliation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from taxauto.parsers.bank import Transaction, parse_bank_text


SAMPLE_STATEMENT = """\
ACME BANK - STATEMENT
Account: ****1234
Period: 01/01/2025 - 01/31/2025
Beginning Balance: $10,000.00
Ending Balance: $11,250.50
Total Deposits: $5,000.00
Total Withdrawals: $3,749.50

Date   Description                                  Amount    Balance
01/03  DEPOSIT PAYROLL ACME CORP                  2,500.00  12,500.00
01/05  POS PURCHASE HOME DEPOT #123                 -150.25  12,349.75
01/07  ACH DEBIT ACME PROPERTY MGMT              -1,200.00  11,149.75
01/15  DEPOSIT RENT 123 MAIN ST                   2,500.00  13,649.75
01/20  POS PURCHASE AMAZON.COM                      -399.25  13,250.50
01/28  ACH DEBIT COMCAST INTERNET                   -200.00  13,050.50
01/30  WIRE OUT PAYMENT TO ACCOUNTANT             -2,000.00  11,050.50
01/31  INTEREST CREDIT                                200.00  11,250.50
"""


def test_parses_all_transactions() -> None:
    result = parse_bank_text(SAMPLE_STATEMENT, account="****1234", statement_year=2025)

    assert len(result.transactions) == 8
    first = result.transactions[0]
    assert isinstance(first, Transaction)
    assert first.date == date(2025, 1, 3)
    assert first.description == "DEPOSIT PAYROLL ACME CORP"
    assert first.amount == Decimal("2500.00")
    assert first.balance == Decimal("12500.00")
    assert first.account == "****1234"


def test_negative_amounts_preserved() -> None:
    result = parse_bank_text(SAMPLE_STATEMENT, account="****1234", statement_year=2025)
    withdrawals = [t for t in result.transactions if t.amount < 0]
    assert len(withdrawals) == 5
    assert any("HOME DEPOT" in t.description for t in withdrawals)


def test_reconciliation_totals_extracted() -> None:
    result = parse_bank_text(SAMPLE_STATEMENT, account="****1234", statement_year=2025)

    assert result.beginning_balance == Decimal("10000.00")
    assert result.ending_balance == Decimal("11250.50")
    assert result.total_deposits == Decimal("5000.00")
    assert result.total_withdrawals == Decimal("3749.50")


def test_reconciliation_matches_transactions() -> None:
    """Sum of transactions should equal ending - beginning balance."""
    result = parse_bank_text(SAMPLE_STATEMENT, account="****1234", statement_year=2025)

    txn_sum = sum((t.amount for t in result.transactions), Decimal("0"))
    delta = result.ending_balance - result.beginning_balance
    assert txn_sum == delta


def test_ignores_non_transaction_lines() -> None:
    """Header and footer noise must not become transactions."""
    noisy = SAMPLE_STATEMENT + "\nPage 1 of 2\nThank you for banking with us.\n"
    result = parse_bank_text(noisy, account="****1234", statement_year=2025)
    assert len(result.transactions) == 8


def test_handles_year_rollover_across_december_january() -> None:
    """A statement spanning Dec/Jan should assign years based on month ordering."""
    text = """\
Beginning Balance: $100.00
Ending Balance: $200.00

12/28  DEPOSIT X    100.00  200.00
01/03  DEPOSIT Y    100.00  300.00
"""
    # Statement starts in 2024, rolls into 2025. We pass statement_year as the
    # period start year; parser should bump Jan rows into the next year.
    result = parse_bank_text(text, account="x", statement_year=2024)
    assert result.transactions[0].date == date(2024, 12, 28)
    assert result.transactions[1].date == date(2025, 1, 3)
