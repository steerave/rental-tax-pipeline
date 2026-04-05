"""Vendor mapper.

Applies a vendor_mapping dict to a list of Transactions, bucketing each one
into auto-tagged, ambiguous (→ review), or unknown (→ review).

Normalization is critical: bank descriptions routinely contain store numbers,
POS prefixes, and noise that differ run-to-run for the same vendor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from taxauto.parsers.bank import Transaction


# Strip common bank-noise prefixes so the vendor key is stable across formats.
_NOISE_PREFIXES = (
    "pos purchase",
    "pos debit",
    "ach debit",
    "ach credit",
    "debit card purchase",
    "check card purchase",
    "wire out",
    "wire in",
    "deposit",
    "withdrawal",
)


def normalize_vendor(description: str) -> str:
    """Produce a stable, lowercase key for a vendor from a raw bank description.

    Steps:
      1. Lowercase.
      2. Strip known bank prefixes (POS PURCHASE, ACH DEBIT, etc.).
      3. Remove store / reference numbers (#123, *AB12C).
      4. Collapse whitespace and trim.
    """
    if description is None:
        return ""

    s = description.lower().strip()
    for prefix in _NOISE_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
            break

    # Remove "#123" style store numbers.
    s = re.sub(r"#\s*\w+", "", s)
    # Remove "*AB12C" style reference tails.
    s = re.sub(r"\*\s*\w+", "", s)
    # Remove standalone trailing digit/alnum tokens (e.g. "store 42").
    s = re.sub(r"\s+\d+\b", "", s)
    # Strip punctuation that isn't useful for identity.
    s = re.sub(r"[.,;:!?]", "", s)
    # Collapse whitespace.
    s = re.sub(r"\s+", " ", s).strip()
    return s


@dataclass
class TaggedTransaction:
    transaction: Transaction
    category: str
    confidence: float
    source: str  # "auto" | "ambiguous" | "unknown"


@dataclass
class MapperResult:
    auto_tagged: List[TaggedTransaction] = field(default_factory=list)
    ambiguous: List[TaggedTransaction] = field(default_factory=list)
    unknown: List[TaggedTransaction] = field(default_factory=list)

    @property
    def review_queue(self) -> List[TaggedTransaction]:
        return self.ambiguous + self.unknown


def categorize_transactions(
    transactions: Iterable[Transaction],
    vendor_mapping: Dict,
    *,
    min_confidence: float = 0.80,
) -> MapperResult:
    """Route each transaction into auto / ambiguous / unknown buckets."""
    vendors = (vendor_mapping or {}).get("vendors", {}) or {}
    result = MapperResult()

    for txn in transactions:
        key = normalize_vendor(txn.description)
        entry = vendors.get(key)

        if entry is None:
            result.unknown.append(
                TaggedTransaction(
                    transaction=txn,
                    category="",
                    confidence=0.0,
                    source="unknown",
                )
            )
            continue

        confidence = float(entry.get("confidence", 0.0))
        ambiguous = bool(entry.get("ambiguous", False))
        category = entry.get("category", "")

        if ambiguous or confidence < min_confidence or not category:
            result.ambiguous.append(
                TaggedTransaction(
                    transaction=txn,
                    category=category,
                    confidence=confidence,
                    source="ambiguous",
                )
            )
            continue

        result.auto_tagged.append(
            TaggedTransaction(
                transaction=txn,
                category=category,
                confidence=confidence,
                source="auto",
            )
        )

    return result
