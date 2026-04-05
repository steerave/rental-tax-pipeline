"""Tests for the eCheck-reference LTR double-count guard."""

from datetime import date
from decimal import Decimal

import pytest

from taxauto.guards.double_count import (
    DoubleCountCollision,
    DoubleCountError,
    detect_double_counts,
)
from taxauto.parsers.chase_checking import ChaseTransaction
from taxauto.parsers.rent_qc import RentQCTransaction


def _bank(desc: str, amount: str, day: int = 16) -> ChaseTransaction:
    return ChaseTransaction(
        date=date(2024, 1, day), description=desc,
        amount=Decimal(amount), account="XXXX9999", section="deposits",
    )


def _rqc(ref: str, cash_out: str, day: int = 12) -> RentQCTransaction:
    return RentQCTransaction(
        date=date(2024, 1, day), payee="Sample Holdings LLC",
        txn_type="eCheck", reference=ref,
        description="Owner Distributions / S corp Distributions - Owner payment for 01/2024",
        cash_in=None, cash_out=Decimal(cash_out), balance=None,
        unit=None, category="Owner Distributions / S corp Distributions",
    )


def test_detects_collision_by_echeck_reference_and_sum() -> None:
    bank = [_bank("Orig CO Name:Rent Qc, LLC Ind Name:Sample Holdings LLC", "6962.38")]
    rqc = [_rqc("65D1-A640", "5827.53"), _rqc("65D1-A640", "12.85"), _rqc("65D1-A640", "1122.00")]
    # 5827.53 + 12.85 + 1122.00 = 6962.38

    collisions = detect_double_counts(bank, rqc)

    assert len(collisions) == 1
    assert collisions[0].echeck_reference == "65D1-A640"
    assert collisions[0].rentqc_sum == Decimal("6962.38")


def test_no_collision_when_amounts_dont_sum() -> None:
    bank = [_bank("Orig CO Name:Rent Qc, LLC", "9999.99")]
    rqc = [_rqc("65D1-A640", "100.00"), _rqc("65D1-A640", "200.00")]

    collisions = detect_double_counts(bank, rqc)
    assert collisions == []


def test_no_collision_when_description_not_rent_qc() -> None:
    bank = [_bank("Orig CO Name:Airbnb 4977", "6962.38")]
    rqc = [_rqc("65D1-A640", "5827.53"), _rqc("65D1-A640", "12.85"), _rqc("65D1-A640", "1122.00")]

    collisions = detect_double_counts(bank, rqc)
    assert collisions == []


def test_raise_mode() -> None:
    bank = [_bank("Orig CO Name:Rent Qc, LLC", "300.00")]
    rqc = [_rqc("ABCD-1234", "300.00")]

    with pytest.raises(DoubleCountError):
        detect_double_counts(bank, rqc, raise_on_found=True)
