"""Tests for the Chase Ink Business credit card (account 1091) parser.

Statements contain TWO cardholders: 1091 (primary) and 1109 (co-user).
The parser must attribute every transaction to the correct cardholder
via a state machine that toggles on the cardholder name lines.
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
