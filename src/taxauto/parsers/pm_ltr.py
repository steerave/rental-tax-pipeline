"""Long-term rental property-manager report parser.

PM reports are pre-categorized — every line already has a PM-assigned category
(Rental Income, Repairs, Management Fee, etc.). The parser keeps that category
verbatim as ``pm_category`` so the LTR writer can map PM categories to
accountant template categories in a single step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional, Sequence

# Default category vocabulary used when parsing text whose column separators
# have collapsed to single spaces (e.g., after pdfplumber extraction).
# Phase 2 will replace this with a config-driven list per PM.
DEFAULT_PM_CATEGORIES: List[str] = [
    "Rental Income",
    "Repairs",
    "Maintenance",
    "Management Fee",
    "Owner Draw",
    "Utilities",
    "Insurance",
    "Property Tax",
    "Cleaning",
    "Legal",
]


@dataclass(frozen=True)
class PMEntry:
    date: date
    description: str
    pm_category: str
    amount: Decimal
    property_id: str


@dataclass
class ParsedPMReport:
    entries: List[PMEntry] = field(default_factory=list)
    total_income: Optional[Decimal] = None
    total_expenses: Optional[Decimal] = None
    net_to_owner: Optional[Decimal] = None
    property_id: Optional[str] = None


# Date MM/DD/YYYY, Description (lazy), Category (one or more words), Amount.
# Category is the last "word-group" (letters/spaces/()%) before the amount.
_PM_LINE = re.compile(
    r"""
    ^\s*
    (?P<month>0?[1-9]|1[0-2])/(?P<day>0?[1-9]|[12][0-9]|3[01])/(?P<year>\d{4})
    \s+
    (?P<description>.+?)
    \s{2,}
    (?P<category>[A-Za-z][A-Za-z0-9 ()%/&\-]*?)
    \s{2,}
    (?P<amount>-?\$?[\d,]+\.\d{2})
    \s*$
    """,
    re.VERBOSE,
)


def _to_decimal(raw: str) -> Decimal:
    return Decimal(raw.replace("$", "").replace(",", "").strip())


def _find_money(text: str, label_regex: str) -> Optional[Decimal]:
    m = re.search(label_regex + r"\s*:?\s*\$?(-?[\d,]+\.\d{2})", text, re.IGNORECASE)
    return _to_decimal(m.group(1)) if m else None


# Fallback regex used after PDF text extraction has collapsed columns into
# single-space-separated tokens. Captures the date, a "middle" blob, and the
# trailing amount; the middle is split into description + category using the
# known-categories list.
_PM_LINE_SINGLE = re.compile(
    r"""
    ^\s*
    (?P<month>0?[1-9]|1[0-2])/(?P<day>0?[1-9]|[12][0-9]|3[01])/(?P<year>\d{4})
    \s+
    (?P<middle>.+?)
    \s+
    (?P<amount>-?\$?[\d,]+\.\d{2})
    \s*$
    """,
    re.VERBOSE,
)


def _split_description_and_category(
    middle: str, known_categories: Sequence[str]
) -> Optional[tuple[str, str]]:
    """Return (description, category) by finding the longest known category
    that appears at the end of ``middle``. Returns None if nothing matches.
    """
    lowered = middle.lower()
    best: Optional[tuple[str, str]] = None
    for cat in known_categories:
        cat_lower = cat.lower()
        if lowered.endswith(cat_lower):
            description = middle[: -len(cat)].strip().rstrip("-").strip()
            if not description:
                continue
            if best is None or len(cat) > len(best[1]):
                best = (description, cat)
    return best


def parse_pm_ltr_text(
    text: str,
    *,
    property_id: str,
    known_categories: Optional[Sequence[str]] = None,
) -> ParsedPMReport:
    """Parse extracted text from a long-term rental PM statement.

    Tries the strict multi-space regex first (preserved column layout, e.g.
    raw text fixtures). Any line that doesn't match is retried with the
    single-space fallback regex + known-categories splitter — this is the
    path that handles pdfplumber-extracted text from real PM PDFs.
    """
    report = ParsedPMReport(property_id=property_id)

    report.total_income = _find_money(text, r"Total Income")
    report.total_expenses = _find_money(text, r"Total Expenses")
    report.net_to_owner = _find_money(text, r"Net to Owner")

    categories = list(known_categories) if known_categories is not None else DEFAULT_PM_CATEGORIES

    for line in text.splitlines():
        m = _PM_LINE.match(line)
        if m:
            try:
                txn_date = date(int(m.group("year")), int(m.group("month")), int(m.group("day")))
            except ValueError:
                continue
            report.entries.append(
                PMEntry(
                    date=txn_date,
                    description=m.group("description").strip(),
                    pm_category=m.group("category").strip(),
                    amount=_to_decimal(m.group("amount")),
                    property_id=property_id,
                )
            )
            continue

        m2 = _PM_LINE_SINGLE.match(line)
        if not m2:
            continue
        try:
            txn_date = date(int(m2.group("year")), int(m2.group("month")), int(m2.group("day")))
        except ValueError:
            continue
        split = _split_description_and_category(m2.group("middle").strip(), categories)
        if split is None:
            continue
        description, category = split
        report.entries.append(
            PMEntry(
                date=txn_date,
                description=description,
                pm_category=category,
                amount=_to_decimal(m2.group("amount")),
                property_id=property_id,
            )
        )

    return report
