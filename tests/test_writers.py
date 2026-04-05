"""Tests for the STR and LTR Excel writers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl

from taxauto.categorize.mapper import TaggedTransaction
from taxauto.parsers.bank import Transaction
from taxauto.parsers.pm_ltr import PMEntry
from taxauto.writers.ltr_writer import write_ltr_workbook
from taxauto.writers.str_writer import write_str_workbook


def _blank_template(path: Path, sheet_title: str = "Expenses") -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(["Date", "Description", "Amount", "Category"])
    wb.save(path)
    return path


def _tagged(
    description: str,
    amount: str,
    day: int,
    category: str,
) -> TaggedTransaction:
    return TaggedTransaction(
        transaction=Transaction(
            date=date(2025, day, 1) if False else date(2025, 3, day),
            description=description,
            amount=Decimal(amount),
            balance=None,
            account="****1234",
        ),
        category=category,
        confidence=1.0,
        source="auto",
    )


def test_str_writer_fills_only_str_rows(tmp_path: Path) -> None:
    template = _blank_template(tmp_path / "str_template.xlsx")
    out = tmp_path / "str_2025.xlsx"

    tagged = [
        _tagged("HOME DEPOT", "-150.00", 5, "STR"),
        _tagged("COMCAST", "-100.00", 6, "LTR"),       # should be excluded
        _tagged("AIRBNB FEE", "-50.00", 7, "STR"),
        _tagged("GROCERY", "-80.00", 8, "Personal"),   # excluded
    ]

    write_str_workbook(template_path=template, output_path=out, tagged_transactions=tagged)

    assert out.exists()
    wb = openpyxl.load_workbook(out)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header, *data = rows
    assert header == ("Date", "Description", "Amount", "Category")
    assert len(data) == 2
    descs = {r[1] for r in data}
    assert descs == {"HOME DEPOT", "AIRBNB FEE"}


def test_str_writer_preserves_template(tmp_path: Path) -> None:
    template = _blank_template(tmp_path / "str_template.xlsx")
    out = tmp_path / "str_out.xlsx"
    write_str_workbook(template_path=template, output_path=out, tagged_transactions=[])
    # Template file should be unchanged.
    wb = openpyxl.load_workbook(template)
    assert list(wb.active.iter_rows(values_only=True)) == [
        ("Date", "Description", "Amount", "Category")
    ]


def test_ltr_writer_merges_pm_and_bank(tmp_path: Path) -> None:
    template = _blank_template(tmp_path / "ltr_template.xlsx")
    out = tmp_path / "ltr_2025.xlsx"

    tagged_bank = [
        _tagged("FURNITURE STORE", "-500.00", 10, "LTR"),
        _tagged("NOT LTR", "-50.00", 11, "STR"),  # excluded
    ]
    pm_entries = [
        PMEntry(
            date=date(2025, 3, 1),
            description="Rent Received",
            pm_category="Rental Income",
            amount=Decimal("2500.00"),
            property_id="123 Main St",
        ),
        PMEntry(
            date=date(2025, 3, 15),
            description="Plumbing Repair",
            pm_category="Repairs",
            amount=Decimal("-300.00"),
            property_id="123 Main St",
        ),
    ]

    write_ltr_workbook(
        template_path=template,
        output_path=out,
        tagged_transactions=tagged_bank,
        pm_entries=pm_entries,
    )

    wb = openpyxl.load_workbook(out)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))[1:]  # skip header
    assert len(rows) == 3  # 2 PM entries + 1 LTR bank txn
    descs = [r[1] for r in rows]
    assert "Rent Received" in descs
    assert "Plumbing Repair" in descs
    assert "FURNITURE STORE" in descs
    assert "NOT LTR" not in descs


def test_ltr_writer_drops_double_counts(tmp_path: Path) -> None:
    template = _blank_template(tmp_path / "ltr_template.xlsx")
    out = tmp_path / "ltr_2025.xlsx"

    # Bank transaction collides with a PM line (same amount, same date).
    tagged_bank = [_tagged("ACME PM DRAW", "1250.00", 5, "LTR")]
    pm_entries = [
        PMEntry(
            date=date(2025, 3, 5),
            description="Owner Draw",
            pm_category="Owner Draw",
            amount=Decimal("1250.00"),
            property_id="123 Main St",
        )
    ]

    write_ltr_workbook(
        template_path=template,
        output_path=out,
        tagged_transactions=tagged_bank,
        pm_entries=pm_entries,
    )

    wb = openpyxl.load_workbook(out)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))[1:]
    # Only the PM entry should remain; the bank duplicate must be dropped.
    assert len(rows) == 1
    assert rows[0][1] == "Owner Draw"
