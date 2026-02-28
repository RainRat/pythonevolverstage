"""Optuna-based hyperparameter optimization for evolverstage."""
from __future__ import annotations

import argparse
import configparser
import csv
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import optuna
import yaml

REPO_ROOT = Path(__file__).resolve().parent
BASE_SETTINGS_PATH = REPO_ROOT / "settings.ini"
TRIAL_OUTPUT_ROOT = REPO_ROOT / "optuna_trials"

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

@dataclass(frozen=True)
class OptimizerConfig:
    tuning_arena_index: int
    clock_time_hours: float
    n_trials: int
    per_era_int_spaces: dict[str, tuple[int, int]]
    per_era_bool_keys: list[str]


def _load_optimizer_config(path: Path) -> OptimizerConfig:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ValueError("Optimizer configuration must be a mapping")

    try:
        tuning_arena_index = int(data["tuning_arena_index"])
        clock_time_hours = float(data["clock_time_hours"])
        n_trials = int(data["n_trials"])
    except KeyError as exc:
        raise ValueError(f"Missing required optimizer config key: {exc.args[0]}") from exc

    raw_spaces = data.get("per_era_int_spaces", {})
    if not isinstance(raw_spaces, dict):
        raise ValueError("per_era_int_spaces must be a mapping of key to [low, high]")

    per_era_int_spaces: dict[str, tuple[int, int]] = {}
    for key, value in raw_spaces.items():
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError(
                f"per_era_int_spaces entry for {key!r} must be a list of two integers"
            )
        low, high = value
        per_era_int_spaces[key] = (int(low), int(high))

    raw_bool_keys = data.get("per_era_bool_keys", [])
    if not isinstance(raw_bool_keys, list):
        raise ValueError("per_era_bool_keys must be a list of strings")
    per_era_bool_keys = [str(item) for item in raw_bool_keys]

    return OptimizerConfig(
        tuning_arena_index=tuning_arena_index,
        clock_time_hours=clock_time_hours,
        n_trials=n_trials,
        per_era_int_spaces=per_era_int_spaces,
        per_era_bool_keys=per_era_bool_keys,
    )


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


def _get_arena_specific_value(key: str, arena_index: int) -> str:
    values = _parse_list(_BASE_DEFAULTS.get(key, ""))
    if not values:
        raise RuntimeError(f"Missing list value for {key} in settings.ini")
    if arena_index >= len(values):
        raise RuntimeError(
            f"Arena index {arena_index} is out of range for {key} (length={len(values)})"
        )
    return values[arena_index]


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


def _build_trial_configuration(
    trial: optuna.trial.Trial, run_dir: Path, optimizer_config: OptimizerConfig
) -> Path:
    config = configparser.ConfigParser()
    config.optionxform = str
    config["DEFAULT"] = {}
    for key, value in _BASE_DEFAULTS.items():
        config["DEFAULT"][key] = value

    config["DEFAULT"]["LAST_ARENA"] = "0"
    for key in _ARENA_LIST_KEYS:
        config["DEFAULT"][key] = _get_arena_specific_value(
            key, optimizer_config.tuning_arena_index
        )

    for key, bounds in optimizer_config.per_era_int_spaces.items():
        values = _suggest_per_era_ints(trial, key, bounds)
        _set_list(config, key, values)

    for key in optimizer_config.per_era_bool_keys:
        values = _suggest_per_era_bools(trial, key)
        _set_list(config, key, ("True" if value else "False" for value in values))

    config["DEFAULT"]["CLOCK_TIME"] = str(optimizer_config.clock_time_hours)
    config["DEFAULT"]["RUN_FINAL_TOURNAMENT"] = "True"
    config["DEFAULT"]["BENCHMARK_FINAL_TOURNAMENT"] = "True"
    config["DEFAULT"]["FINAL_TOURNAMENT_CSV"] = "final_tournament.csv"
    config["DEFAULT"]["IN_MEMORY_ARENAS"] = "False"
    config["DEFAULT"]["ARCHIVE_PATH"] = "archive"

    config_path = run_dir / "settings.ini"
    with config_path.open("w", encoding="utf-8") as handle:
        config.write(handle)
    return config_path


def _prepare_trial_directory(run_dir: Path) -> None:
    arena_dir = run_dir / "arena0"
    if arena_dir.exists():
        shutil.rmtree(arena_dir)
    arena_dir.mkdir(parents=True, exist_ok=True)
    
    # Symlink benchmarks to run_dir
    benchmark_src = REPO_ROOT / "benchmarks"
    benchmark_dst = run_dir / "benchmarks"
    if benchmark_dst.exists():
        benchmark_dst.unlink()
    if benchmark_src.exists():
        benchmark_dst.symlink_to(benchmark_src, target_is_directory=True)

    # Copy global archive to local trial archive to seed it
    archive_src = REPO_ROOT / "archive"
    archive_dst = run_dir / "archive"
    if archive_dst.exists():
        shutil.rmtree(archive_dst)
    if archive_src.exists() and archive_src.is_dir():
        shutil.copytree(archive_src, archive_dst)
    else:
        archive_dst.mkdir(parents=True, exist_ok=True)


def _run_trial(trial: optuna.trial.Trial, optimizer_config: OptimizerConfig) -> float:
    trial_dir = TRIAL_OUTPUT_ROOT / f"trial_{trial.number:04d}"
    if trial_dir.exists():
        shutil.rmtree(trial_dir)
    trial_dir.mkdir(parents=True)
    run_dir = trial_dir / "run"
    run_dir.mkdir(parents=True)

    _prepare_trial_directory(run_dir)
    config_path = _build_trial_configuration(trial, run_dir, optimizer_config)

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


def objective(trial: optuna.trial.Trial, optimizer_config: OptimizerConfig) -> float:
    return _run_trial(trial, optimizer_config)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Optuna optimizer for evolverstage settings")
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "optimizer_config.yaml",
        help="Path to optimizer YAML configuration file",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=None,
        help="Number of Optuna trials to run (overrides YAML config if provided)",
    )
    args = parser.parse_args(argv)

    TRIAL_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    optimizer_config = _load_optimizer_config(args.config)
    n_trials = args.trials if args.trials is not None else optimizer_config.n_trials

    study = optuna.create_study(direction="maximize")
    study.optimize(lambda trial: objective(trial, optimizer_config), n_trials=n_trials)

    print("Best score:", study.best_value)
    print("Best parameters:")
    for key, value in sorted(study.best_params.items()):
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
