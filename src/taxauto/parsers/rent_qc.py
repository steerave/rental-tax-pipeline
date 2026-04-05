"""Rent QC owner statement parser.

Rent QC owner statements are multi-property PDFs where each property section
contains a transaction table with 8 columns:

    Date | Payee / Payer | Type | Reference | Description | Cash In | Cash Out | Balance

Plain ``page.extract_text()`` collapses the ``Cash In`` and ``Cash Out``
columns, so the parser uses ``page.extract_words()`` with x-coordinate
binning to recover the column structure. Transactions can wrap across
2-4 physical lines because both Payee and Description wrap independently.

See ``years/2024/intermediate/discovery_rentqc.md`` for the full format
discovery report, including the 28-category vocabulary, wrapping patterns,
unit-number enumeration, and reconciliation formulas.
"""

from __future__ import annotations

import re
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pdfplumber


# ---------------------------------------------------------------------------
# Category vocabulary (discovery report section 5) - 28 distinct categories.
# Order matters: longer strings first so the longest-match wins (e.g.
# "Repair (IA)" beats "Repair" if we ever added a bare "Repair").
# ---------------------------------------------------------------------------
KNOWN_CATEGORIES: List[str] = sorted(
    [
        "Rent Income",
        "Prepaid Rent",
        "Late Fee",
        "Laundry Income",
        "Security Deposits",
        "Security Deposits Clearing",
        "Management Fees",
        "Lawn and Snow Care",
        "Water",
        "Electricity & Gas",
        "Garbage and Recycling",
        "Pest Control",
        "Sewer",
        "Plumbing",
        "Carpet Cleaning",
        "HVAC (Heat, Ventilation, Air)",
        "Rental License",
        "Lease Fee",
        "Legal Expenses",
        "Maintenance Labor",
        "Repair (IA)",
        "Repair (IL)",
        "Cleaning (IA)",
        "Cleaning (IL)",
        "Supply and Materials",
        "Stock Materials",
        "Postage",
        "Owner Distributions / S corp Distributions",
    ],
    key=len,
    reverse=True,
)

# Canonical property names used as Gamgee LTR workbook sheet titles.
# Matched case-insensitively as substrings of the per-property header line
# (which looks like "SW 1015 39th St. Bettendorf - 1015 39th St., ...").
KNOWN_PROPERTY_MATCHERS: List[Tuple[str, str]] = [
    ("1015 39th", "1015 39th St"),
    ("1210", "1210 College Ave"),
    ("Lincoln", "308 S Lincoln Ave"),
]

# Default column x-coordinate boundaries, used for the consolidated summary
# section and as a fallback when a per-property header row cannot be read.
# Per-property boundaries are learned from the actual
# "Date | Payee / Payer | Type | Reference | Description | Cash In | Cash Out | Balance"
# header row of each property section, because the real Rent QC reports use
# slightly different x anchors per property (the 1210 College Ave section in
# particular pushes Description left to ~x=235, colliding with the default
# Reference column range).
DEFAULT_BOUNDS: "ColumnBounds" = None  # filled in below after ColumnBounds defined


@dataclass(frozen=True)
class ColumnBounds:
    date_max: float
    payee_max: float
    type_max: float
    ref_max: float
    desc_max: float
    cash_in_max: float
    cash_out_max: float

    def column_of(self, x0: float) -> str:
        if x0 < self.date_max:
            return "date"
        if x0 < self.payee_max:
            return "payee"
        if x0 < self.type_max:
            return "type"
        if x0 < self.ref_max:
            return "ref"
        if x0 < self.desc_max:
            return "desc"
        if x0 < self.cash_in_max:
            return "cash_in"
        if x0 < self.cash_out_max:
            return "cash_out"
        return "balance"


DEFAULT_BOUNDS = ColumnBounds(
    date_max=88,
    payee_max=148,
    type_max=182,
    ref_max=225,
    desc_max=450,
    cash_in_max=490,
    cash_out_max=528,
)


def _bounds_from_header(header_line: List[dict]) -> ColumnBounds:
    """Learn per-section column bounds from a Rent QC transactions header row.

    The header row contains the tokens: ``Date``, ``Payee``, ``/``, ``Payer``,
    ``Type``, ``Reference``, ``Description``, ``Cash``, ``In``, ``Cash``,
    ``Out``, ``Balance``. Each column's upper bound is taken as the x0 of the
    NEXT column's starting token, minus a small margin. This lets us bin
    wrap-line tokens robustly regardless of per-property x drift.
    """
    anchors: Dict[str, float] = {}
    for w in header_line:
        t = w["text"]
        x = w["x0"]
        if t == "Date" and "date" not in anchors:
            anchors["date"] = x
        elif t == "Payee" and "payee" not in anchors:
            anchors["payee"] = x
        elif t == "Type" and "type" not in anchors:
            anchors["type"] = x
        elif t == "Reference" and "ref" not in anchors:
            anchors["ref"] = x
        elif t == "Description" and "desc" not in anchors:
            anchors["desc"] = x
        elif t == "Cash" and "cash_in" not in anchors:
            anchors["cash_in"] = x
        elif t == "Cash":
            anchors["cash_out"] = x
        elif t == "Balance":
            anchors["balance"] = x

    required = ("date", "payee", "type", "ref", "desc", "cash_in", "cash_out", "balance")
    if not all(k in anchors for k in required):
        return DEFAULT_BOUNDS

    def mid(a: str, b: str) -> float:
        return (anchors[a] + anchors[b]) / 2.0

    # For the Description -> CashIn boundary, use a point much closer to
    # the CashIn header (90% of the gap) because description text commonly
    # stretches rightward to within a few points of the amount column. The
    # amount tokens themselves are right-aligned, so their x0 is always near
    # the header anchor for that column.
    desc_cash_in_boundary = anchors["desc"] + 0.9 * (anchors["cash_in"] - anchors["desc"])

    return ColumnBounds(
        date_max=mid("date", "payee"),
        payee_max=mid("payee", "type"),
        type_max=mid("type", "ref"),
        ref_max=mid("ref", "desc"),
        desc_max=desc_cash_in_boundary,
        cash_in_max=mid("cash_in", "cash_out"),
        cash_out_max=mid("cash_out", "balance"),
    )

DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
AMOUNT_RE = re.compile(r"^-?\d{1,3}(?:,\d{3})*\.\d{2}$")
PERIOD_RE = re.compile(
    r"([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})\s*-\s*([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})"
)

# Unit prefix pattern: numeric unit (101..304, 1210, 1212) or string tokens
# ("lower", "upper", "1/2 upper", "1/2 lower") then separator " - ".
UNIT_PREFIX_RE = re.compile(
    r"^(?P<unit>\d{3,4}|1/2\s+upper|1/2\s+lower|upper|lower)\s*-\s*(?P<rest>.+)$",
    re.IGNORECASE,
)

# Transfer descriptions are skipped by the category matcher (intra-owner moves).
TRANSFER_RE = re.compile(r"^Transfer\s+(to|from)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RentQCTransaction:
    date: date
    payee: str
    txn_type: str
    reference: Optional[str]
    description: str
    cash_in: Optional[Decimal]
    cash_out: Optional[Decimal]
    balance: Optional[Decimal]
    unit: Optional[str]
    category: Optional[str]


@dataclass
class RentQCProperty:
    name: str
    beginning_balance: Optional[Decimal] = None
    cash_in: Optional[Decimal] = None
    cash_out: Optional[Decimal] = None
    owner_disbursements: Optional[Decimal] = None
    ending_balance: Optional[Decimal] = None
    property_reserve: Optional[Decimal] = None
    prepayments: Optional[Decimal] = None
    net_owner_funds: Optional[Decimal] = None
    total_cash_in_printed: Optional[Decimal] = None
    total_cash_out_printed: Optional[Decimal] = None
    transactions: List[RentQCTransaction] = field(default_factory=list)


@dataclass
class RentQCReport:
    source_path: Path
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    consolidated_beginning: Optional[Decimal] = None
    consolidated_cash_in: Optional[Decimal] = None
    consolidated_cash_out: Optional[Decimal] = None
    consolidated_owner_disbursements: Optional[Decimal] = None
    consolidated_ending: Optional[Decimal] = None
    properties: List[RentQCProperty] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _parse_amount(text: str) -> Optional[Decimal]:
    if not text:
        return None
    cleaned = text.replace(",", "").replace("$", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_month_day(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s.strip(), "%b %d, %Y").date()
    except ValueError:
        return None


def _group_words_by_line(words: Iterable[dict]) -> List[Tuple[int, List[dict]]]:
    """Cluster words into lines by rounded top-y.

    Returns a list of ``(y, [words...])`` sorted by y ascending. Words in
    each line are sorted by ``x0`` ascending.
    """
    buckets: Dict[int, List[dict]] = defaultdict(list)
    for w in words:
        buckets[round(w["top"])].append(w)
    out: List[Tuple[int, List[dict]]] = []
    for y in sorted(buckets.keys()):
        out.append((y, sorted(buckets[y], key=lambda w: w["x0"])))
    return out


def _line_starts_with_date(line: List[dict]) -> Optional[date]:
    if not line:
        return None
    first = line[0]
    if first["x0"] >= DEFAULT_BOUNDS.date_max:
        return None
    m = DATE_RE.match(first["text"])
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def _line_text(line: List[dict]) -> str:
    return " ".join(w["text"] for w in line)


# ---------------------------------------------------------------------------
# Description parsing
# ---------------------------------------------------------------------------

def _extract_unit_and_category(description: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse ``{unit} - {category} - {details}`` or ``{category} - {details}``.

    Returns ``(unit_or_none, category_or_none)``. Matches category
    case-insensitively against the known list; longest match wins.
    """
    if not description:
        return None, None

    # Skip intra-owner transfer rows (no category).
    if TRANSFER_RE.match(description):
        return None, None

    remainder = description.strip()
    unit: Optional[str] = None

    m = UNIT_PREFIX_RE.match(remainder)
    if m:
        unit = re.sub(r"\s+", " ", m.group("unit").strip().lower())
        # Preserve "1/2 upper" etc. as lowercase strings, and numerics as-is.
        if unit.isdigit():
            unit = m.group("unit")
        remainder = m.group("rest").strip()

    # Longest-match category lookup at the start of the remainder.
    lowered = remainder.lower()
    for cat in KNOWN_CATEGORIES:
        cl = cat.lower()
        if lowered == cl or lowered.startswith(cl + " -") or lowered.startswith(cl + "-") or lowered == cl or lowered.startswith(cl + " "):
            return unit, cat

    return unit, None


# ---------------------------------------------------------------------------
# Page walker / state machine
# ---------------------------------------------------------------------------

def _looks_like_property_header(text: str) -> Optional[str]:
    """If a line text is a property section header, return the canonical name."""
    if not text.startswith("SW "):
        return None
    for needle, canonical in KNOWN_PROPERTY_MATCHERS:
        if needle.lower() in text.lower():
            return canonical
    return None


def _parse_summary_row(line: List[dict]) -> Optional[Tuple[str, Decimal]]:
    """If ``line`` is a ``Label ... Amount`` row from a Cash Summary block,
    return ``(lowercase_label, amount)``."""
    if not line:
        return None
    last = line[-1]
    amt = _parse_amount(last["text"])
    if amt is None:
        return None
    label_words = [w["text"] for w in line[:-1]]
    label = " ".join(label_words).strip().lower()
    if not label:
        return None
    return label, amt


def _apply_summary(prop: RentQCProperty, label: str, amount: Decimal) -> bool:
    mapping = {
        "beginning balance": "beginning_balance",
        "cash in": "cash_in",
        "cash out": "cash_out",
        "owner disbursements": "owner_disbursements",
        "ending cash balance": "ending_balance",
        "property reserve": "property_reserve",
        "prepayments": "prepayments",
        "net owner funds": "net_owner_funds",
    }
    attr = mapping.get(label)
    if attr is None:
        return False
    setattr(prop, attr, amount)
    return True


def _apply_consolidated(report: RentQCReport, label: str, amount: Decimal) -> bool:
    mapping = {
        "beginning balance": "consolidated_beginning",
        "cash in": "consolidated_cash_in",
        "cash out": "consolidated_cash_out",
        "owner disbursements": "consolidated_owner_disbursements",
        "ending cash balance": "consolidated_ending",
    }
    attr = mapping.get(label)
    if attr is None:
        return False
    setattr(report, attr, amount)
    return True


# ---------------------------------------------------------------------------
# Transaction assembly
# ---------------------------------------------------------------------------

def _bin_line(line: List[dict], bounds: ColumnBounds) -> Dict[str, List[str]]:
    """Bin a single physical line's words into columns by x-position."""
    bins: Dict[str, List[str]] = defaultdict(list)
    for w in line:
        bins[bounds.column_of(w["x0"])].append(w["text"])
    return bins


def _assemble_transaction(
    anchor_line: List[dict],
    context_lines: List[List[dict]],
    bounds: ColumnBounds,
) -> Optional[RentQCTransaction]:
    """Build a transaction from an anchor date-line plus 0+ context wrap lines.

    The anchor line carries the authoritative date, type, reference,
    description start, and amounts. Context lines are adjacent non-date lines
    (one or two above and below) used to gather wrapped Payee and Description
    continuations.
    """
    txn_date = _line_starts_with_date(anchor_line)
    if txn_date is None:
        return None

    # Start with anchor's bins.
    bins = _bin_line(anchor_line, bounds)

    # Merge in context lines. For each wrap line, the words fall into payee
    # or description columns (or occasionally type/ref for "receipt").
    for ctx in context_lines:
        cbins = _bin_line(ctx, bounds)
        for col, vals in cbins.items():
            bins[col].extend(vals)

    # Drop the leading date token from the date column.
    date_tokens = bins.get("date", [])
    if date_tokens and DATE_RE.match(date_tokens[0]):
        date_tokens = date_tokens[1:]
    bins["date"] = date_tokens

    payee = " ".join(bins.get("payee", [])).strip()
    txn_type = " ".join(bins.get("type", [])).strip()
    reference = " ".join(bins.get("ref", [])).strip() or None
    description = " ".join(bins.get("desc", [])).strip()

    cash_in_tokens = bins.get("cash_in", [])
    cash_out_tokens = bins.get("cash_out", [])
    balance_tokens = bins.get("balance", [])

    # Description text can spill rightward past the desc_max boundary into the
    # Cash In / Cash Out / Balance column bins. Use the LAST valid amount token
    # from each bin, since spilled description text appears earlier in the list
    # (lower x position) than the actual right-aligned amount.
    def _last_amount(tokens: list[str]) -> Optional[Decimal]:
        for tok in reversed(tokens):
            a = _parse_amount(tok)
            if a is not None:
                return a
        return None

    cash_in = _last_amount(cash_in_tokens)
    cash_out = _last_amount(cash_out_tokens)
    balance = _last_amount(balance_tokens)

    if cash_in is None and cash_out is None:
        warnings.warn(
            f"Rent QC row on {txn_date.isoformat()} has neither Cash In nor Cash Out; "
            f"description={description!r}"
        )
        return None

    unit, category = _extract_unit_and_category(description)

    return RentQCTransaction(
        date=txn_date,
        payee=payee,
        txn_type=txn_type,
        reference=reference,
        description=description,
        cash_in=cash_in,
        cash_out=cash_out,
        balance=balance,
        unit=unit,
        category=category,
    )


def _gather_property_transactions(
    lines: List[Tuple[int, List[dict]]],
    start_idx: int,
    bounds: ColumnBounds,
) -> Tuple[List[RentQCTransaction], Optional[Decimal], Optional[Decimal], int]:
    """Walk lines from ``start_idx`` onward collecting transactions until we
    hit a Total row, a new property header, or an appendix marker.

    Returns ``(transactions, total_cash_in, total_cash_out, end_idx)``.
    ``end_idx`` points at the line *after* the last consumed row.
    """
    transactions: List[RentQCTransaction] = []
    total_in: Optional[Decimal] = None
    total_out: Optional[Decimal] = None

    # First pass: find all date-line indices within this block.
    date_indices: List[int] = []
    end_idx = len(lines)
    for i in range(start_idx, len(lines)):
        y, line = lines[i]
        text = _line_text(line)

        if "Cash Flow - 12 Month" in text:
            end_idx = i
            break
        if _looks_like_property_header(text) is not None:
            end_idx = i
            break
        # Total row: first word "Total" at date column, then two amounts.
        if (
            line
            and line[0]["text"] == "Total"
            and line[0]["x0"] < bounds.date_max
            and len(line) >= 2
        ):
            amounts = [_parse_amount(w["text"]) for w in line[1:]]
            amounts = [a for a in amounts if a is not None]
            if len(amounts) >= 2:
                total_in = amounts[0]
                total_out = amounts[1]
            end_idx = i + 1
            break

        if _line_starts_with_date(line) is not None:
            date_indices.append(i)

    # Second pass: build transactions. For each date-line, collect context
    # lines between the previous date-line's y (or the block start) and the
    # next date-line's y (or the block end), excluding summary/header rows.
    # Context lines are lines within [prev_end, next_start) that do NOT start
    # with a date.
    for pos, di in enumerate(date_indices):
        _, anchor_line = lines[di]

        if pos > 0:
            prev_di = date_indices[pos - 1]
            ctx_start = prev_di + 1
        else:
            ctx_start = start_idx

        if pos + 1 < len(date_indices):
            next_di = date_indices[pos + 1]
            ctx_end = next_di
        else:
            ctx_end = end_idx

        context_lines: List[List[dict]] = []
        anchor_y = lines[di][0]
        for j in range(ctx_start, ctx_end):
            if j == di:
                continue
            y_j, ln_j = lines[j]
            if _line_starts_with_date(ln_j) is not None:
                continue
            # Skip column-header and "Beginning Cash Balance as of ..." /
            # "Ending Cash Balance" lines inside the transaction block.
            text_j = _line_text(ln_j)
            if text_j.startswith("Beginning Cash Balance as of"):
                continue
            if text_j.startswith("Ending Cash Balance"):
                continue
            if text_j.startswith("Date Payee"):
                continue
            # Only accept lines "adjacent" to the anchor (within ~4 rows up/down).
            # This prevents bleed from earlier/later transactions in very
            # dense sections. y values are in points, line spacing ~15pt,
            # so within ~30pt of the anchor.
            if abs(y_j - anchor_y) > 30:
                continue
            # Exclusively own a context line: if it is closer to another
            # date-line than to this one, let that one claim it.
            closest = di
            closest_dist = abs(y_j - anchor_y)
            for other in date_indices:
                if other == di:
                    continue
                d = abs(y_j - lines[other][0])
                if d < closest_dist:
                    closest_dist = d
                    closest = other
            if closest != di:
                continue
            context_lines.append(ln_j)

        txn = _assemble_transaction(anchor_line, context_lines, bounds)
        if txn is not None:
            transactions.append(txn)

    return transactions, total_in, total_out, end_idx


# ---------------------------------------------------------------------------
# Top-level parse
# ---------------------------------------------------------------------------

def parse_rent_qc_pdf(path: Path) -> RentQCReport:
    """Parse a Rent QC owner statement PDF into a :class:`RentQCReport`."""
    path = Path(path)
    report = RentQCReport(source_path=path)

    # Collect every page's grouped lines up front so the state machine can
    # walk one continuous stream.
    all_lines: List[Tuple[int, List[dict]]] = []
    page_appendix_cut: Optional[int] = None  # index into all_lines

    with pdfplumber.open(str(path)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            words = page.extract_words(
                keep_blank_chars=False, x_tolerance=2, y_tolerance=3
            )
            if not words:
                continue
            page_lines = _group_words_by_line(words)
            # Offset y-values per page so each page's lines are distinct
            # in the flattened stream (add 1000 * page_idx).
            offset = 10000 * (page_idx + 1)
            for y, ln in page_lines:
                all_lines.append((y + offset, ln))

    if not all_lines:
        raise ValueError(f"No extractable text in {path}")

    # --- Extract period from the header ---
    for _, ln in all_lines[:40]:
        text = _line_text(ln)
        m = PERIOD_RE.search(text)
        if m:
            report.period_start = _parse_month_day(m.group(1))
            report.period_end = _parse_month_day(m.group(2))
            break

    # --- Walk lines: consolidated summary, then per-property sections ---
    i = 0
    in_consolidated = False
    current_property: Optional[RentQCProperty] = None
    in_appendix = False  # latches True at the first "Cash Flow - 12 Month" / "Rent Roll" marker

    while i < len(all_lines):
        y, line = all_lines[i]
        text = _line_text(line)

        # Appendix markers: "Cash Flow - 12 Month" and "Rent Roll" both begin
        # the non-transactional appendix. Once seen, no further property
        # sections should be created and no further transactions consumed.
        # Each marker page repeats the property header in a different layout
        # ("Properties: SW ..."), so we rely on the marker rather than the
        # header text to know we are in the appendix.
        if "Cash Flow - 12 Month" in text or text.startswith("Rent Roll"):
            in_appendix = True
            current_property = None
            i += 1
            continue

        if in_appendix:
            i += 1
            continue

        if "Consolidated Summary" in text:
            in_consolidated = True
            i += 1
            continue

        # Property section header
        canonical = _looks_like_property_header(text)
        if canonical is not None:
            in_consolidated = False
            current_property = RentQCProperty(name=canonical)
            report.properties.append(current_property)
            i += 1
            continue

        # Summary rows (both consolidated and per-property use "Label ... Amount")
        summary = _parse_summary_row(line)
        if summary is not None:
            label, amount = summary
            if in_consolidated:
                if _apply_consolidated(report, label, amount):
                    i += 1
                    continue
            elif current_property is not None:
                if _apply_summary(current_property, label, amount):
                    i += 1
                    continue

        # Transactions table: anchored by the "Date Payee / Payer Type ..." header.
        if current_property is not None and text.startswith("Date Payee"):
            bounds = _bounds_from_header(line)
            txns, total_in, total_out, end_idx = _gather_property_transactions(
                all_lines, i + 1, bounds
            )
            current_property.transactions.extend(txns)
            current_property.total_cash_in_printed = total_in
            current_property.total_cash_out_printed = total_out
            i = end_idx
            continue

        i += 1

    if not report.properties:
        raise ValueError(f"No property sections found in Rent QC PDF {path}")

    return report
