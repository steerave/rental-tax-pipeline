"""STR platform earnings vs bank deposit totals reconciliation."""

from __future__ import annotations

from decimal import Decimal


class PlatformReconcileError(Exception):
    pass


def reconcile_str_platform_vs_bank(
    *,
    platform_total: Decimal,
    bank_str_deposits_total: Decimal,
    tolerance: Decimal = Decimal("500.00"),
) -> None:
    """Raise PlatformReconcileError if the STR platform total and bank deposit
    total diverge beyond tolerance."""
    delta = abs(platform_total - bank_str_deposits_total)
    if delta > tolerance:
        raise PlatformReconcileError(
            f"STR platform total {platform_total} vs bank STR deposits "
            f"{bank_str_deposits_total}: delta {delta} exceeds tolerance {tolerance}"
        )
