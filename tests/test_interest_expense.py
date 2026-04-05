"""Tests for the interest expense YAML loader."""

from decimal import Decimal
from pathlib import Path

from taxauto.sources.interest_expense import load_interest_expense


def test_loads_year(tmp_path: Path) -> None:
    p = tmp_path / "ie.yaml"
    p.write_text("2024:\n  15 Belden: 5667.15\n  1015 39th St: 12000.00\n", encoding="utf-8")
    result = load_interest_expense(p, year=2024)
    assert result["15 Belden"] == Decimal("5667.15")
    assert result["1015 39th St"] == Decimal("12000.00")


def test_missing_file_returns_empty_dict(tmp_path: Path) -> None:
    assert load_interest_expense(tmp_path / "nope.yaml", year=2024) == {}


def test_missing_year_returns_empty_dict(tmp_path: Path) -> None:
    p = tmp_path / "ie.yaml"
    p.write_text("2023:\n  X: 100\n", encoding="utf-8")
    assert load_interest_expense(p, year=2024) == {}
