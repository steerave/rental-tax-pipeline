"""Tests for the Chase Ink Business credit card (account 1091) parser.

Statements contain TWO cardholders: 1091 (primary) and 1109 (co-user).
The parser uses a state machine driven by the per-card TRANSACTIONS THIS
CYCLE subtotal lines (not cardholder name headers, which appear after
each block in pdfplumber extraction order). The state machine flips to
1109 when the 1091 subtotal is seen and blanks after the 1109 subtotal.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from taxauto.parsers.chase_credit import (
    ChaseCreditStatement,
    ChaseCreditTransaction,
    parse_chase_credit,
)


FIXTURE = Path(__file__).parent / "fixtures" / "chase_credit" / "sample_feb_2024.txt"


@pytest.fixture()
def statement() -> ChaseCreditStatement:
    return parse_chase_credit(
        FIXTURE.read_text(encoding="utf-8"),
        account_label="CC-1091",
    )


def test_parses_account_summary(statement: ChaseCreditStatement) -> None:
    assert statement.previous_balance is not None
    assert statement.new_balance is not None
    assert statement.purchases_total is not None


def test_parses_billing_period(statement: ChaseCreditStatement) -> None:
    assert statement.period_start is not None
    assert statement.period_end is not None
    assert statement.period_end > statement.period_start


def test_transactions_attributed_to_correct_cardholder(statement: ChaseCreditStatement) -> None:
    card_1091 = [t for t in statement.transactions if t.cardholder_last4 == "1091"]
    card_1109 = [t for t in statement.transactions if t.cardholder_last4 == "1109"]
    assert len(card_1091) >= 1
    assert len(card_1109) >= 1


def test_debits_positive_credits_negative(statement: ChaseCreditStatement) -> None:
    """Chase prints debits as bare positive numbers and credits with a leading
    minus. Parser preserves the sign: positive = expense, negative = refund/payment."""
    debits = [t for t in statement.transactions if t.amount > 0]
    assert len(debits) >= 1


def test_cycle_subtotal_not_emitted_as_transaction(statement: ChaseCreditStatement) -> None:
    for t in statement.transactions:
        assert "TRANSACTIONS THIS CYCLE" not in t.description
        assert "Year-to-Date" not in t.description


def test_year_derived_from_billing_period(statement: ChaseCreditStatement) -> None:
    """MM/DD dates on transactions get the year from Opening/Closing Date."""
    assert all(
        t.date.year in (statement.period_start.year, statement.period_end.year)
        for t in statement.transactions
    )


def test_transaction_count_matches_card_subtotals_if_available(statement: ChaseCreditStatement) -> None:
    """If the parser captured per-card cycle totals, the number of parsed
    transactions per card should be at least 1. This is a soft invariant —
    the parser may not always capture subtotal counts, but we verify the
    per-card lists are non-empty."""
    card_1091_count = sum(1 for t in statement.transactions if t.cardholder_last4 == "1091")
    card_1109_count = sum(1 for t in statement.transactions if t.cardholder_last4 == "1109")
    assert card_1091_count + card_1109_count == len(statement.transactions)
    assert card_1091_count >= 1
    assert card_1109_count >= 1


def test_per_card_sum_matches_cycle_subtotal(statement: ChaseCreditStatement) -> None:
    """Strong cross-check invariant (analogous to the checking parser's
    instance-count check): summing each card's parsed transactions must
    equal the ``TRANSACTIONS THIS CYCLE (CARD xxxx)`` subtotal captured
    from the statement. The two values come from independent regex paths,
    so drift in either side is caught here."""
    card_1091_sum = sum(
        (t.amount for t in statement.transactions if t.cardholder_last4 == "1091"),
        Decimal("0"),
    )
    card_1109_sum = sum(
        (t.amount for t in statement.transactions if t.cardholder_last4 == "1109"),
        Decimal("0"),
    )
    assert statement.card_1091_cycle_total is not None
    assert statement.card_1109_cycle_total is not None
    assert card_1091_sum == statement.card_1091_cycle_total
    assert card_1109_sum == statement.card_1109_cycle_total


def test_year_boundary_dec_jan_split() -> None:
    """Statements spanning Dec 2024 → Jan 2025 must assign December
    transactions to 2024 and January transactions to 2025. Verified on
    the real 20250106 statement with 32 Dec and 1 Jan transactions during
    development; this test locks in the behavior with a synthetic fixture."""
    mini_statement = """\
AACCCCOOUUNNTT SSUUMMMMAARRYY
Previous Balance $100.00
Purchases +$30.00
New Balance $130.00
Opening/Closing Date 12/07/24 - 01/06/25

12/15 FOO MERCHANT 10.00
01/02 BAR MERCHANT 20.00
TRANSACTIONS THIS CYCLE (CARD 1091) $30.00
"""
    statement = parse_chase_credit(mini_statement, account_label="CC-1091")

    assert statement.period_start == date(2024, 12, 7)
    assert statement.period_end == date(2025, 1, 6)
    assert len(statement.transactions) == 2
    # December transaction -> 2024 (period start year)
    dec_txn = next(t for t in statement.transactions if t.date.month == 12)
    assert dec_txn.date == date(2024, 12, 15)
    # January transaction -> 2025 (period end year)
    jan_txn = next(t for t in statement.transactions if t.date.month == 1)
    assert jan_txn.date == date(2025, 1, 2)
