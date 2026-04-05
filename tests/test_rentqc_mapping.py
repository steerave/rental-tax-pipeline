from pathlib import Path

from taxauto.aggregate.rentqc_to_template import get_rentqc_mapping, map_rentqc_category
from taxauto.config import load_config


def test_mapping_from_real_config() -> None:
    """Test against the actual project config.yaml to verify the mapping loads."""
    cfg = load_config(Path("config.yaml"))
    mapping = get_rentqc_mapping(cfg)

    # Spot-check key mappings
    assert map_rentqc_category("Rent Income", mapping) == "Sales revenue"
    assert map_rentqc_category("Management Fees", mapping) == "Management Fees"
    assert map_rentqc_category("Repair (IA)", mapping) == "Repairs and Maintenance"
    assert map_rentqc_category("Supply and Materials", mapping) == "Supplies"
    assert map_rentqc_category("Lawn and Snow Care", mapping) == "Lawn and Snow Care"

    # Excluded categories return None
    assert map_rentqc_category("Owner Distributions / S corp Distributions", mapping) is None
    assert map_rentqc_category("Security Deposits", mapping) is None

    # Unknown category returns None
    assert map_rentqc_category("BRAND NEW CATEGORY", mapping) is None
