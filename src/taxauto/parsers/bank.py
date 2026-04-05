"""Bank statement parser.

Normalizes a text-extracted bank statement into a list of Transaction records
plus statement-level totals used for reconciliation guards.

The line format assumed in Phase 1 is a common US-bank post-extraction shape:

    MM/DD  DESCRIPTION ... AMOUNT  BALANCE

Phase 2 will specialize this for the real statement format(s) seen in
production.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional


@dataclass(frozen=True)
class Transaction:
    date: date
    description: str
    amount: Decimal
    balance: Optional[Decimal]
    account: str


@dataclass
class ParsedStatement:
    transactions: List[Transaction] = field(default_factory=list)
    beginning_balance: Optional[Decimal] = None
    ending_balance: Optional[Decimal] = None
    total_deposits: Optional[Decimal] = None
    total_withdrawals: Optional[Decimal] = None
    account: Optional[str] = None


# Matches: 01/05  Description text here   -1,200.00   11,149.75
# Amount is required; balance is optional (some banks omit it on certain rows).
_TXN_LINE = re.compile(
    r"""
    ^\s*
    (?P<month>0?[1-9]|1[0-2])/(?P<day>0?[1-9]|[12][0-9]|3[01])   # MM/DD
    \s+
    (?P<description>.+?)                                          # description (lazy)
    \s+
    (?P<amount>-?\$?[\d,]+\.\d{2})                                # amount
    (?:\s+(?P<balance>-?\$?[\d,]+\.\d{2}))?                       # optional balance
    \s*$
    """,
    re.VERBOSE,
)


def _to_decimal(raw: str) -> Decimal:
    cleaned = raw.replace("$", "").replace(",", "").strip()
    return Decimal(cleaned)


def _find_money(line: str, label_regex: str) -> Optional[Decimal]:
    m = re.search(label_regex + r"\s*:?\s*\$?(-?[\d,]+\.\d{2})", line, re.IGNORECASE)
    if not m:
        return None
    return _to_decimal(m.group(1))


def parse_bank_text(
    text: str,
    *,
    account: str,
    statement_year: int,
) -> ParsedStatement:
    """Parse a bank statement's extracted text into structured transactions.

    ``statement_year`` is the calendar year the statement period starts in.
    Transactions whose month is earlier than the first seen month are assumed
    to belong to the following year (Dec/Jan rollover).
    """
    parsed = ParsedStatement(account=account)

    # Header-level totals. Scan the whole text once.
    parsed.beginning_balance = _find_money(text, r"Beginning Balance")
    parsed.ending_balance = _find_money(text, r"Ending Balance")
    parsed.total_deposits = _find_money(text, r"Total Deposits")
    parsed.total_withdrawals = _find_money(text, r"Total Withdrawals")

    first_month_seen: Optional[int] = None

    for line in text.splitlines():
        m = _TXN_LINE.match(line)
        if not m:
            continue

        month = int(m.group("month"))
        day = int(m.group("day"))

        if first_month_seen is None:
            first_month_seen = month
            year = statement_year
        else:
            # Rollover: if we see a month earlier than the first one, bump year.
            year = statement_year + 1 if month < first_month_seen else statement_year

        try:
            txn_date = date(year, month, day)
        except ValueError:
            # Invalid date (e.g. parser matched something wrong) — skip.
            continue

        amount = _to_decimal(m.group("amount"))
        balance_raw = m.group("balance")
        balance = _to_decimal(balance_raw) if balance_raw else None

        description = m.group("description").strip()
        # Collapse internal whitespace runs for stable vendor matching.
        description = re.sub(r"\s{2,}", " ", description)

        parsed.transactions.append(
            Transaction(
                date=txn_date,
                description=description,
                amount=amount,
                balance=balance,
                account=account,
            )
        )

    return parsed
