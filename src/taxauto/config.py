"""Configuration loader — reads config.yaml and .env.

The loader is intentionally a thin dataclass rather than a dict so callers
get IDE autocompletion and fail loudly on typos.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class YearPaths:
    """Resolved absolute paths for a single tax year."""

    root: Path
    inputs: Path
    bank_inputs: Path
    pm_ltr_inputs: Path
    pm_str_inputs: Path
    intermediate: Path
    outputs: Path
    review_log: Path


@dataclass
class Config:
    project_root: Path
    raw: dict

    template_str: Path
    template_ltr: Path

    _year_path_templates: dict = field(default_factory=dict)

    categories_primary: List[str] = field(default_factory=list)
    str_subcategories: List[str] = field(default_factory=list)
    ltr_subcategories: List[str] = field(default_factory=list)

    ltr_pm_name_contains: List[str] = field(default_factory=list)
    str_pm_name_contains: List[str] = field(default_factory=list)

    bootstrap_date_window_days: int = 3
    bootstrap_fuzzy_threshold: float = 0.72
    bootstrap_min_confidence: float = 0.80

    review_sheet_id: Optional[str] = None
    google_service_account_json: Optional[str] = None

    def paths_for_year(self, year: int) -> YearPaths:
        def resolve(template: str) -> Path:
            relative = Path(template.format(year=year))
            return (self.project_root / relative).resolve()

        # Derive inputs from root if not explicitly configured (backward compat).
        inputs_template = self._year_path_templates.get(
            "inputs",
            self._year_path_templates["root"] + "/inputs",
        )

        return YearPaths(
            root=resolve(self._year_path_templates["root"]),
            inputs=resolve(inputs_template),
            bank_inputs=resolve(self._year_path_templates["bank_inputs"]),
            pm_ltr_inputs=resolve(self._year_path_templates["pm_ltr_inputs"]),
            pm_str_inputs=resolve(self._year_path_templates["pm_str_inputs"]),
            intermediate=resolve(self._year_path_templates["intermediate"]),
            outputs=resolve(self._year_path_templates["outputs"]),
            review_log=resolve(self._year_path_templates["review_log"]),
        )


def load_config(
    config_path: Path,
    *,
    env_path: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> Config:
    """Load config.yaml and optionally a .env file.

    project_root defaults to the config file's parent directory.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    root = Path(project_root) if project_root else config_path.parent

    # Load .env (explicit path) or walk upward for a default .env
    if env_path is not None:
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        default_env = root / ".env"
        if default_env.exists():
            load_dotenv(dotenv_path=default_env, override=False)

    templates = raw.get("templates", {}) or {}
    year_paths = raw.get("year_paths", {}) or {}
    categories = raw.get("categories", {}) or {}
    pms = raw.get("property_managers", {}) or {}
    bootstrap = raw.get("bootstrap", {}) or {}

    return Config(
        project_root=root.resolve(),
        raw=raw,
        template_str=(root / templates.get("str", "")).resolve() if templates.get("str") else Path(),
        template_ltr=(root / templates.get("ltr", "")).resolve() if templates.get("ltr") else Path(),
        _year_path_templates=dict(year_paths),
        categories_primary=list(categories.get("primary", []) or []),
        str_subcategories=list(categories.get("str_subcategories", []) or []),
        ltr_subcategories=list(categories.get("ltr_subcategories", []) or []),
        ltr_pm_name_contains=list(((pms.get("ltr") or {}).get("name_contains") or [])),
        str_pm_name_contains=list(((pms.get("str") or {}).get("name_contains") or [])),
        bootstrap_date_window_days=int(bootstrap.get("date_window_days", 3)),
        bootstrap_fuzzy_threshold=float(bootstrap.get("description_fuzzy_threshold", 0.72)),
        bootstrap_min_confidence=float(bootstrap.get("min_confidence_to_auto_learn", 0.80)),
        review_sheet_id=os.environ.get("REVIEW_SHEET_ID"),
        google_service_account_json=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"),
    )
