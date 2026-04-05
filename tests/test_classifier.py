"""Tests for input file classification by filename pattern."""

from pathlib import Path

import pytest

from taxauto.inputs.classifier import DocType, classify_file, classify_directory


def test_classify_checking_statement() -> None:
    assert classify_file(Path("20240131-statements-7552-.pdf")) == DocType.CHASE_CHECKING


def test_classify_credit_card_statement() -> None:
    assert classify_file(Path("20240206-statements-1091-.pdf")) == DocType.CHASE_CREDIT


def test_classify_rentqc_report() -> None:
    assert classify_file(Path("rentqc-01 janfeb.pdf")) == DocType.RENT_QC
    assert classify_file(Path("rentqc-00 decjan.pdf")) == DocType.RENT_QC
    assert classify_file(Path("rentqc-12 decjan2.pdf")) == DocType.RENT_QC


def test_classify_unknown_file() -> None:
    assert classify_file(Path("random-document.pdf")) == DocType.UNKNOWN
    assert classify_file(Path("readme.txt")) == DocType.UNKNOWN


def test_classify_case_insensitive() -> None:
    assert classify_file(Path("RENTQC-01 JANFEB.PDF")) == DocType.RENT_QC
    assert classify_file(Path("20240131-Statements-7552-.pdf")) == DocType.CHASE_CHECKING


def test_classify_directory_groups_files(tmp_path: Path) -> None:
    for name in [
        "20240131-statements-7552-.pdf",
        "20240229-statements-7552-.pdf",
        "20240206-statements-1091-.pdf",
        "rentqc-01 janfeb.pdf",
        "rentqc-02 febmar.pdf",
        "stray.txt",
    ]:
        (tmp_path / name).touch()

    groups = classify_directory(tmp_path)

    assert len(groups[DocType.CHASE_CHECKING]) == 2
    assert len(groups[DocType.CHASE_CREDIT]) == 1
    assert len(groups[DocType.RENT_QC]) == 2
    assert len(groups[DocType.UNKNOWN]) == 1
    # Files are returned sorted for deterministic ordering.
    assert groups[DocType.CHASE_CHECKING] == sorted(groups[DocType.CHASE_CHECKING])
