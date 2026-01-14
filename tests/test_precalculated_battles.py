import json
import pytest
import sys
from pathlib import Path

# Add project root to path to allow importing engine module
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine import (
    set_engine_config,
    execute_battle_with_sources,
    _require_config,
)
from evolverstage import load_configuration
from config import set_active_config

# Load the pre-calculated battle data
with open(PROJECT_ROOT / "precalculated_battles.json", "r") as f:
    BATTLE_DATA = [json.load(f)[1]]

# Basic configuration for the engine
config = load_configuration("settings.ini")
set_active_config(config)
set_engine_config(config)

@pytest.mark.parametrize("battle", BATTLE_DATA)
def test_precalculated_battle(battle):
    """
    Runs a battle with the internal worker and compares the result
    to the pre-calculated result from pMars.
    """
    config = _require_config()

    # Temporarily modify the config to use the battle's parameters
    original_config_lists = {
        "coresize_list": config.coresize_list,
        "cycles_list": config.cycles_list,
        "processes_list": config.processes_list,
        "warlen_list": config.warlen_list,
        "wardistance_list": config.wardistance_list,
    }

    params = battle["parameters"]
    config.coresize_list = [params["coresize"]]
    config.cycles_list = [params["cycles"]]
    config.processes_list = [params["processes"]]
    config.warlen_list = [params["warlen"]]
    config.wardistance_list = [params["wardistance"]]

    original_engine = config.battle_engine
    config.battle_engine = "internal"

    try:
        # Use arena=0, since we've modified the config lists to have one entry
        warriors, scores = execute_battle_with_sources(
            arena=0,
            cont1=1,
            cont1_code=battle["warrior1"],
            cont2=2,
            cont2_code=battle["warrior2"],
            era=0,
            seed=battle["seed"],
        )
        # Ensure scores are returned in a consistent order (warrior 1, warrior 2)
        if warriors[0] == 2:
            scores.reverse()

        assert scores == battle["scores"]
    finally:
        # Restore the original configuration
        config.battle_engine = original_engine
        config.coresize_list = original_config_lists["coresize_list"]
        config.cycles_list = original_config_lists["cycles_list"]
        config.processes_list = original_config_lists["processes_list"]
        config.warlen_list = original_config_lists["warlen_list"]
        config.wardistance_list = original_config_lists["wardistance_list"]
