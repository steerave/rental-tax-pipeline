"""Parser for Rent QC 'Cash Flow - 12 Month' summary pages.

Extracts per-property annual category totals from the appendix pages
of a Rent QC owner statement PDF. These totals are pre-computed by
Rent QC and match the accountant's filed values much more closely
than summing individual transactions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

import pdfplumber


_AMOUNT_RE = re.compile(r"-?[\d,]+\.\d{2}")


@dataclass
class CashFlowSummary:
    property_name: str
    period: str  # e.g., "Jan 2024 to Dec 2024"
    income: Dict[str, Decimal] = field(default_factory=dict)
    expenses: Dict[str, Decimal] = field(default_factory=dict)
    total_income: Optional[Decimal] = None
    total_expense: Optional[Decimal] = None
    net_income: Optional[Decimal] = None


def _is_cashflow_page(text: str) -> bool:
    """Detect whether a page is a Cash Flow 12-Month summary."""
    return "Cash Flow" in text and "12 Month" in text


def _extract_property_name(lines: list[str]) -> str:
    """Extract property name from the 'Properties:' line."""
    for line in lines:
        if line.startswith("Properties:"):
            # Format: "Properties:SW 1015 39th St. Bettendorf - 1015 39th St. Bettendorf, IA 52722"
            raw = line.split("Properties:", 1)[1].strip()
            # Take the part after " - " which has the clean address
            if " - " in raw:
                return raw.split(" - ", 1)[1].strip()
            return raw
    return ""


def _extract_period(lines: list[str]) -> str:
    """Extract period from the 'Period Range:' line."""
    for line in lines:
        if "Period Range:" in line:
            return line.split("Period Range:", 1)[1].strip()
    return ""


def _extract_total(line: str) -> Optional[Decimal]:
    """Extract the last numeric amount from a line (the Total column)."""
    amounts = _AMOUNT_RE.findall(line)
    if amounts:
        return Decimal(amounts[-1].replace(",", ""))
    return None


def _parse_cashflow_pages(page_texts: list[str]) -> CashFlowSummary:
    """Parse one property's Cash Flow pages (typically 2 pages) into a summary.

    Sections are tracked as:
      - 'income': between "Income" header and "Total Operating Income" (may wrap)
      - 'expense': between "Expense" header and "Total Operating Expense" (may wrap)
      - 'other': between "Other Items" and end
      - None: skip everything else

    Category names can wrap across lines. When a category wraps, the text-only
    continuation line(s) appear AFTER the data row. For example::

        HVAC (Heat, 0.00 0.00 ... 2,932.57
        Ventilation, Air)
        Lawn and Snow 337.50 525.00 ... 2,287.50
        Care

    So "Ventilation, Air)" is a suffix for "HVAC (Heat," and "Care" is a
    suffix for "Lawn and Snow". We handle this by tracking the last category
    key and retroactively renaming it when we encounter text-only continuation
    lines.
    """
    # Combine all page texts
    all_lines: list[str] = []
    for text in page_texts:
        all_lines.extend(text.split("\n"))

    # Extract metadata from first page
    prop_name = _extract_property_name(all_lines)
    period = _extract_period(all_lines)

    summary = CashFlowSummary(property_name=prop_name, period=period)

    section: Optional[str] = None  # 'income', 'expense', 'other', None
    # Track last category written so we can rename it if continuation lines follow
    last_cat_key: Optional[str] = None
    last_cat_section: Optional[str] = None

    # Lines to skip (headers, metadata, non-data)
    skip_prefixes = (
        "Cash Flow", "Rent QC", "Properties:", "Owned By:", "Period Range:",
        "Include Zero", "Account Name", "Created on", "Operating Income",
        "& Expense", "Beginning Cash", "Actual Ending",
    )

    for line in all_lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Skip header/metadata lines
        if any(stripped.startswith(p) for p in skip_prefixes):
            # "Cash Flow" with numbers is the summary row at bottom — skip it
            last_cat_key = None
            continue

        # Section transitions
        if stripped == "Income":
            section = "income"
            last_cat_key = None
            continue
        if stripped == "Expense":
            section = "expense"
            last_cat_key = None
            continue
        if stripped == "Other Items":
            section = "other"
            last_cat_key = None
            continue

        # Detect summary/total lines that end sections
        if stripped.startswith("Total Operating"):
            total_val = _extract_total(stripped)
            if section == "income" and total_val is not None:
                summary.total_income = total_val
            elif section == "expense" and total_val is not None:
                summary.total_expense = total_val
            last_cat_key = None
            continue

        if stripped.startswith("NOI - Net"):
            last_cat_key = None
            continue

        if stripped.startswith("Total Income"):
            total_val = _extract_total(stripped)
            if total_val is not None:
                summary.total_income = total_val
            section = None
            last_cat_key = None
            continue

        if stripped.startswith("Total Expense"):
            total_val = _extract_total(stripped)
            if total_val is not None:
                summary.total_expense = total_val
            section = None
            last_cat_key = None
            continue

        if stripped.startswith("Net Income"):
            total_val = _extract_total(stripped)
            if total_val is not None:
                summary.net_income = total_val
            section = None
            last_cat_key = None
            continue

        if stripped.startswith("Net Other Items"):
            last_cat_key = None
            continue

        if section is None:
            continue

        # Try to extract amounts from this line
        amounts = _AMOUNT_RE.findall(stripped)

        if amounts:
            # This line has numbers — extract category name (text before first number)
            first_match = _AMOUNT_RE.search(stripped)
            cat_name = stripped[:first_match.start()].strip() if first_match else ""

            if not cat_name:
                last_cat_key = None
                continue

            # Skip subtotal lines (e.g., "Total Repairs Cleaning",
            # "Total Utilities") to avoid double-counting with the
            # individual line items above them.
            if cat_name.lower().startswith("total "):
                last_cat_key = None
                continue

            total = Decimal(amounts[-1].replace(",", ""))

            if section == "income":
                summary.income[cat_name] = total
            elif section == "expense":
                summary.expenses[cat_name] = total
            # Track for potential continuation lines
            last_cat_key = cat_name
            last_cat_section = section
        else:
            # No numbers — this is a continuation of the PREVIOUS category name
            # or a section label fragment
            if stripped in ("Income", "Expense", "Operating"):
                # Fragment from wrapped "Total Operating Income/Expense" or
                # "NOI - Net Operating Income" — skip
                last_cat_key = None
                continue

            # Rename the last category key by appending this continuation text
            if last_cat_key and last_cat_section:
                new_key = f"{last_cat_key} {stripped}"
                target = (
                    summary.income if last_cat_section == "income"
                    else summary.expenses if last_cat_section == "expense"
                    else None
                )
                if target is not None and last_cat_key in target:
                    val = target.pop(last_cat_key)
                    target[new_key] = val
                    last_cat_key = new_key

    return summary


def parse_cashflow_summaries(pdf_path: Path) -> List[CashFlowSummary]:
    """Extract Cash Flow 12-Month summaries for all properties in the PDF."""
    summaries: List[CashFlowSummary] = []

    with pdfplumber.open(pdf_path) as pdf:
        # Collect pages belonging to each property's Cash Flow section.
        # First page of each property has "Properties:" line.
        # Subsequent continuation pages lack "Properties:" but still have
        # "Cash Flow - 12 Month" header.
        current_pages: list[str] = []

        for page in pdf.pages:
            text = page.extract_text() or ""
            if not _is_cashflow_page(text):
                # If we were collecting pages, flush them
                if current_pages:
                    summaries.append(_parse_cashflow_pages(current_pages))
                    current_pages = []
                continue

            # Check if this is a new property's first page
            if "Properties:" in text:
                # Flush previous property if any
                if current_pages:
                    summaries.append(_parse_cashflow_pages(current_pages))
                current_pages = [text]
            else:
                # Continuation page for current property
                current_pages.append(text)

        # Flush last property
        if current_pages:
            summaries.append(_parse_cashflow_pages(current_pages))

    return summaries
