import argparse
import random
import subprocess
import sys
from pathlib import Path

# Add project root to path to allow importing engine module
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine import (
    generate_random_instruction,
    instruction_to_line,
    RedcodeInstruction,
    set_engine_config,
    execute_battle_with_sources,
    _require_config,
)
from evolverstage import load_configuration


def generate_random_warrior(length: int, arena: int) -> str:
    """Generates a random warrior of a given length."""
    lines = []
    for _ in range(length):
        instruction = generate_random_instruction(arena)
        lines.append(instruction_to_line(instruction, arena))
    return "".join(lines)

def run_battle(warrior1: str, warrior2: str, engine: str, seed: int):
    """Runs a battle between two warriors using the specified engine."""
    # This is a simplified setup for the stress test.
    # We'll use a single arena configuration.
    arena = 0
    era = 0

    config = _require_config()

    # Temporarily set the battle_engine in the config
    original_engine = config.battle_engine
    config.battle_engine = engine

    try:
        warriors, scores = execute_battle_with_sources(
            arena=arena,
            cont1=1,
            cont1_code=warrior1,
            cont2=2,
            cont2_code=warrior2,
            era=era,
            seed=seed,
        )
        # Ensure scores are returned in a consistent order (warrior 1, warrior 2)
        if warriors[0] == 2:
            scores.reverse()
        return scores
    finally:
        config.battle_engine = original_engine


def main():
    """Main function for the stress test."""
    parser = argparse.ArgumentParser(description="Stress-test redcode-worker against pMars.")
    parser.add_argument("--iterations", type=int, default=10000, help="Number of battles to run.")
    args = parser.parse_args()

    # Basic configuration for the engine
    config = load_configuration("settings.ini")
    set_engine_config(config)

    print("Stress test configuration:")
    print(f"  Coresize: {config.coresize_list[0]}")
    print(f"  Cycles: {config.cycles_list[0]}")
    print(f"  Processes: {config.processes_list[0]}")
    print(f"  Warrior length: {config.warlen_list[0]}")
    print(f"  Min distance: {config.wardistance_list[0]}")
    print("-" * 80)

    # Use the warrior length from the config for the first arena
    warrior_length = config.warlen_list[0]
    mismatches = 0
    for i in range(args.iterations):
        seed = random.randint(0, 2**31 - 1)

        warrior1 = generate_random_warrior(warrior_length, 0)
        warrior2 = generate_random_warrior(warrior_length, 0)

        scores_worker = run_battle(warrior1, warrior2, "internal", seed)
        scores_pmars = run_battle(warrior1, warrior2, "pmars", seed)

        if scores_worker != scores_pmars:
            mismatches += 1
            print(f"Mismatch found on iteration {i+1} with seed {seed}!")
            print("Warrior 1:")
            print(warrior1)
            print("Warrior 2:")
            print(warrior2)
            print(f"redcode-worker scores: {scores_worker}")
            print(f"pMars scores: {scores_pmars}")
            print("-" * 80)

        if (i + 1) % (args.iterations // 100) == 0:
            print(f"Completed {i+1}/{args.iterations} iterations with {mismatches} mismatches.")

    print(f"Stress test complete. Found {mismatches} mismatches in {args.iterations} iterations.")
    if mismatches > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
