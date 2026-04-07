"""Chase Business Complete Checking statement parser.

Grounded in the discovery of 12 real 2024 statements for account ...7552.
See years/2024/intermediate/discovery_7552.md for format details.

Design:
1. Parse the statement period from the RAW text (clean_chase_text strips the
   period-header lines, so we have to read it first).
2. Pre-clean text (strip anchors, page footers, repeated headers).
3. Parse CHECKING SUMMARY block -> 5 totals for reconciliation.
4. Slice the cleaned text into the fixed sections.
5. Within each transaction section, fold continuation lines into their
   posting-date line, then emit one ChaseTransaction per fold.
6. Return a structured ChaseCheckingStatement.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from .chase_common import clean_chase_text


MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


@dataclass(frozen=True)
class ChaseTransaction:
    date: date
    description: str
    amount: Decimal   # positive for deposits, negative for withdrawals
    account: str
    section: str      # "deposits", "checks_paid", "electronic_withdrawals"
    check_number: Optional[str] = None


@dataclass
class ChaseCheckingStatement:
    account: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    beginning_balance: Optional[Decimal] = None
    ending_balance: Optional[Decimal] = None
    total_deposits: Optional[Decimal] = None
    total_checks_paid: Optional[Decimal] = None
    total_electronic_withdrawals: Optional[Decimal] = None
    total_fees: Optional[Decimal] = None
    instance_counts: Dict[str, Optional[int]] = field(default_factory=lambda: {
        "deposits": None,
        "checks_paid": None,
        "electronic_withdrawals": None,
        "fees": None,
        "total": None,
    })
    deposits: List[ChaseTransaction] = field(default_factory=list)
    checks_paid: List[ChaseTransaction] = field(default_factory=list)
    electronic_withdrawals: List[ChaseTransaction] = field(default_factory=list)
    fees: List[ChaseTransaction] = field(default_factory=list)


# --- Regexes ------------------------------------------------------------

_PERIOD_RE = re.compile(
    r"([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})through([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})"
)

# Summary rows. Beginning Balance has no count. Others have a count. Amounts
# may be prefixed by `$` and may carry a leading minus sign.
_SUMMARY_ROW_RE = re.compile(
    r"^\s*(?P<label>Beginning Balance|Deposits and Additions|Checks Paid|"
    r"Electronic Withdrawals|Fees|Ending Balance)"
    r"(?:\s+(?P<count>\d+))?"
    r"\s+(?P<sign>-)?\$?(?P<amount>[\d,]+\.\d{2})\s*$"
)

# Transaction-start for DEPOSITS / ELECTRONIC WITHDRAWALS.
_TXN_RE = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+(?P<desc>.+?)\s+(?P<sign>-)?\$?(?P<amount>[\d,]+\.\d{2})\s*$"
)

# CHECKS PAID row. check_no first, optional `*^` or `^` marker, then MM/DD,
# then amount.
_CHECK_RE = re.compile(
    r"^(?P<checkno>\d{3,6})\s+(?:\*?\^\s+)?(?P<date>\d{2}/\d{2})\s+"
    r"\$?(?P<amount>[\d,]+\.\d{2})\s*$"
)

# Fallback for check lines where OCR dropped the check number.
# These start with `^ MM/DD amount` (no leading check number).
_CHECK_NO_NUM_RE = re.compile(
    r"^\*?\^\s+(?P<date>\d{2}/\d{2})\s+\$?(?P<amount>[\d,]+\.\d{2})\s*$"
)

# Noise lines to drop entirely before folding continuations.
_NOISE_EXACT = {
    "DEPOSITS AND ADDITIONS",
    "CHECKS PAID",
    "ELECTRONIC WITHDRAWALS",
    "FEES",
    "DATE DESCRIPTION AMOUNT",
    "DATE",
    "CHECK NO. DESCRIPTION PAID AMOUNT",
    "(continued)",
}

_TOTAL_LINE_RE = re.compile(
    r"^\s*Total\s+(Deposits and Additions|Checks Paid|Electronic Withdrawals|Fees)\s+\$?[\d,]+\.\d{2}\s*$"
)

# Section markers -- used to slice the cleaned text.
_SECTION_HEADERS = [
    "CUSTOMER SERVICE INFORMATION",
    "CHECKING SUMMARY",
    "DEPOSITS AND ADDITIONS",
    "CHECKS PAID",
    "ELECTRONIC WITHDRAWALS",
    "FEES",
    "DAILY ENDING BALANCE",
]


# --- Helpers ------------------------------------------------------------

def _to_decimal(raw: str, negative: bool = False) -> Decimal:
    val = Decimal(raw.replace(",", ""))
    return -val if negative else val


def _parse_period(raw_text: str) -> tuple[Optional[date], Optional[date]]:
    m = _PERIOD_RE.search(raw_text)
    if not m:
        return None, None
    mo1, d1, y1, mo2, d2, y2 = m.groups()
    start = date(int(y1), MONTHS[mo1], int(d1))
    end = date(int(y2), MONTHS[mo2], int(d2))
    return start, end


def _slice_sections(cleaned: str) -> Dict[str, str]:
    """Return a dict of section name -> section body text.

    We scan line-by-line for the known section headers. A section's body
    is everything between its header and the next recognized header (or EOF).
    """
    lines = cleaned.splitlines()
    # Find (line_index, header) in order.
    positions: List[tuple[int, str]] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        for hdr in _SECTION_HEADERS:
            if stripped == hdr:
                # Record only the FIRST occurrence of each header (dedupe
                # the reprints that follow `(continued)` on wrapped pages).
                if all(p[1] != hdr for p in positions):
                    positions.append((i, hdr))
                break
    positions.sort()
    sections: Dict[str, str] = {}
    for idx, (line_i, hdr) in enumerate(positions):
        end_i = positions[idx + 1][0] if idx + 1 < len(positions) else len(lines)
        body = "\n".join(lines[line_i + 1: end_i])
        sections[hdr] = body
    return sections


def _parse_summary(body: str) -> Dict[str, object]:
    out: Dict[str, object] = {}
    for line in body.splitlines():
        m = _SUMMARY_ROW_RE.match(line)
        if not m:
            continue
        label = m.group("label")
        count = m.group("count")
        sign = m.group("sign")
        amount = _to_decimal(m.group("amount"), negative=bool(sign))
        out[label] = {
            "count": int(count) if count else None,
            "amount": amount,
        }
    return out


def _clean_txn_lines(body: str) -> List[str]:
    """Drop noise lines and blank lines from a transaction-section body."""
    out: List[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in _NOISE_EXACT:
            continue
        if _TOTAL_LINE_RE.match(line):
            continue
        # Drop the occasional legal text left around CHECKS PAID.
        if line.startswith("If you see a description"):
            continue
        if line.startswith("not the original"):
            continue
        if line.startswith("* All of your recent checks"):
            continue
        if line.startswith("one of your previous statements"):
            continue
        out.append(line)
    return out


def _fold_continuations(lines: List[str], is_check_section: bool) -> List[str]:
    """Fold continuation lines into their preceding posting-date/check-number line."""
    folded: List[str] = []
    for line in lines:
        if is_check_section:
            is_start = bool(_CHECK_RE.match(line))
        else:
            is_start = bool(re.match(r"^\d{2}/\d{2}\s", line))
        if is_start or not folded:
            folded.append(line)
        else:
            folded[-1] = folded[-1] + " " + line
    return folded


def _parse_deposits_or_ew(
    body: str,
    year: int,
    account_label: str,
    section: str,
    negative: bool,
) -> List[ChaseTransaction]:
    """Parse DEPOSITS AND ADDITIONS or ELECTRONIC WITHDRAWALS.

    Strategy: parse the posting-date START line (which ends with the amount)
    via _TXN_RE to capture date/desc/amount, THEN append continuation lines
    to the description only. This avoids the fold-first pitfall where a
    multi-line ACH block ends on a trailing `...Tc` fragment and the amount
    is no longer at the end.
    """
    lines = _clean_txn_lines(body)
    out: List[ChaseTransaction] = []
    current: Optional[Dict[str, object]] = None

    def _flush() -> None:
        if current is None:
            return
        out.append(
            ChaseTransaction(
                date=current["date"],  # type: ignore[arg-type]
                description=current["desc"],  # type: ignore[arg-type]
                amount=current["amount"],  # type: ignore[arg-type]
                account=account_label,
                section=section,
            )
        )

    for line in lines:
        if re.match(r"^\d{2}/\d{2}\s", line):
            m = _TXN_RE.match(line)
            if not m:
                # Start-of-transaction line that did not fully parse.
                # Flush any in-progress transaction, then drop the current
                # pointer so subsequent continuation lines are NOT wrongly
                # appended to the previous transaction's description.
                warnings.warn(
                    f"Chase parser: line looks like a transaction start but "
                    f"failed regex match: {line!r}",
                    stacklevel=2,
                )
                _flush()
                current = None
                continue
            # Flush previous
            _flush()
            mm, dd = m.group("date").split("/")
            current = {
                "date": date(year, int(mm), int(dd)),
                "desc": m.group("desc").strip(),
                "amount": _to_decimal(m.group("amount"), negative=negative),
            }
        else:
            # Continuation line
            if current is not None:
                current["desc"] = f"{current['desc']} {line}"  # type: ignore[index]
    _flush()
    return out


def _parse_checks_paid(
    body: str, year: int, account_label: str
) -> List[ChaseTransaction]:
    # Checks are always single-line; do NOT fold. Folding would glue a
    # check row to any trailing disclosure-text fragment and break the
    # end-of-line amount match.
    lines = _clean_txn_lines(body)
    out: List[ChaseTransaction] = []
    for line in lines:
        m = _CHECK_RE.match(line)
        if m:
            mm, dd = m.group("date").split("/")
            txn_date = date(year, int(mm), int(dd))
            amt = _to_decimal(m.group("amount"), negative=True)
            out.append(
                ChaseTransaction(
                    date=txn_date,
                    description=f"Check #{m.group('checkno')}",
                    amount=amt,
                    account=account_label,
                    section="checks_paid",
                    check_number=m.group("checkno"),
                )
            )
            continue
        # Fallback: OCR dropped the check number (line starts with `^ MM/DD`)
        m2 = _CHECK_NO_NUM_RE.match(line)
        if m2:
            mm, dd = m2.group("date").split("/")
            txn_date = date(year, int(mm), int(dd))
            amt = _to_decimal(m2.group("amount"), negative=True)
            warnings.warn(
                f"Chase parser: check line missing check number, "
                f"inferred from context: {line!r}",
                stacklevel=2,
            )
            out.append(
                ChaseTransaction(
                    date=txn_date,
                    description="Check #(unknown)",
                    amount=amt,
                    account=account_label,
                    section="checks_paid",
                    check_number=None,
                )
            )
    return out


# --- Public entry point -------------------------------------------------

def parse_chase_checking(text: str, *, account_label: str) -> ChaseCheckingStatement:
    """Parse a Chase Business Complete Checking statement text blob."""
    # Capture period from raw text BEFORE the cleaner strips the header.
    period_start, period_end = _parse_period(text)
    if period_end is None:
        raise ValueError("Could not parse statement period from Chase checking text")
    year = period_end.year

    cleaned = clean_chase_text(text)
    sections = _slice_sections(cleaned)

    stmt = ChaseCheckingStatement(
        account=account_label,
        period_start=period_start,
        period_end=period_end,
    )

    # Summary
    if "CHECKING SUMMARY" in sections:
        summary = _parse_summary(sections["CHECKING SUMMARY"])
        if "Beginning Balance" in summary:
            stmt.beginning_balance = summary["Beginning Balance"]["amount"]  # type: ignore[index]
        if "Ending Balance" in summary:
            stmt.ending_balance = summary["Ending Balance"]["amount"]  # type: ignore[index]
            stmt.instance_counts["total"] = summary["Ending Balance"]["count"]  # type: ignore[index]
        if "Deposits and Additions" in summary:
            stmt.total_deposits = summary["Deposits and Additions"]["amount"]  # type: ignore[index]
            stmt.instance_counts["deposits"] = summary["Deposits and Additions"]["count"]  # type: ignore[index]
        if "Checks Paid" in summary:
            stmt.total_checks_paid = summary["Checks Paid"]["amount"]  # type: ignore[index]
            stmt.instance_counts["checks_paid"] = summary["Checks Paid"]["count"]  # type: ignore[index]
        if "Electronic Withdrawals" in summary:
            stmt.total_electronic_withdrawals = summary["Electronic Withdrawals"]["amount"]  # type: ignore[index]
            stmt.instance_counts["electronic_withdrawals"] = summary["Electronic Withdrawals"]["count"]  # type: ignore[index]
        if "Fees" in summary:
            stmt.total_fees = summary["Fees"]["amount"]  # type: ignore[index]
            stmt.instance_counts["fees"] = summary["Fees"]["count"]  # type: ignore[index]

    # Guard: if NONE of the 5 summary fields were populated, the CHECKING
    # SUMMARY block is missing entirely (format change or truncated text).
    # Downstream reconcile guards (Task 8) depend on these fields, so fail
    # loudly here rather than silently handing back an empty statement.
    if (stmt.beginning_balance is None
            and stmt.total_deposits is None
            and stmt.total_checks_paid is None
            and stmt.total_electronic_withdrawals is None
            and stmt.ending_balance is None):
        raise ValueError(
            f"Chase checking statement for account {account_label} has no "
            f"parseable CHECKING SUMMARY block — format may have changed or "
            f"text is truncated."
        )

    # Deposits (positive amounts)
    if "DEPOSITS AND ADDITIONS" in sections:
        stmt.deposits = _parse_deposits_or_ew(
            sections["DEPOSITS AND ADDITIONS"],
            year=year,
            account_label=account_label,
            section="deposits",
            negative=False,
        )

    # Checks Paid (negative)
    if "CHECKS PAID" in sections:
        stmt.checks_paid = _parse_checks_paid(
            sections["CHECKS PAID"],
            year=year,
            account_label=account_label,
        )

    # Electronic Withdrawals (negative)
    if "ELECTRONIC WITHDRAWALS" in sections:
        stmt.electronic_withdrawals = _parse_deposits_or_ew(
            sections["ELECTRONIC WITHDRAWALS"],
            year=year,
            account_label=account_label,
            section="electronic_withdrawals",
            negative=True,
        )

    # Fees (negative — e.g., monthly service fees, check supply orders)
    if "FEES" in sections:
        stmt.fees = _parse_deposits_or_ew(
            sections["FEES"],
            year=year,
            account_label=account_label,
            section="fees",
            negative=True,
        )

    return stmt
