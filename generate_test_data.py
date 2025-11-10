import json
import random
import sys
from pathlib import Path

# Add project root to path to allow importing engine module
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine import (
    set_engine_config,
    execute_battle_with_sources,
    _require_config,
)
from evolverstage import load_configuration
from stress_test import generate_random_warrior


def generate_battle_data(num_battles: int, output_file: str):
    """Generates pre-calculated battle data and saves it to a file."""
    config = load_configuration("settings.ini")
    set_engine_config(config)

    battle_data = []
    num_arenas = len(config.coresize_list)

    for _ in range(num_battles):
        seed = random.randint(0, 2**31 - 1)

        # Randomly select an arena configuration
        arena_index = random.randint(0, num_arenas - 1)

        # Get parameters for the selected arena
        coresize = config.coresize_list[arena_index]
        cycles = config.cycles_list[arena_index]
        processes = config.processes_list[arena_index]
        warlen = config.warlen_list[arena_index]
        wardistance = config.wardistance_list[arena_index]
        readlimit = config.readlimit_list[arena_index]
        writelimit = config.writelimit_list[arena_index]

        # Generate warriors with the correct length for the arena
        warrior1 = generate_random_warrior(warlen, arena_index)
        warrior2 = generate_random_warrior(warlen, arena_index)

        # Temporarily modify the config to use only the selected parameters
        original_config_lists = {
            "coresize_list": config.coresize_list,
            "cycles_list": config.cycles_list,
            "processes_list": config.processes_list,
            "warlen_list": config.warlen_list,
            "wardistance_list": config.wardistance_list,
            "readlimit_list": config.readlimit_list,
            "writelimit_list": config.writelimit_list,
        }

        config.coresize_list = [coresize]
        config.cycles_list = [cycles]
        config.processes_list = [processes]
        config.warlen_list = [warlen]
        config.wardistance_list = [wardistance]
        config.readlimit_list = [readlimit]
        config.writelimit_list = [writelimit]

        original_engine = config.battle_engine
        config.battle_engine = "pmars"

        try:
            # Use arena=0, since we've modified the config lists to have one entry
            warriors, scores = execute_battle_with_sources(
                arena=0,
                cont1=1,
                cont1_code=warrior1,
                cont2=2,
                cont2_code=warrior2,
                era=0,
                seed=seed,
            )
            if warriors[0] == 2:
                scores.reverse()

            battle_data.append({
                "seed": seed,
                "warrior1": warrior1,
                "warrior2": warrior2,
                "scores": scores,
                "parameters": {
                    "coresize": coresize,
                    "cycles": cycles,
                    "processes": processes,
                    "warlen": warlen,
                    "wardistance": wardistance,
                    "readlimit": readlimit,
                    "writelimit": writelimit,
                }
            })
        finally:
            # Restore the original configuration
            config.battle_engine = original_engine
            config.coresize_list = original_config_lists["coresize_list"]
            config.cycles_list = original_config_lists["cycles_list"]
            config.processes_list = original_config_lists["processes_list"]
            config.warlen_list = original_config_lists["warlen_list"]
            config.wardistance_list = original_config_lists["wardistance_list"]
            config.readlimit_list = original_config_lists["readlimit_list"]
            config.writelimit_list = original_config_lists["writelimit_list"]

    with open(output_file, "w") as f:
        json.dump(battle_data, f, indent=2)

    print(f"Generated {num_battles} battles and saved to {output_file}")


if __name__ == "__main__":
    generate_battle_data(100, "precalculated_battles.json")
