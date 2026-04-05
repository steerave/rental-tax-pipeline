"""Tests for Chase text cleaning shared by checking and credit card parsers."""

from taxauto.parsers.chase_common import clean_chase_text


def test_strips_start_end_anchors() -> None:
    dirty = (
        "*start*summary\n"
        "CHECKING SUMMARY\n"
        "INSTANCES AMOUNT\n"
        "Beginning Balance $37,969.40\n"
        "*end*summary\n"
    )
    cleaned = clean_chase_text(dirty)
    assert "*start*" not in cleaned
    assert "*end*" not in cleaned
    assert "CHECKING SUMMARY" in cleaned
    assert "Beginning Balance $37,969.40" in cleaned


def test_recovers_anchor_spliced_into_data_line() -> None:
    # Observed in real Chase statements: anchors get glued onto data lines.
    dirty = "*end*electro0nic withdraw1al /29 01/29 Payment To Chase Card Ending IN 1091 3,464.28"
    cleaned = clean_chase_text(dirty)
    # The posting line should survive, with the anchor scrubbed.
    assert "01/29 Payment To Chase Card Ending IN 1091 3,464.28" in cleaned
    assert "*end*" not in cleaned
    assert "electronic" not in cleaned  # the glued-in letters are gone


def test_strips_page_footer() -> None:
    dirty = "some transaction line\nPage of\n2 6\nnext line\n"
    cleaned = clean_chase_text(dirty)
    assert "Page of" not in cleaned
    assert "some transaction line" in cleaned
    assert "next line" in cleaned


def test_strips_account_number_header_on_continuation_pages() -> None:
    dirty = (
        "December 30, 2023throughJanuary 31, 2024\n"
        "Account Number:\n"
        "000000398387552\n"
        "01/05 some txn 100.00\n"
    )
    cleaned = clean_chase_text(dirty)
    assert "Account Number:" not in cleaned
    assert "000000398387552" not in cleaned
    assert "01/05 some txn 100.00" in cleaned


def test_preserves_transaction_content() -> None:
    clean = "01/02 Orig CO Name:Vrbo Orig ID:9872667522 Desc Date:240102 CO Entry $5,849.66"
    assert clean_chase_text(clean).strip() == clean
