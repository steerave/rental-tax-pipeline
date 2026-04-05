"""Maps Rent QC categories to accountant template row labels."""

from __future__ import annotations

from typing import Dict, Optional

from taxauto.config import Config


def get_rentqc_mapping(cfg: Config) -> Dict[str, Optional[str]]:
    """Load the rentqc_to_ltr_template mapping from config."""
    raw = cfg.raw.get("rentqc_to_ltr_template", {}) or {}
    return {k: (v if v else None) for k, v in raw.items()}


def map_rentqc_category(
    rentqc_category: str,
    mapping: Dict[str, Optional[str]],
) -> Optional[str]:
    """Return the template row label for a Rent QC category.

    Returns None if the category is explicitly excluded (mapped to null)
    or not present in the mapping (unknown — should go to review queue).
    """
    if not rentqc_category:
        return None
    return mapping.get(rentqc_category)
