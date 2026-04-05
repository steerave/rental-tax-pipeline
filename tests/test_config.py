"""Tests for taxauto.config — YAML + dotenv loader and path resolution."""

from pathlib import Path

import pytest

from taxauto.config import Config, load_config


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_load_config_reads_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "config.yaml"
    write(
        yaml_path,
        """
templates:
  str: templates/str.xlsx
  ltr: templates/ltr.xlsx
year_paths:
  root: years/{year}
  bank_inputs: years/{year}/inputs/bank
  pm_ltr_inputs: years/{year}/inputs/pm_ltr
  pm_str_inputs: years/{year}/inputs/pm_str
  intermediate: years/{year}/intermediate
  outputs: years/{year}/outputs
  review_log: years/{year}/review_log.csv
categories:
  primary: [STR, LTR, Personal, Skip, Split]
  str_subcategories: []
  ltr_subcategories: []
property_managers:
  ltr:
    name_contains: [ACME PM]
  str:
    name_contains: []
bootstrap:
  date_window_days: 3
  description_fuzzy_threshold: 0.72
  min_confidence_to_auto_learn: 0.80
""",
    )

    cfg = load_config(yaml_path)

    assert isinstance(cfg, Config)
    assert cfg.categories_primary == ["STR", "LTR", "Personal", "Skip", "Split"]
    assert cfg.bootstrap_date_window_days == 3
    assert cfg.bootstrap_fuzzy_threshold == pytest.approx(0.72)
    assert cfg.ltr_pm_name_contains == ["ACME PM"]


def test_year_paths_substitute_year(tmp_path: Path) -> None:
    yaml_path = tmp_path / "config.yaml"
    write(
        yaml_path,
        """
templates: {str: t/s.xlsx, ltr: t/l.xlsx}
year_paths:
  root: years/{year}
  bank_inputs: years/{year}/inputs/bank
  pm_ltr_inputs: years/{year}/inputs/pm_ltr
  pm_str_inputs: years/{year}/inputs/pm_str
  intermediate: years/{year}/intermediate
  outputs: years/{year}/outputs
  review_log: years/{year}/review_log.csv
categories: {primary: [STR]}
property_managers: {ltr: {name_contains: []}, str: {name_contains: []}}
bootstrap: {date_window_days: 1, description_fuzzy_threshold: 0.5, min_confidence_to_auto_learn: 0.9}
""",
    )
    cfg = load_config(yaml_path, project_root=tmp_path)

    paths = cfg.paths_for_year(2025)

    assert paths.root == tmp_path / "years" / "2025"
    assert paths.bank_inputs == tmp_path / "years" / "2025" / "inputs" / "bank"
    assert paths.outputs == tmp_path / "years" / "2025" / "outputs"
    assert paths.review_log == tmp_path / "years" / "2025" / "review_log.csv"


def test_env_loading_picks_up_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("REVIEW_SHEET_ID=abc123\nGOOGLE_SERVICE_ACCOUNT_JSON=./sa.json\n", encoding="utf-8")
    # Ensure values don't leak from ambient env
    monkeypatch.delenv("REVIEW_SHEET_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)

    yaml_path = tmp_path / "config.yaml"
    write(
        yaml_path,
        """
templates: {str: t/s.xlsx, ltr: t/l.xlsx}
year_paths:
  root: y/{year}
  bank_inputs: y/{year}/b
  pm_ltr_inputs: y/{year}/pl
  pm_str_inputs: y/{year}/ps
  intermediate: y/{year}/i
  outputs: y/{year}/o
  review_log: y/{year}/r.csv
categories: {primary: [STR]}
property_managers: {ltr: {name_contains: []}, str: {name_contains: []}}
bootstrap: {date_window_days: 1, description_fuzzy_threshold: 0.5, min_confidence_to_auto_learn: 0.9}
""",
    )

    cfg = load_config(yaml_path, env_path=env_path, project_root=tmp_path)

    assert cfg.review_sheet_id == "abc123"
    assert cfg.google_service_account_json == "./sa.json"
