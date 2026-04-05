"""Vendor-mapping learning module.

Loads/saves vendor_mapping.yaml and folds human review decisions back into it.
Whenever a vendor is seen with two different categories across time, it is
flagged as ambiguous so it will always be routed to review in future runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

import yaml

from .mapper import normalize_vendor


def load_vendor_mapping(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {"vendors": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "vendors" not in data or data["vendors"] is None:
        data["vendors"] = {}
    return data


def save_vendor_mapping(path: Path, mapping: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(mapping, f, sort_keys=True, allow_unicode=True)


def record_review_decisions(
    mapping: Dict[str, Any],
    decisions: Iterable[Dict[str, Any]],
    *,
    default_confidence: float = 0.9,
) -> Dict[str, Any]:
    """Fold a batch of human decisions into the vendor mapping.

    Each decision is a dict with at minimum:
        {"description": str, "category": str, "year": int}

    - New vendors are added with occurrences=1.
    - Repeated decisions with the same category increment occurrences.
    - Conflicting categories flip `ambiguous` to True; the stored category
      stays at whatever was seen first (informational only — ambiguous
      vendors are always routed to human review anyway).
    """
    vendors = mapping.setdefault("vendors", {})

    for decision in decisions:
        description = decision.get("description", "")
        category = decision.get("category", "")
        year = decision.get("year")
        if not description or not category:
            continue

        # "Skip" and "Split" are review outcomes, not categories to learn.
        if category in ("Skip", "Split"):
            continue

        key = normalize_vendor(description)
        if not key:
            continue

        entry = vendors.get(key)
        if entry is None:
            vendors[key] = {
                "category": category,
                "confidence": default_confidence,
                "occurrences": 1,
                "learned_from": [year] if year is not None else [],
                "ambiguous": False,
            }
            continue

        entry["occurrences"] = int(entry.get("occurrences", 0)) + 1
        learned_from = entry.setdefault("learned_from", [])
        if year is not None and year not in learned_from:
            learned_from.append(year)

        existing_category = entry.get("category", "")
        if existing_category and existing_category != category:
            entry["ambiguous"] = True

    return mapping
