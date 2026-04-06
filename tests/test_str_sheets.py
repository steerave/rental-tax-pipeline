"""Tests for the STR earnings source reader."""

from pathlib import Path
from decimal import Decimal

import pytest

from taxauto.sources.str_sheets import (
    STREarning,
    load_str_earnings_from_gsheets,
    load_str_earnings_from_xlsx,
    total_net_payout_by_property,
)


FIXTURE = Path(__file__).parent / "fixtures" / "str_sheets" / "str_earnings_2024.xlsx"
SA_PATH = Path("C:/Users/steerave/Desktop/Claude Projects/Job Search Tool/service_account.json")


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


# --- Live Google Sheets tests (skipped if no service account) ---


@pytest.mark.skipif(not SA_PATH.exists(), reason="No service account available")
def test_live_sheets_reader_oak_glen() -> None:
    earnings = load_str_earnings_from_gsheets(
        {"17 Oak Glen": "16fbni_o58JYy8Htkf2xko5ecRKRqrNwa4XUoJILjSKM"},
        service_account_json=SA_PATH,
        year=2024,
    )
    total = sum(e.net_payout for e in earnings)
    # Should be close to the filed $34,411.38
    assert abs(total - Decimal("34411.38")) < Decimal("1.00"), (
        f"Oak Glen total {total} too far from filed $34,411.38"
    )
