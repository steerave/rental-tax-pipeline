"""Tests for the prior-year bootstrap learner."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl

from taxauto.bootstrap.learn_from_prior import (
    BootstrapReport,
    PriorEntry,
    match_and_learn,
    read_prior_entries_xlsx,
)
from taxauto.parsers.bank import Transaction


def _bank_txn(description: str, amount: str, day: int) -> Transaction:
    return Transaction(
        date=date(2024, 1, day),
        description=description,
        amount=Decimal(amount),
        balance=None,
        account="****1234",
    )


def _entry(description: str, amount: str, day: int, category: str) -> PriorEntry:
    return PriorEntry(
        date=date(2024, 1, day),
        description=description,
        amount=Decimal(amount),
        category=category,
    )


def test_match_and_learn_adds_new_vendor() -> None:
    bank = [_bank_txn("POS PURCHASE HOME DEPOT #123", "-150.25", 5)]
    prior = [_entry("Home Depot supplies", "-150.25", 5, "STR")]

    mapping: dict = {"vendors": {}}
    report = match_and_learn(bank, prior, mapping, year=2024)

    assert isinstance(report, BootstrapReport)
    assert report.matched == 1
    assert report.new_vendors_learned == 1
    assert report.ambiguous == 0

    from taxauto.categorize.mapper import normalize_vendor
    key = normalize_vendor("POS PURCHASE HOME DEPOT #123")
    assert key in mapping["vendors"]
    assert mapping["vendors"][key]["category"] == "STR"
    assert 2024 in mapping["vendors"][key]["learned_from"]


def test_match_and_learn_fuzzy_description_within_date_window() -> None:
    bank = [_bank_txn("ACH DEBIT COMCAST XFINITY", "-200.00", 10)]
    # Prior entry's description differs slightly and date is off by 2 days,
    # but within the default window.
    prior = [_entry("Comcast Xfinity internet", "-200.00", 12, "STR")]

    mapping: dict = {"vendors": {}}
    report = match_and_learn(bank, prior, mapping, year=2024, date_window_days=3)

    assert report.matched == 1


def test_match_and_learn_flags_ambiguous_across_categories() -> None:
    bank = [
        _bank_txn("AMAZON.COM", "-50.00", 3),
        _bank_txn("AMAZON.COM", "-75.00", 20),
    ]
    prior = [
        _entry("Amazon.com", "-50.00", 3, "STR"),
        _entry("Amazon.com", "-75.00", 20, "Personal"),
    ]
    mapping: dict = {"vendors": {}}
    report = match_and_learn(bank, prior, mapping, year=2024)

    from taxauto.categorize.mapper import normalize_vendor
    entry = mapping["vendors"][normalize_vendor("AMAZON.COM")]
    assert entry["ambiguous"] is True
    assert report.ambiguous >= 1


def test_unmatched_transactions_reported() -> None:
    bank = [_bank_txn("MYSTERY LLC", "-99.99", 7)]
    prior: list = []
    mapping: dict = {"vendors": {}}
    report = match_and_learn(bank, prior, mapping, year=2024)

    assert report.matched == 0
    assert report.unmatched_bank == 1


def test_read_prior_entries_xlsx(tmp_path: Path) -> None:
    path = tmp_path / "str_2024.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Expenses"
    ws.append(["Date", "Description", "Amount", "Category"])
    ws.append([date(2024, 1, 5), "Home Depot supplies", -150.25, "STR"])
    ws.append([date(2024, 1, 12), "Comcast Xfinity", -200.00, "STR"])
    wb.save(path)

    entries = read_prior_entries_xlsx(path)

    assert len(entries) == 2
    assert entries[0].description == "Home Depot supplies"
    assert entries[0].amount == Decimal("-150.25")
    assert entries[0].category == "STR"
