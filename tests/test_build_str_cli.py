"""Tests for the build-str CLI subcommand wiring."""

import pytest
from unittest.mock import patch
from taxauto.cli import main


def test_build_str_subcommand_is_wired(tmp_path):
    """build-str subcommand dispatches to cmd_build_str."""
    config_yaml = tmp_path / "config.yaml"
    config_yaml.write_text(
        "templates:\n  str: ''\n  ltr: ''\n"
        "year_paths:\n"
        "  root: 'years/{year}'\n"
        "  bank_inputs: 'years/{year}/inputs'\n"
        "  pm_ltr_inputs: 'years/{year}/inputs'\n"
        "  pm_str_inputs: 'years/{year}/inputs'\n"
        "  intermediate: 'years/{year}/intermediate'\n"
        "  outputs: 'years/{year}/outputs'\n"
        "  review_log: 'years/{year}/review_log.json'\n",
        encoding="utf-8",
    )
    with patch("taxauto.cli.cmd_build_str", return_value=0) as mock_cmd:
        result = main(["--config", str(config_yaml), "build-str", "--year", "2025"])
    assert result == 0
    mock_cmd.assert_called_once()
    cfg_arg, year_arg = mock_cmd.call_args.args
    assert year_arg == 2025
