"""Helpers shared by the Chase checking and credit card parsers.

The most important helper is ``clean_chase_text`` which fixes a pdfplumber
extraction artifact: Chase statements contain invisible text-layer anchors
like ``*start*summary`` and ``*end*deposits and additions`` that pdfplumber
splices into adjacent data lines. Without stripping, every section boundary
line is corrupted and transactions at section edges get lost.
"""

from __future__ import annotations

import re


# Matches a *start* or *end* anchor phrase. Anchor phrases use lowercase
# letters, digits, and spaces (observed: "deposits and additions",
# "electronic withdrawal", "checks paid section3", "daily ending balance2",
# "post summary message1"). Digits appear because the anchor tag includes
# the section sequence.
_ANCHOR = re.compile(r"\*(?:start|end)\*[a-z0-9][a-z0-9 ]*")

# After stripping an anchor from the start of a line, Chase also leaks
# single alphanumeric glyphs that were part of the underlying text glyph
# stream into the data line, e.g.:
#     "*end*electro0nic withdraw1al /29 01/29 Payment..."
# becomes
#     "electro0nic withdraw1al /29 01/29 Payment..."
# after anchor strip. We recover by removing any leading run of "leaked
# letter/digit tokens" on a line BEFORE the first real MM/DD date.
# Only applies to lines that actually contain a subsequent date — never
# touches legitimate header or narrative lines.
_LEAKED_PREFIX_BEFORE_DATE = re.compile(
    r"^[a-z0-9 /]*?(\d{2}/\d{2}\s)",
    re.MULTILINE | re.IGNORECASE,
)

# Page footer: "Page of" on one line, "<n> <N>" on the next.
_PAGE_FOOTER = re.compile(r"^Page of\s*\n\s*\d+\s+\d+\s*$", re.MULTILINE)

# Account number header that reprints on continuation pages.
_ACCOUNT_HEADER = re.compile(r"^Account Number:\s*\n\s*\d{10,}\s*$", re.MULTILINE)

# Period header that reprints on continuation pages (Chase glues "through"
# directly between the two dates without spaces).
_PERIOD_HEADER = re.compile(
    r"^[A-Z][a-z]+ \d{1,2}, \d{4}through[A-Z][a-z]+ \d{1,2}, \d{4}\s*$",
    re.MULTILINE,
)


def clean_chase_text(text: str) -> str:
    """Remove Chase's embedded anchor text, page footers, and repeated headers.

    Safe to call multiple times. Preserves transaction content verbatim.
    """
    if not text:
        return text

    # Pre-pass 1: strip anchors wherever they appear.
    cleaned = _ANCHOR.sub("", text)

    # Pre-pass 2: on lines that contain a MM/DD date, remove any leaked
    # lowercase/digit prefix that came from anchor glyph leakage.
    cleaned = _LEAKED_PREFIX_BEFORE_DATE.sub(r"\1", cleaned)

    # Pre-pass 3: strip page footers and repeated headers on continuation pages.
    cleaned = _PAGE_FOOTER.sub("", cleaned)
    cleaned = _ACCOUNT_HEADER.sub("", cleaned)
    cleaned = _PERIOD_HEADER.sub("", cleaned)

    # Collapse runs of blank lines that the strips may have created.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip() + "\n"
