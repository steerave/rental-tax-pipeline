"""Chase Ink Business credit card statement parser (account 1091).

Grounded in the discovery of 13 real 2024 statements for the Chase Ink
Business card ending 1091. See years/2024/intermediate/discovery_1091.md
for the format details.

Key quirks:
1. pdfplumber extracts Chase's underlined section headers with doubled
   letters (``AACCCCOOUUNNTT SSUUMMMMAARRYY``). The parser collapses these.
2. Every statement lists transactions for BOTH cardholders: 1091 (primary)
   and 1109 (co-user). Transactions stream in together inside the single
   ``ACCOUNT ACTIVITY`` section; the divider is the
   ``TRANSACTIONS THIS CYCLE (CARD xxxx)`` subtotal line that follows
   each cardholder's block. The parser uses a state machine where the
   initial current_card is ``1091`` and flips to ``1109`` when the 1091
   subtotal line is encountered.
3. Transaction dates are MM/DD with no year. The year is derived from the
   Opening/Closing Date line in ACCOUNT SUMMARY. When the period spans a
   year boundary (e.g. 12/07/24 - 01/06/25), December rows get the opening
   year and January rows get the closing year.
4. Sign convention: debits (purchases/fees) are bare positive numbers;
   credits (payments/refunds) have a leading minus. Trust the sign, not
   the word "Payment".
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from .chase_common import clean_chase_text


# --- Data structures ----------------------------------------------------

@dataclass(frozen=True)
class ChaseCreditTransaction:
    date: date
    description: str
    amount: Decimal  # positive = debit/purchase/fee, negative = credit/payment/refund
    cardholder_last4: str
    account: str


@dataclass
class ChaseCreditStatement:
    account: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    previous_balance: Optional[Decimal] = None
    new_balance: Optional[Decimal] = None
    payments_credits: Optional[Decimal] = None  # stored as negative magnitude (as printed)
    purchases_total: Optional[Decimal] = None
    cash_advances_total: Optional[Decimal] = None
    balance_transfers_total: Optional[Decimal] = None
    fees_charged: Optional[Decimal] = None
    interest_charged: Optional[Decimal] = None
    card_1091_cycle_total: Optional[Decimal] = None  # from TRANSACTIONS THIS CYCLE line
    card_1109_cycle_total: Optional[Decimal] = None
    transactions: List[ChaseCreditTransaction] = field(default_factory=list)


# --- Regexes ------------------------------------------------------------

# A transaction line: MM/DD <desc> <amount>
# Amount may have a leading minus (credit) and comma thousands separators.
_TXN_RE = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+(?P<desc>.+?)\s+(?P<amount>-?[\d,]*\.\d{2})\s*$"
)

# Opening/Closing Date MM/DD/YY - MM/DD/YY
_PERIOD_RE = re.compile(
    r"Opening/Closing Date\s+(\d{2})/(\d{2})/(\d{2})\s*-\s*(\d{2})/(\d{2})/(\d{2})"
)

# TRANSACTIONS THIS CYCLE (CARD xxxx) $amount[-]
_CYCLE_SUBTOTAL_RE = re.compile(
    r"TRANSACTIONS THIS CYCLE \(CARD (?P<card>\d{4})\)\s*\$?(?P<amount>[\d,]+\.\d{2})(?P<trailneg>-)?"
)

# Account summary field regexes. Each captures a signed decimal.
# Chase prints signs as `+$`, `-$`, or bare `$`.
_SUMMARY_FIELDS = {
    "previous_balance": re.compile(r"Previous Balance\s+([+-]?)\$(-?[\d,]+\.\d{2})"),
    "payments_credits": re.compile(r"Payment, Credits\s+([+-]?)\$(-?[\d,]+\.\d{2})"),
    "purchases_total": re.compile(r"Purchases\s+([+-]?)\$(-?[\d,]+\.\d{2})"),
    "cash_advances_total": re.compile(r"Cash Advances\s+([+-]?)\$(-?[\d,]+\.\d{2})"),
    "balance_transfers_total": re.compile(r"Balance Transfers\s+([+-]?)\$(-?[\d,]+\.\d{2})"),
    "fees_charged": re.compile(r"Fees Charged\s+([+-]?)\$(-?[\d,]+\.\d{2})"),
    "interest_charged": re.compile(r"Interest Charged\s+([+-]?)\$(-?[\d,]+\.\d{2})"),
    "new_balance": re.compile(r"New Balance\s+([+-]?)\$(-?[\d,]+\.\d{2})"),
}

# Noise substrings -- lines containing any of these are skipped entirely
# during transaction scanning (even if they have something that looks like
# MM/DD inside them, which they generally don't).
_NOISE_SUBSTRINGS = (
    "TRANSACTIONS THIS CYCLE",
    "INCLUDING PAYMENTS RECEIVED",
    "Year-to-Date",
    "Total fees charged",
    "Total interest charged",
    "2024 Totals",
    "Date of",
    "Merchant Name or Transaction Description",
)


# --- Helpers ------------------------------------------------------------

def _de_double(text: str) -> str:
    """Collapse Chase's doubled-letter underline headers.

    pdfplumber renders Chase's underlined section headers with each letter
    doubled, e.g., ``AACCCCOOUUNNTT SSUUMMMMAARRYY`` -> ``ACCOUNT SUMMARY``.
    We only apply this transform to lines that look like a doubled header:
    mostly uppercase letters and spaces, containing at least one run of
    two identical consecutive letters.

    Safe on mixed-case transaction lines (they are not modified because
    the uppercase-only guard rejects them).
    """
    out_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        # Only consider lines that are entirely uppercase letters, spaces,
        # and a limited set of punctuation that appears in Chase section
        # names like "ACCOUNT ACTIVITY (CONTINUED)".
        if (
            len(stripped) >= 4
            and re.fullmatch(r"[A-Z \-()]+", stripped)
            and re.search(r"([A-Z])\1", stripped)
        ):
            # Verify that EVERY alphabetic run in the line is a doubled
            # pair (Chase's rendering doubles every letter). Collapse only
            # if the line is pure doubled — this avoids mangling a
            # legitimate uppercase string that happens to contain one
            # doubled letter (e.g., "INTEREST" -> "INTREST").
            #
            # We evaluate the alphabetic CORE of each token (ignoring
            # punctuation like parentheses) so tokens such as
            # ``(CCOONNTTIINNUUEEDD)`` are correctly collapsed.
            words = stripped.split()
            if all(
                _is_pure_doubled(w) for w in words if _alpha_core(w)
            ):
                collapsed_words = [
                    _collapse_doubled(w) if _alpha_core(w) else w
                    for w in words
                ]
                leading = line[: len(line) - len(line.lstrip())]
                out_lines.append(leading + " ".join(collapsed_words))
                continue
        out_lines.append(line)
    return "\n".join(out_lines)


def _alpha_core(token: str) -> str:
    """Return only the alphabetic characters of a token, dropping punctuation.

    Used so that tokens like ``(CCOONNTTIINNUUEEDD)`` can be evaluated for
    pure-doubled-ness without their surrounding parentheses tripping the
    even-length / isalpha checks.
    """
    return "".join(c for c in token if c.isalpha())


def _is_pure_doubled(token: str) -> bool:
    """True iff the alphabetic CORE of ``token`` is a pure doubled pattern.

    A 'pure doubled' alphabetic string has even length and every letter
    appears in a consecutive same-letter pair, e.g. ``AACCCCOOUUNNTT``
    (ACCOUNT doubled) or the alphabetic core of ``(CCOONNTTIINNUUEEDD)``
    which is ``CCOONNTTIINNUUEEDD`` (CONTINUED doubled). This correctly
    returns False for words like ``INTEREST`` that merely contain a single
    natural double letter.
    """
    core = _alpha_core(token)
    if len(core) < 2 or len(core) % 2 != 0:
        return False
    return all(core[i] == core[i + 1] for i in range(0, len(core), 2))


def _collapse_doubled(token: str) -> str:
    """Collapse consecutive same-letter pairs in a token, preserving punctuation.

    ``AACCCCOOUUNNTT`` -> ``ACCOUNT``
    ``(CCOONNTTIINNUUEEDD)`` -> ``(CONTINUED)``
    Non-alphabetic characters are passed through untouched.
    """
    result: List[str] = []
    i = 0
    n = len(token)
    while i < n:
        if (
            i + 1 < n
            and token[i].isalpha()
            and token[i] == token[i + 1]
        ):
            result.append(token[i])
            i += 2
        else:
            result.append(token[i])
            i += 1
    return "".join(result)


def _to_decimal(raw: str) -> Decimal:
    """Parse a numeric string with optional leading sign and commas."""
    return Decimal(raw.replace(",", ""))


def _parse_period(text: str) -> tuple[Optional[date], Optional[date]]:
    m = _PERIOD_RE.search(text)
    if not m:
        return None, None
    mo1, d1, y1, mo2, d2, y2 = m.groups()
    start = date(2000 + int(y1), int(mo1), int(d1))
    end = date(2000 + int(y2), int(mo2), int(d2))
    return start, end


def _assign_year(
    mm: int,
    period_start: Optional[date],
    period_end: Optional[date],
) -> int:
    """Pick the calendar year for a MM/DD transaction using the period."""
    if period_start is None or period_end is None:
        # Best effort: fall back to today's year (shouldn't happen because
        # the parser guards above ensure the period is present).
        from datetime import datetime
        return datetime.now().year
    if period_start.year == period_end.year:
        return period_end.year
    # Period spans two calendar years. Use MM to disambiguate: rows with
    # MM >= period_start.month belong to the start year; rows with
    # MM <= period_end.month belong to the end year. (For Dec/Jan this is
    # unambiguous.)
    if mm >= period_start.month:
        return period_start.year
    return period_end.year


# --- Public entry point -------------------------------------------------

def parse_chase_credit(text: str, *, account_label: str) -> ChaseCreditStatement:
    """Parse a Chase Ink Business credit card statement text blob.

    Parameters
    ----------
    text:
        Full extracted text of the statement (all pages concatenated).
    account_label:
        Account label to store on every emitted transaction (e.g. ``CC-1091``).
    """
    if not text:
        raise ValueError("Chase credit parser: empty input text")

    # Parse the billing period from the RAW text first: clean_chase_text's
    # leaked-prefix cleanup is case-insensitive and eats the "Opening/Closing
    # Date " label because it looks like a leaked prefix before a date token.
    period_start, period_end = _parse_period(text)

    cleaned = clean_chase_text(text)
    cleaned = _de_double(cleaned)

    stmt = ChaseCreditStatement(
        account=account_label,
        period_start=period_start,
        period_end=period_end,
    )

    # Account summary fields
    for attr, rx in _SUMMARY_FIELDS.items():
        m = rx.search(cleaned)
        if not m:
            continue
        sign, raw = m.group(1), m.group(2)
        val = _to_decimal(raw)
        if sign == "-":
            val = -val
        setattr(stmt, attr, val)

    # Guard: if nothing in the summary block was parseable, fail loudly so
    # downstream reconcile guards don't silently see a blank statement.
    if all(
        getattr(stmt, attr) is None
        for attr in (
            "previous_balance",
            "payments_credits",
            "purchases_total",
            "cash_advances_total",
            "balance_transfers_total",
            "fees_charged",
            "interest_charged",
            "new_balance",
        )
    ):
        raise ValueError(
            f"Chase credit statement for account {account_label} has no "
            f"parseable ACCOUNT SUMMARY block — format may have changed or "
            f"text is truncated."
        )

    if period_start is None or period_end is None:
        raise ValueError(
            f"Chase credit statement for account {account_label} is missing "
            f"the Opening/Closing Date line — cannot assign years to "
            f"transactions."
        )

    # Walk the text line by line to extract transactions and per-card
    # cycle subtotals. Cardholder state: default to 1091 (primary card,
    # whose block always comes first). Flip to 1109 when we see the
    # 1091 TRANSACTIONS THIS CYCLE subtotal line. After the 1109
    # subtotal, reset to None so any trailing noise isn't attributed.
    current_card = "1091"
    transactions: List[ChaseCreditTransaction] = []

    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Per-card cycle subtotal line: record and flip state.
        sub_m = _CYCLE_SUBTOTAL_RE.search(line)
        if sub_m:
            card = sub_m.group("card")
            amt = _to_decimal(sub_m.group("amount"))
            if sub_m.group("trailneg"):
                amt = -amt
            if card == "1091":
                stmt.card_1091_cycle_total = amt
                current_card = "1109"
            elif card == "1109":
                stmt.card_1109_cycle_total = amt
                current_card = ""  # done
            continue  # never treat subtotal line as a transaction

        # Skip other noise lines before attempting transaction match.
        if any(noise in line for noise in _NOISE_SUBSTRINGS):
            continue

        # Attempt transaction match.
        m = _TXN_RE.match(line)
        if not m:
            continue

        if not current_card:
            warnings.warn(
                f"Chase credit parser: transaction-looking line encountered "
                f"after both cycle subtotals (no active cardholder): {line!r}",
                stacklevel=2,
            )
            continue

        date_part = m.group("date")
        desc = m.group("desc").strip()
        amount_raw = m.group("amount")
        try:
            amount = _to_decimal(amount_raw)
        except Exception:  # pragma: no cover
            warnings.warn(
                f"Chase credit parser: could not parse amount {amount_raw!r} "
                f"on line: {line!r}",
                stacklevel=2,
            )
            continue

        mm_str, dd_str = date_part.split("/")
        mm, dd = int(mm_str), int(dd_str)
        try:
            year = _assign_year(mm, period_start, period_end)
            txn_date = date(year, mm, dd)
        except ValueError:
            warnings.warn(
                f"Chase credit parser: invalid date {date_part!r} on line: {line!r}",
                stacklevel=2,
            )
            continue

        transactions.append(
            ChaseCreditTransaction(
                date=txn_date,
                description=desc,
                amount=amount,
                cardholder_last4=current_card,
                account=account_label,
            )
        )

    stmt.transactions = transactions
    return stmt
