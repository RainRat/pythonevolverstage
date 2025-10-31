"""Optuna-based hyperparameter optimization for evolverstage."""
from __future__ import annotations

import argparse
import configparser
import csv
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import optuna

REPO_ROOT = Path(__file__).resolve().parent
BASE_SETTINGS_PATH = REPO_ROOT / "settings.ini"
TRIAL_OUTPUT_ROOT = REPO_ROOT / "optuna_trials"
TUNING_ARENA_INDEX = 4
CLOCK_TIME_HOURS = 0.25

_ARENA_LIST_KEYS = [
    "CORESIZE_LIST",
    "SANITIZE_LIST",
    "READLIMIT_LIST",
    "WRITELIMIT_LIST",
    "CYCLES_LIST",
    "PROCESSES_LIST",
    "WARLEN_LIST",
    "WARDISTANCE_LIST",
    "SPEC_LIST",
    "ARENA_WEIGHT_LIST",
]

_PER_ERA_INT_SPACES = {
    "BATTLEROUNDS_LIST": (1, 200),
    "BENCHMARK_BATTLE_FREQUENCY_LIST": (0, 50),
    "CHAMPION_BATTLE_FREQUENCY_LIST": (0, 50),
    "RANDOM_PAIR_BATTLE_FREQUENCY_LIST": (0, 200),
    "ARCHIVE_LIST": (0, 10000),
    "UNARCHIVE_LIST": (0, 10000),
    "CROSSOVERRATE_LIST": (1, 40),
    "TRANSPOSITIONRATE_LIST": (1, 40),
    "NOTHING_LIST": (0, 40),
    "RANDOM_LIST": (0, 20),
    "NAB_LIST": (0, 20),
    "MINI_MUT_LIST": (0, 20),
    "MICRO_MUT_LIST": (0, 20),
    "LIBRARY_LIST": (0, 20),
    "MAGIC_NUMBER_LIST": (0, 20),
}

_PER_ERA_BOOL_KEYS = ["PREFER_WINNER_LIST"]


def _load_base_configuration() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.optionxform = str  # preserve case
    with BASE_SETTINGS_PATH.open("r", encoding="utf-8") as handle:
        parser.read_file(handle)
    return parser


_BASE_CONFIG = _load_base_configuration()
_BASE_DEFAULTS = _BASE_CONFIG["DEFAULT"]


def _parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _get_era_count() -> int:
    random_list = _parse_list(_BASE_DEFAULTS.get("RANDOM_LIST", ""))
    if not random_list:
        raise RuntimeError("Unable to determine era count from RANDOM_LIST in settings.ini")
    return len(random_list)


ERA_COUNT = _get_era_count()


def _get_arena_specific_value(key: str) -> str:
    values = _parse_list(_BASE_DEFAULTS.get(key, ""))
    if not values:
        raise RuntimeError(f"Missing list value for {key} in settings.ini")
    if TUNING_ARENA_INDEX >= len(values):
        raise RuntimeError(
            f"Arena index {TUNING_ARENA_INDEX} is out of range for {key} (length={len(values)})"
        )
    return values[TUNING_ARENA_INDEX]


def _suggest_per_era_ints(trial: optuna.trial.Trial, key: str, bounds: tuple[int, int]) -> list[int]:
    low, high = bounds
    values = []
    for era in range(ERA_COUNT):
        name = f"{key}_ERA{era + 1}"
        value = trial.suggest_int(name, low, high)
        values.append(value)
    return values


def _suggest_per_era_bools(trial: optuna.trial.Trial, key: str) -> list[bool]:
    values: list[bool] = []
    for era in range(ERA_COUNT):
        name = f"{key}_ERA{era + 1}"
        enabled = trial.suggest_int(name, 0, 1)
        values.append(bool(enabled))
    return values


def _set_list(config: configparser.ConfigParser, key: str, values: Iterable[object]) -> None:
    config["DEFAULT"][key] = ",".join(str(v) for v in values)


def _build_trial_configuration(trial: optuna.trial.Trial, run_dir: Path) -> Path:
    config = configparser.ConfigParser()
    config.optionxform = str
    config["DEFAULT"] = {}
    for key, value in _BASE_DEFAULTS.items():
        config["DEFAULT"][key] = value

    config["DEFAULT"]["LAST_ARENA"] = "0"
    for key in _ARENA_LIST_KEYS:
        config["DEFAULT"][key] = _get_arena_specific_value(key)

    for key, bounds in _PER_ERA_INT_SPACES.items():
        values = _suggest_per_era_ints(trial, key, bounds)
        _set_list(config, key, values)

    for key in _PER_ERA_BOOL_KEYS:
        values = _suggest_per_era_bools(trial, key)
        _set_list(config, key, ("True" if value else "False" for value in values))

    config["DEFAULT"]["CLOCK_TIME"] = str(CLOCK_TIME_HOURS)
    config["DEFAULT"]["RUN_FINAL_TOURNAMENT"] = "True"
    config["DEFAULT"]["BENCHMARK_FINAL_TOURNAMENT"] = "True"
    config["DEFAULT"]["FINAL_TOURNAMENT_CSV"] = "final_tournament.csv"
    config["DEFAULT"]["IN_MEMORY_ARENAS"] = "False"

    config_path = run_dir / "settings.ini"
    with config_path.open("w", encoding="utf-8") as handle:
        config.write(handle)
    return config_path


def _prepare_arena_directory(run_dir: Path) -> None:
    arena_dir = run_dir / "arena0"
    if arena_dir.exists():
        shutil.rmtree(arena_dir)
    arena_dir.mkdir(parents=True, exist_ok=True)


def _run_trial(trial: optuna.trial.Trial) -> float:
    trial_dir = TRIAL_OUTPUT_ROOT / f"trial_{trial.number:04d}"
    if trial_dir.exists():
        shutil.rmtree(trial_dir)
    trial_dir.mkdir(parents=True)
    run_dir = trial_dir / "run"
    run_dir.mkdir(parents=True)

    _prepare_arena_directory(run_dir)
    config_path = _build_trial_configuration(trial, run_dir)

    cmd = [sys.executable, "evolverstage.py", "--config", str(config_path), "--seed", str(trial.number)]
    subprocess.run(cmd, check=True, cwd=REPO_ROOT)

    final_csv_path = run_dir / "final_tournament.csv"
    if not final_csv_path.exists():
        raise RuntimeError("Final tournament CSV was not generated")

    best_score = None
    best_entry: dict[str, str] | None = None
    with final_csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                score = float(row["score"])
            except (KeyError, ValueError) as exc:
                raise RuntimeError("Invalid final tournament CSV format") from exc
            if best_score is None or score > best_score:
                best_score = score
                best_entry = row

    if best_score is None or best_entry is None:
        raise RuntimeError("Final tournament CSV did not contain any results")

    warrior_id = best_entry.get("warrior_id")
    if warrior_id is None:
        raise RuntimeError("Best entry is missing warrior_id")

    source_warrior_path = run_dir / "arena0" / f"{warrior_id}.red"
    if not source_warrior_path.exists():
        raise RuntimeError(f"Best warrior file '{source_warrior_path}' was not found")

    shutil.copyfile(source_warrior_path, trial_dir / "best_warrior.red")
    shutil.copyfile(final_csv_path, trial_dir / "final_tournament.csv")
    shutil.copyfile(config_path, trial_dir / "settings.ini")

    return float(best_score)


def objective(trial: optuna.trial.Trial) -> float:
    return _run_trial(trial)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Optuna optimizer for evolverstage settings")
    parser.add_argument("--trials", type=int, default=10, help="Number of Optuna trials to run")
    args = parser.parse_args(argv)

    TRIAL_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=args.trials)

    print("Best score:", study.best_value)
    print("Best parameters:")
    for key, value in sorted(study.best_params.items()):
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
