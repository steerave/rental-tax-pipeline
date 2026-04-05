"""Tests for the STR earnings source reader."""

from pathlib import Path
from decimal import Decimal

from taxauto.sources.str_sheets import STREarning, load_str_earnings_from_xlsx, total_net_payout_by_property


FIXTURE = Path(__file__).parent / "fixtures" / "str_sheets" / "str_earnings_2024.xlsx"


def test_loads_four_properties() -> None:
    earnings = load_str_earnings_from_xlsx(FIXTURE)
    properties = {e.property_name for e in earnings}
    assert "15 Belden" in properties
    assert "27 Farmstead Dr" in properties
    assert "20 Valleywood Ln" in properties
    assert "17 Oak Glen" in properties


def test_earning_has_expected_fields() -> None:
    earnings = load_str_earnings_from_xlsx(FIXTURE)
    first = earnings[0]
    assert isinstance(first, STREarning)
    assert first.stay_start is not None
    assert first.net_payout > Decimal("0")
    assert first.platform in ("Vrbo", "Airbnb")


def test_totals_per_property() -> None:
    earnings = load_str_earnings_from_xlsx(FIXTURE)
    totals = total_net_payout_by_property(earnings)
    assert "15 Belden" in totals
    # 765 + 540 + 675 = 1980
    assert totals["15 Belden"] == Decimal("1980")
    for total in totals.values():
        assert total > Decimal("0")
