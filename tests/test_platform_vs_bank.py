from decimal import Decimal

import pytest

from taxauto.guards.platform_vs_bank import PlatformReconcileError, reconcile_str_platform_vs_bank


def test_passes_when_totals_match_within_tolerance() -> None:
    reconcile_str_platform_vs_bank(
        platform_total=Decimal("100000.00"),
        bank_str_deposits_total=Decimal("100050.00"),
        tolerance=Decimal("100.00"),
    )


def test_fails_when_totals_diverge() -> None:
    with pytest.raises(PlatformReconcileError):
        reconcile_str_platform_vs_bank(
            platform_total=Decimal("100000.00"),
            bank_str_deposits_total=Decimal("90000.00"),
            tolerance=Decimal("100.00"),
        )
