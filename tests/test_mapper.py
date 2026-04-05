"""Tests for vendor categorization and learning."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

from taxauto.categorize.learning import (
    load_vendor_mapping,
    record_review_decisions,
    save_vendor_mapping,
)
from taxauto.categorize.mapper import (
    MapperResult,
    categorize_transactions,
    normalize_vendor,
)
from taxauto.parsers.bank import Transaction


def _txn(description: str, amount: str = "-100.00") -> Transaction:
    return Transaction(
        date=date(2025, 1, 15),
        description=description,
        amount=Decimal(amount),
        balance=None,
        account="****1234",
    )


# --- normalization --------------------------------------------------------


def test_normalize_strips_store_numbers_and_punctuation() -> None:
    assert normalize_vendor("POS PURCHASE HOME DEPOT #123") == normalize_vendor("home depot #456")
    assert normalize_vendor("AMAZON.COM*AB12C") == normalize_vendor("AMAZON.COM *XY99Z")


def test_normalize_collapses_whitespace_and_lowercases() -> None:
    assert normalize_vendor("  Comcast    Internet  ") == "comcast internet"


# --- mapper ---------------------------------------------------------------


def test_known_vendor_auto_tags() -> None:
    mapping = {
        "vendors": {
            normalize_vendor("HOME DEPOT"): {
                "category": "STR",
                "confidence": 0.95,
                "occurrences": 4,
                "learned_from": [2023, 2024],
                "ambiguous": False,
            }
        }
    }
    txns = [_txn("POS PURCHASE HOME DEPOT #123")]

    result = categorize_transactions(txns, mapping)

    assert isinstance(result, MapperResult)
    assert len(result.auto_tagged) == 1
    assert result.auto_tagged[0].category == "STR"
    assert result.unknown == []
    assert result.ambiguous == []


def test_ambiguous_vendor_routes_to_review() -> None:
    mapping = {
        "vendors": {
            normalize_vendor("COMCAST INTERNET"): {
                "category": "STR",
                "confidence": 0.6,
                "occurrences": 3,
                "learned_from": [2023, 2024],
                "ambiguous": True,
            }
        }
    }
    txns = [_txn("COMCAST INTERNET")]
    result = categorize_transactions(txns, mapping)

    assert len(result.ambiguous) == 1
    assert result.auto_tagged == []


def test_unknown_vendor_goes_to_unknown_bucket() -> None:
    mapping = {"vendors": {}}
    txns = [_txn("MYSTERIOUS LLC 42")]
    result = categorize_transactions(txns, mapping)

    assert len(result.unknown) == 1
    assert result.auto_tagged == []


def test_low_confidence_routes_to_review() -> None:
    mapping = {
        "vendors": {
            normalize_vendor("SHELL GAS"): {
                "category": "Personal",
                "confidence": 0.55,
                "occurrences": 1,
                "learned_from": [2024],
                "ambiguous": False,
            }
        }
    }
    txns = [_txn("SHELL GAS")]
    # Under the min_confidence threshold, should be routed to review.
    result = categorize_transactions(txns, mapping, min_confidence=0.80)
    assert len(result.ambiguous) == 1
    assert result.auto_tagged == []


# --- learning -------------------------------------------------------------


def test_load_and_save_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "vm.yaml"
    path.write_text("vendors: {}\n", encoding="utf-8")

    mapping = load_vendor_mapping(path)
    mapping["vendors"]["home depot"] = {
        "category": "STR",
        "confidence": 1.0,
        "occurrences": 1,
        "learned_from": [2023],
        "ambiguous": False,
    }
    save_vendor_mapping(path, mapping)

    reloaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert reloaded["vendors"]["home depot"]["category"] == "STR"


def test_record_review_decisions_learns_new_vendor(tmp_path: Path) -> None:
    path = tmp_path / "vm.yaml"
    path.write_text("vendors: {}\n", encoding="utf-8")
    mapping = load_vendor_mapping(path)

    decisions = [
        {"description": "WHOLE FOODS MARKET #1", "category": "Personal", "year": 2025},
        {"description": "WHOLE FOODS MARKET #2", "category": "Personal", "year": 2025},
    ]
    record_review_decisions(mapping, decisions)

    key = normalize_vendor("WHOLE FOODS MARKET")
    assert key in mapping["vendors"]
    entry = mapping["vendors"][key]
    assert entry["category"] == "Personal"
    assert entry["occurrences"] == 2
    assert 2025 in entry["learned_from"]
    assert entry["ambiguous"] is False


def test_record_review_decisions_flags_conflict_as_ambiguous() -> None:
    mapping = {"vendors": {}}
    decisions = [
        {"description": "COMCAST INTERNET", "category": "STR", "year": 2024},
        {"description": "COMCAST INTERNET", "category": "Personal", "year": 2025},
    ]
    record_review_decisions(mapping, decisions)

    entry = mapping["vendors"][normalize_vendor("COMCAST INTERNET")]
    assert entry["ambiguous"] is True
