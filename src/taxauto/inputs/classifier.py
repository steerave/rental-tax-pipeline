"""Classify input files by filename pattern.

Phase 2 decision: files are dropped directly into ``years/YYYY/inputs/``
without subfolders. The pipeline routes them to the right parser purely
by filename pattern. This keeps the "drop and go" workflow the user wants
and avoids a manual file-moving step each year.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Dict, List


class DocType(str, Enum):
    CHASE_CHECKING = "chase_checking"
    CHASE_CREDIT = "chase_credit"
    RENT_QC = "rent_qc"
    UNKNOWN = "unknown"


# Exact patterns from observed 2024 filenames.
_PATTERNS = [
    (re.compile(r"statements-7552", re.IGNORECASE), DocType.CHASE_CHECKING),
    (re.compile(r"statements-1091", re.IGNORECASE), DocType.CHASE_CREDIT),
    (re.compile(r"^rentqc-", re.IGNORECASE), DocType.RENT_QC),
    (re.compile(r"owner\s*packet", re.IGNORECASE), DocType.RENT_QC),
]


def classify_file(path: Path) -> DocType:
    """Return the DocType for a single file based on its filename."""
    name = Path(path).name
    for pattern, doc_type in _PATTERNS:
        if pattern.search(name):
            return doc_type
    return DocType.UNKNOWN


def classify_directory(directory: Path) -> Dict[DocType, List[Path]]:
    """Return a mapping of DocType → sorted list of matching files."""
    directory = Path(directory)
    groups: Dict[DocType, List[Path]] = {dt: [] for dt in DocType}
    if not directory.exists():
        return groups
    for entry in sorted(directory.iterdir()):
        if not entry.is_file():
            continue
        groups[classify_file(entry)].append(entry)
    return groups
