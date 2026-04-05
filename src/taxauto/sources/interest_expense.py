"""Per-property interest expense from YAML (sourced from Form 1098)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Dict

import yaml


def load_interest_expense(path: Path, *, year: int) -> Dict[str, Decimal]:
    """Load interest expense per property for the given year.

    Returns {} if the file doesn't exist or the year isn't present.
    """
    path = Path(path)
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    year_data = data.get(year) or {}
    return {str(k): Decimal(str(v)) for k, v in year_data.items()}
