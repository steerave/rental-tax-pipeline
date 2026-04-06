"""Tests for auto-skip logic that filters income deposits and CC payments."""

from datetime import date
from decimal import Decimal

from taxauto.parsers.chase_checking import ChaseTransaction


_INCOME_DEPOSIT_PATTERNS = ["airbnb", "vrbo", "rent qc", "etsy"]
_CC_SKIP_PATTERNS = ["payment thank you"]


def _should_skip_checking(t: ChaseTransaction) -> bool:
    return t.amount > 0 and any(
        p in t.description.lower() for p in _INCOME_DEPOSIT_PATTERNS
    )


def test_airbnb_deposit_skipped():
    t = ChaseTransaction(
        date=date(2024, 1, 2),
        description="Orig CO Name:Airbnb 4977 Descr:Airbnb",
        amount=Decimal("2176.10"),
        account="CHK",
        section="deposits",
    )
    assert _should_skip_checking(t)


def test_vrbo_deposit_skipped():
    t = ChaseTransaction(
        date=date(2024, 1, 2),
        description="Orig CO Name:Vrbo Orig ID:9872667522",
        amount=Decimal("5849.66"),
        account="CHK",
        section="deposits",
    )
    assert _should_skip_checking(t)


def test_rentqc_deposit_skipped():
    t = ChaseTransaction(
        date=date(2024, 1, 16),
        description="Orig CO Name:Rent Qc, LLC Descr:Sigonfile",
        amount=Decimal("4705.95"),
        account="CHK",
        section="deposits",
    )
    assert _should_skip_checking(t)


def test_etsy_deposit_skipped():
    t = ChaseTransaction(
        date=date(2024, 3, 5),
        description="Orig CO Name:Etsy Inc Descr:Deposit",
        amount=Decimal("120.00"),
        account="CHK",
        section="deposits",
    )
    assert _should_skip_checking(t)


def test_negative_airbnb_not_skipped():
    """Withdrawals/payments to these vendors should NOT be skipped."""
    t = ChaseTransaction(
        date=date(2024, 1, 5),
        description="Online Payment to Airbnb hosting fee",
        amount=Decimal("-50.00"),
        account="CHK",
        section="electronic_withdrawals",
    )
    assert not _should_skip_checking(t)


def test_unrelated_deposit_not_skipped():
    t = ChaseTransaction(
        date=date(2024, 2, 1),
        description="Direct Deposit from Employer",
        amount=Decimal("5000.00"),
        account="CHK",
        section="deposits",
    )
    assert not _should_skip_checking(t)


def test_cc_payment_thank_you_skipped():
    desc = "Payment Thank You - Web"
    assert any(p in desc.lower() for p in _CC_SKIP_PATTERNS)


def test_cc_normal_transaction_not_skipped():
    desc = "AMAZON.COM*1234 SEATTLE WA"
    assert not any(p in desc.lower() for p in _CC_SKIP_PATTERNS)
