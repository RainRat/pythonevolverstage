import argparse
import configparser
import csv
import os
import random
import shutil
import statistics
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple, TypeVar, Union, cast, TextIO

from engine import *
from ui import (
    BattleStatisticsTracker,
    ChampionDisplay,
    ConsoleInterface,
    PseudoGraphicalConsole,
    SimpleConsole,
    StatusDisplay,
    VerbosityLevel,
    close_console,
    console_clear_status,
    console_log,
    console_update_champions,
    console_update_status,
    get_console,
    set_console_verbosity,
)


@dataclass
class BenchmarkWarrior:
    name: str
    code: str
    path: str


@dataclass
class BenchmarkBattleResult:
    warriors: list[int]
    scores: list[int]
    benchmarks_played: int


@dataclass
class EvolverConfig:
    battle_engine: str
    last_arena: int
    base_path: str
    archive_path: str
    coresize_list: list[int]
    sanitize_list: list[int]
    cycles_list: list[int]
    processes_list: list[int]
    readlimit_list: list[int]
    writelimit_list: list[int]
    warlen_list: list[int]
    wardistance_list: list[int]
    arena_spec_list: list[str]
    arena_weight_list: list[int]
    numwarriors: int
    alreadyseeded: bool
    use_in_memory_arenas: bool
    arena_checkpoint_interval: int
    clock_time: float
    battle_log_file: Optional[str]
    benchmark_log_file: Optional[str]
    benchmark_log_generation_interval: int
    final_era_only: bool
    nothing_list: list[int]
    random_list: list[int]
    nab_list: list[int]
    mini_mut_list: list[int]
    micro_mut_list: list[int]
    library_list: list[int]
    magic_number_list: list[int]
    archive_list: list[int]
    unarchive_list: list[int]
    library_path: Optional[str]
    crossoverrate_list: list[int]
    transpositionrate_list: list[int]
    battlerounds_list: list[int]
    prefer_winner_list: list[bool]
    champion_battle_frequency_list: list[int]
    random_pair_battle_frequency_list: list[int]
    instr_set: list[str]
    instr_modes: list[str]
    instr_modif: list[str]
    run_final_tournament: bool
    final_tournament_csv: Optional[str]
    benchmark_root: Optional[str]
    benchmark_final_tournament: bool
    benchmark_battle_frequency_list: list[int]
    benchmark_sets: dict[int, list[BenchmarkWarrior]] = field(default_factory=dict)


class _ConfigNotLoaded:
    def __getattr__(self, item: str):
        raise RuntimeError(
            "Active evolver configuration has not been set. Call set_active_config() "
            "or main() before using module-level helpers."
        )


config = cast(EvolverConfig, _ConfigNotLoaded())

_RNG_SEQUENCE: Optional[list[int]] = None
_RNG_INDEX: int = 0

_BENCHMARK_WARRIOR_ID_BASE = MAX_WARRIOR_FILENAME_ID - 10_000

_FINAL_STANDINGS_DISPLAY_LIMIT = 20
_PER_WARRIOR_SUMMARY_LIMIT = 20

T = TypeVar("T")


def set_rng_sequence(sequence: list[int]) -> None:
    """Set a deterministic RNG sequence for tests."""

    global _RNG_SEQUENCE, _RNG_INDEX
    if sequence:
        _RNG_SEQUENCE = list(sequence)
    else:
        _RNG_SEQUENCE = None
    _RNG_INDEX = 0


def get_random_int(min_val: int, max_val: int) -> int:
    """Return a random integer within ``[min_val, max_val]``."""

    if min_val > max_val:
        raise ValueError("min_val cannot be greater than max_val")

    global _RNG_SEQUENCE, _RNG_INDEX
    if _RNG_SEQUENCE is not None:
        if _RNG_INDEX >= len(_RNG_SEQUENCE):
            raise RuntimeError("Deterministic RNG sequence exhausted")
        value = _RNG_SEQUENCE[_RNG_INDEX]
        _RNG_INDEX += 1
        if value < min_val or value > max_val:
            raise ValueError(
                f"Deterministic RNG value {value} outside range [{min_val}, {max_val}]"
            )
        return value

    return random.randint(min_val, max_val)


def _get_random_choice(sequence: Sequence[T]) -> T:
    if not sequence:
        raise ValueError("Cannot choose from an empty sequence")
    index = get_random_int(0, len(sequence) - 1)
    return sequence[index]


configure_rng(get_random_int, _get_random_choice)


def _select_arena_index(active_config: EvolverConfig) -> int:
    """Choose an arena index, honouring optional per-arena weights."""

    arena_count = active_config.last_arena + 1
    if arena_count <= 0:
        raise ValueError("No arenas configured to select from.")

    weights = active_config.arena_weight_list
    if not weights:
        return get_random_int(0, active_config.last_arena)

    limited_weights = [max(0, weight) for weight in weights[:arena_count]]
    weighted_indices = [
        (index, weight)
        for index, weight in enumerate(limited_weights)
        if weight > 0
    ]

    if not weighted_indices:
        return get_random_int(0, active_config.last_arena)

    total_weight = sum(weight for _, weight in weighted_indices)
    roll = get_random_int(1, total_weight)
    cumulative = 0
    for index, weight in weighted_indices:
        cumulative += weight
        if roll <= cumulative:
            return index

    # Fallback; should not occur but protects against rounding mistakes.
    return weighted_indices[-1][0]


def _parse_int(value: str, *, key: str, parser: configparser.ConfigParser) -> int:
    return int(value)


def _parse_float(value: str, *, key: str, parser: configparser.ConfigParser) -> float:
    return float(value)


def _parse_bool(value: str, *, key: str, parser: configparser.ConfigParser) -> bool:
    if isinstance(value, bool):
        return value

    normalized = value.strip().lower()
    if not normalized:
        raise ValueError(f"Boolean value for '{key}' cannot be empty")

    boolean_states = getattr(parser, "BOOLEAN_STATES", configparser.ConfigParser.BOOLEAN_STATES)
    if normalized in boolean_states:
        return boolean_states[normalized]

    raise ValueError(f"Invalid boolean value '{value}' for '{key}'")


def _parse_int_list(value: str, *, key: str, parser: configparser.ConfigParser) -> list[int]:
    return [int(item.strip()) for item in value.split(',') if item.strip()]


def _parse_bool_list(value: str, *, key: str, parser: configparser.ConfigParser) -> list[bool]:
    return [item.strip().lower() == 'true' for item in value.split(',') if item.strip()]


def _parse_string_list(value: str, *, key: str, parser: configparser.ConfigParser) -> list[str]:
    return [item.strip() for item in value.split(',') if item.strip()]


def _parse_str(value: str, *, key: str, parser: configparser.ConfigParser) -> str:
    return value


_CONFIG_PARSERS: dict[str, Callable[..., object]] = {
    'int': _parse_int,
    'float': _parse_float,
    'bool': _parse_bool,
    'int_list': _parse_int_list,
    'bool_list': _parse_bool_list,
    'string_list': _parse_string_list,
    'str': _parse_str,
}


def set_active_config(new_config: EvolverConfig) -> None:
    global config
    config = new_config
    set_engine_config(new_config)


def get_active_config() -> EvolverConfig:
    return config


def _validate_arena_parameters(idx: int, active_config: EvolverConfig) -> None:
    core_size = active_config.coresize_list[idx]
    sanitize_limit = active_config.sanitize_list[idx]
    cycles_limit = active_config.cycles_list[idx]
    process_limit = active_config.processes_list[idx]
    warrior_length = active_config.warlen_list[idx]
    min_distance = active_config.wardistance_list[idx]
    read_limit = active_config.readlimit_list[idx]
    write_limit = active_config.writelimit_list[idx]

    max_min_distance = core_size // 2

    if core_size < CPP_WORKER_MIN_CORE_SIZE:
        raise ValueError(
            f"CORESIZE_LIST[{idx + 1}] must be at least {CPP_WORKER_MIN_CORE_SIZE} "
            f"(got {core_size})."
        )
    if core_size > CPP_WORKER_MAX_CORE_SIZE:
        raise ValueError(
            f"CORESIZE_LIST[{idx + 1}] cannot exceed {CPP_WORKER_MAX_CORE_SIZE} "
            f"(got {core_size})."
        )
    if cycles_limit <= 0 or cycles_limit > CPP_WORKER_MAX_CYCLES:
        raise ValueError(
            f"CYCLES_LIST[{idx + 1}] must be between 1 and {CPP_WORKER_MAX_CYCLES} "
            f"(got {cycles_limit})."
        )
    if process_limit <= 0 or process_limit > CPP_WORKER_MAX_PROCESSES:
        raise ValueError(
            f"PROCESSES_LIST[{idx + 1}] must be between 1 and {CPP_WORKER_MAX_PROCESSES} "
            f"(got {process_limit})."
        )
    if warrior_length <= 0 or warrior_length > CPP_WORKER_MAX_WARRIOR_LENGTH:
        raise ValueError(
            f"WARLEN_LIST[{idx + 1}] must be between 1 and "
            f"{CPP_WORKER_MAX_WARRIOR_LENGTH} (got {warrior_length})."
        )
    if warrior_length > core_size:
        raise ValueError(
            f"WARLEN_LIST[{idx + 1}] cannot exceed the arena's core size "
            f"(got {warrior_length} with core size {core_size})."
        )
    if min_distance < CPP_WORKER_MIN_DISTANCE or min_distance > max_min_distance:
        raise ValueError(
            f"WARDISTANCE_LIST[{idx + 1}] must be between {CPP_WORKER_MIN_DISTANCE} and "
            f"{max_min_distance} (CORESIZE/2) (got {min_distance})."
        )
    if min_distance < warrior_length:
        raise ValueError(
            "WARDISTANCE_LIST values must be greater than or equal to their corresponding "
            "WARLEN_LIST values and fall within 0..(CORESIZE/2) to prevent overlap ("
            f"got wardistance={min_distance}, warlen={warrior_length} at index {idx + 1})."
        )
    if sanitize_limit < 1 or sanitize_limit > core_size:
        raise ValueError(
            f"SANITIZE_LIST[{idx + 1}] must be between 1 and the arena's core size "
            f"(got {sanitize_limit})."
        )
    if read_limit <= 0 or read_limit > core_size:
        raise ValueError(
            f"READLIMIT_LIST[{idx + 1}] must be between 1 and the arena's core size "
            f"(got {read_limit})."
        )
    if write_limit <= 0 or write_limit > core_size:
        raise ValueError(
            f"WRITELIMIT_LIST[{idx + 1}] must be between 1 and the arena's core size "
            f"(got {write_limit})."
        )


def _detect_existing_seed(active_config: EvolverConfig) -> tuple[bool, list[str]]:
    """Return whether all arenas contain seeded warriors and any missing entries."""

    missing_entries: list[str] = []
    arena_count = active_config.last_arena + 1
    base_path = active_config.base_path

    for arena in range(arena_count):
        arena_dir = os.path.join(base_path, f"arena{arena}")
        if not os.path.isdir(arena_dir):
            missing_entries.append(arena_dir)
            continue

        for warrior_id in range(1, active_config.numwarriors + 1):
            warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
            if not os.path.isfile(warrior_path):
                missing_entries.append(warrior_path)

    return not missing_entries, missing_entries


def validate_config(active_config: EvolverConfig, config_path: Optional[str] = None) -> None:
    if active_config.last_arena is None:
        raise ValueError("LAST_ARENA must be specified in the configuration.")

    if (
        active_config.benchmark_final_tournament
        and not active_config.benchmark_root
    ):
        warnings.warn(
            "BENCHMARK_FINAL_TOURNAMENT is enabled but BENCHMARK_ROOT is not set; "
            "benchmark-based tournaments will be disabled.",
            RuntimeWarning,
            stacklevel=2,
        )
        active_config.benchmark_final_tournament = False

    valid_engines = {"nmars", "internal", "pmars"}
    if active_config.battle_engine not in valid_engines:
        raise ValueError(
            "BATTLE_ENGINE must be one of "
            + ", ".join(sorted(valid_engines))
            + f" (got {active_config.battle_engine!r})."
        )

    arena_count = active_config.last_arena + 1
    if arena_count <= 0:
        raise ValueError(
            "LAST_ARENA must be greater than or equal to 0 (implies at least one arena)."
        )

    if active_config.arena_checkpoint_interval <= 0:
        raise ValueError(
            "ARENA_CHECKPOINT_INTERVAL must be a positive integer."
        )

    if active_config.benchmark_log_generation_interval < 0:
        raise ValueError(
            "BENCHMARK_LOG_GENERATION_INTERVAL cannot be negative."
        )

    if (
        active_config.benchmark_log_file
        and active_config.benchmark_log_generation_interval <= 0
    ):
        warnings.warn(
            "BENCHMARK_LOG_FILE is set but BENCHMARK_LOG_GENERATION_INTERVAL is not "
            "positive; benchmark logging will be disabled.",
            RuntimeWarning,
            stacklevel=2,
        )
        active_config.benchmark_log_file = None

    per_arena_lists = {
        "CORESIZE_LIST": active_config.coresize_list,
        "SANITIZE_LIST": active_config.sanitize_list,
        "CYCLES_LIST": active_config.cycles_list,
        "PROCESSES_LIST": active_config.processes_list,
        "READLIMIT_LIST": active_config.readlimit_list,
        "WRITELIMIT_LIST": active_config.writelimit_list,
        "WARLEN_LIST": active_config.warlen_list,
        "WARDISTANCE_LIST": active_config.wardistance_list,
        "SPEC_LIST": active_config.arena_spec_list,
    }

    extra_length_lists: list[str] = []
    for name, values in per_arena_lists.items():
        if len(values) < arena_count:
            raise ValueError(
                f"{name} must contain {arena_count} entries (one for each arena),"
                f" but {len(values)} value(s) were provided."
            )
        if len(values) > arena_count:
            extra_length_lists.append(f"{name} ({len(values)})")

    if extra_length_lists:
        warnings.warn(
            "LAST_ARENA limits the run to "
            f"{arena_count} arena(s), but the following list(s) provide extra values: "
            + ", ".join(extra_length_lists)
            + f". Only the first {arena_count} entries will be used.",
            stacklevel=2,
        )

    if active_config.arena_weight_list:
        weight_count = len(active_config.arena_weight_list)
        if weight_count < arena_count:
            raise ValueError(
                "ARENA_WEIGHT_LIST must contain at least one entry per arena "
                f"({arena_count} required, got {weight_count})."
            )
        if weight_count > arena_count:
            warnings.warn(
                "LAST_ARENA limits the run to "
                f"{arena_count} arena(s), but ARENA_WEIGHT_LIST provides {weight_count} entries. "
                f"Only the first {arena_count} entries will be used.",
                stacklevel=2,
            )

        limited_weights = active_config.arena_weight_list[:arena_count]
        for idx, weight in enumerate(limited_weights, start=1):
            if weight < 0:
                raise ValueError(
                    "ARENA_WEIGHT_LIST values must be non-negative integers "
                    f"(got {weight} at position {idx})."
                )
        if not any(weight > 0 for weight in limited_weights):
            raise ValueError(
                "ARENA_WEIGHT_LIST must include at least one positive value to select arenas."
            )

    for idx in range(arena_count):
        _validate_arena_parameters(idx, active_config)

    if active_config.numwarriors is None or active_config.numwarriors <= 0:
        raise ValueError("NUMWARRIORS must be a positive integer.")
    if active_config.numwarriors > MAX_WARRIOR_FILENAME_ID:
        raise ValueError(
            "NUMWARRIORS exceeds the supported maximum of "
            f"{MAX_WARRIOR_FILENAME_ID}."
        )

    if not active_config.battlerounds_list:
        raise ValueError("BATTLEROUNDS_LIST must contain at least one value.")

    for idx, rounds in enumerate(active_config.battlerounds_list, start=1):
        if rounds < 1:
            raise ValueError(
                f"BATTLEROUNDS_LIST[{idx}] must be at least 1 (got {rounds})."
            )
        if rounds > CPP_WORKER_MAX_ROUNDS:
            raise ValueError(
                f"BATTLEROUNDS_LIST[{idx}] cannot exceed {CPP_WORKER_MAX_ROUNDS} "
                f"(got {rounds})."
            )

    era_count = len(active_config.battlerounds_list)

    benchmark_frequency_list = list(active_config.benchmark_battle_frequency_list)
    if not benchmark_frequency_list:
        benchmark_frequency_list = [0] * era_count
    elif len(benchmark_frequency_list) == 1 and era_count > 1:
        benchmark_frequency_list = benchmark_frequency_list * era_count
    elif len(benchmark_frequency_list) != era_count:
        raise ValueError(
            "BENCHMARK_BATTLE_FREQUENCY_LIST must contain either 1 value or one value per era.",
        )
    if any(value < 0 for value in benchmark_frequency_list):
        raise ValueError(
            "BENCHMARK_BATTLE_FREQUENCY_LIST entries cannot be negative."
        )
    active_config.benchmark_battle_frequency_list = benchmark_frequency_list

    champion_frequency_list = list(active_config.champion_battle_frequency_list)
    if not champion_frequency_list:
        champion_frequency_list = [1] * era_count
    elif len(champion_frequency_list) == 1 and era_count > 1:
        champion_frequency_list = champion_frequency_list * era_count
    elif len(champion_frequency_list) != era_count:
        raise ValueError(
            "CHAMPION_BATTLE_FREQUENCY_LIST must contain either 1 value or one value per era."
        )

    random_pair_frequency_list = list(active_config.random_pair_battle_frequency_list)
    if not random_pair_frequency_list:
        random_pair_frequency_list = [1] * era_count
    elif len(random_pair_frequency_list) == 1 and era_count > 1:
        random_pair_frequency_list = random_pair_frequency_list * era_count
    elif len(random_pair_frequency_list) != era_count:
        raise ValueError(
            "RANDOM_PAIR_BATTLE_FREQUENCY_LIST must contain either 1 value or one value per era."
        )

    for idx, value in enumerate(champion_frequency_list, start=1):
        if value < 0:
            raise ValueError(
                "CHAMPION_BATTLE_FREQUENCY_LIST entries cannot be negative."
            )

    for idx, value in enumerate(random_pair_frequency_list, start=1):
        if value < 0:
            raise ValueError(
                "RANDOM_PAIR_BATTLE_FREQUENCY_LIST entries cannot be negative."
            )

    active_config.champion_battle_frequency_list = champion_frequency_list
    active_config.random_pair_battle_frequency_list = random_pair_frequency_list

    era_lists = {
        "NOTHING_LIST": active_config.nothing_list,
        "RANDOM_LIST": active_config.random_list,
        "NAB_LIST": active_config.nab_list,
        "MINI_MUT_LIST": active_config.mini_mut_list,
        "MICRO_MUT_LIST": active_config.micro_mut_list,
        "LIBRARY_LIST": active_config.library_list,
        "MAGIC_NUMBER_LIST": active_config.magic_number_list,
        "ARCHIVE_LIST": active_config.archive_list,
        "UNARCHIVE_LIST": active_config.unarchive_list,
        "CROSSOVERRATE_LIST": active_config.crossoverrate_list,
        "TRANSPOSITIONRATE_LIST": active_config.transpositionrate_list,
        "PREFER_WINNER_LIST": active_config.prefer_winner_list,
        "BENCHMARK_BATTLE_FREQUENCY_LIST": active_config.benchmark_battle_frequency_list,
        "CHAMPION_BATTLE_FREQUENCY_LIST": active_config.champion_battle_frequency_list,
        "RANDOM_PAIR_BATTLE_FREQUENCY_LIST": active_config.random_pair_battle_frequency_list,
    }

    for name, values in era_lists.items():
        if len(values) != era_count:
            raise ValueError(
                f"{name} must contain {era_count} entries (one for each era),"
                f" but {len(values)} value(s) were provided."
            )

    for era_index in range(era_count):
        total_battle_weight = (
            active_config.champion_battle_frequency_list[era_index]
            + active_config.random_pair_battle_frequency_list[era_index]
            + active_config.benchmark_battle_frequency_list[era_index]
        )
        if total_battle_weight <= 0:
            raise ValueError(
                "Battle frequency lists must sum to a positive value for era "
                f"{era_index + 1}."
            )

    marble_probability_limits = {
        "NOTHING_LIST": active_config.nothing_list,
        "RANDOM_LIST": active_config.random_list,
        "NAB_LIST": active_config.nab_list,
        "MINI_MUT_LIST": active_config.mini_mut_list,
        "MICRO_MUT_LIST": active_config.micro_mut_list,
        "LIBRARY_LIST": active_config.library_list,
        "MAGIC_NUMBER_LIST": active_config.magic_number_list,
    }

    for name, values in marble_probability_limits.items():
        for value in values:
            if value < 0:
                raise ValueError(f"Values in {name} cannot be negative (found {value}).")
            if value > 100000:
                raise ValueError(
                    f"Values in {name} appear unreasonably large (found {value});"
                    " please double-check the configuration."
                )

    for era_index in range(era_count):
        total_weight = sum(values[era_index] for values in marble_probability_limits.values())
        if total_weight <= 0:
            raise ValueError(
                "Marble bag probabilities for era "
                f"{era_index + 1} must sum to a positive value."
            )

    for idx, value in enumerate(active_config.crossoverrate_list, start=1):
        if value < 1:
            raise ValueError(
                f"CROSSOVERRATE_LIST[{idx}] must be at least 1 (got {value})."
            )

    for idx, value in enumerate(active_config.transpositionrate_list, start=1):
        if value < 1:
            raise ValueError(
                f"TRANSPOSITIONRATE_LIST[{idx}] must be at least 1 (got {value})."
            )

    base_path = getattr(active_config, "base_path", None) or os.getcwd()
    if config_path and not getattr(active_config, "base_path", None):
        config_directory = os.path.dirname(os.path.abspath(config_path))
        if config_directory:
            base_path = config_directory

    active_config.base_path = base_path

    required_directories = [os.path.join(base_path, f"arena{i}") for i in range(arena_count)]
    required_directories.append(active_config.archive_path)

    expect_benchmarks = active_config.benchmark_final_tournament or any(
        value > 0 for value in active_config.benchmark_battle_frequency_list
    )

    if active_config.benchmark_root:
        benchmark_root = active_config.benchmark_root
        if not os.path.isabs(benchmark_root):
            benchmark_root = os.path.abspath(benchmark_root)
            active_config.benchmark_root = benchmark_root
        if not os.path.isdir(benchmark_root):
            if expect_benchmarks:
                raise FileNotFoundError(
                    f"Benchmark directory '{benchmark_root}' does not exist or is not a directory."
                )
            active_config.benchmark_root = None

    if not os.path.isdir(base_path):
        raise FileNotFoundError(
            f"Configuration directory '{base_path}' does not exist or is not a directory."
        )

    for directory in required_directories:
        if os.path.isdir(directory):
            if not os.access(directory, os.W_OK):
                raise PermissionError(
                    f"Directory '{directory}' is not writable."
                )
        else:
            parent_dir = os.path.dirname(directory) or base_path
            if not os.access(parent_dir, os.W_OK):
                raise PermissionError(
                    f"Missing permissions to create directory '{directory}'."
                )

    seeded, missing_entries = _detect_existing_seed(active_config)
    active_config.alreadyseeded = seeded
    if not seeded and missing_entries:
        console_log(
            "Arenas will be freshly seeded because required warriors are missing.",
            minimum_level=VerbosityLevel.TERSE,
        )

    if active_config.clock_time is None or active_config.clock_time <= 0:
        raise ValueError("CLOCK_TIME must be a positive number of hours.")

    if active_config.instr_modes:
        invalid_modes = sorted(
            {
                mode.strip()
                for mode in active_config.instr_modes
                if mode.strip() and mode.strip() not in BASE_ADDRESSING_MODES
            }
        )
        if invalid_modes:
            allowed_modes = ", ".join(sorted(BASE_ADDRESSING_MODES))
            raise ValueError(
                "INSTR_MODES contains unsupported addressing mode(s): "
                + ", ".join(invalid_modes)
                + f". Allowed values are: {allowed_modes}."
            )


def _load_benchmark_sets(active_config: EvolverConfig) -> dict[int, list[BenchmarkWarrior]]:
    benchmark_root = active_config.benchmark_root
    if not benchmark_root:
        return {}

    expect_benchmarks = active_config.benchmark_final_tournament or any(
        value > 0 for value in active_config.benchmark_battle_frequency_list
    )

    if not os.path.isdir(benchmark_root):
        if expect_benchmarks:
            warnings.warn(
                f"Benchmark root '{benchmark_root}' is missing.",
                RuntimeWarning,
                stacklevel=2,
            )
        return {}

    benchmark_sets: dict[int, list[BenchmarkWarrior]] = {}
    arena_count = active_config.last_arena + 1
    for arena in range(arena_count):
        arena_dir = os.path.join(benchmark_root, f"arena{arena}")
        if not os.path.isdir(arena_dir):
            if expect_benchmarks:
                warnings.warn(
                    f"Benchmark directory '{arena_dir}' missing for arena {arena}.",
                    RuntimeWarning,
                    stacklevel=2,
                )
            continue

        entries = sorted(
            entry for entry in os.listdir(arena_dir) if entry.lower().endswith(".red")
        )
        warriors: list[BenchmarkWarrior] = []
        for entry in entries:
            full_path = os.path.join(arena_dir, entry)
            try:
                with open(full_path, "r") as handle:
                    code = handle.read()
            except OSError as exc:
                warnings.warn(
                    f"Unable to read benchmark warrior '{full_path}': {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue
            name, _ = os.path.splitext(entry)
            warriors.append(BenchmarkWarrior(name=name, code=code, path=full_path))

        if warriors:
            benchmark_sets[arena] = warriors
        elif expect_benchmarks:
            warnings.warn(
                f"No benchmark warriors found for arena {arena} in '{arena_dir}'.",
                RuntimeWarning,
                stacklevel=2,
            )

    return benchmark_sets


def _run_benchmark_battle(
    arena_index: int,
    cont1: int,
    cont2: int,
    era: int,
    active_config: EvolverConfig,
) -> Optional[BenchmarkBattleResult]:
    benchmark_warriors = active_config.benchmark_sets.get(arena_index)
    if not benchmark_warriors or era < 0:
        return None

    storage = get_arena_storage()
    cont1_lines = storage.get_warrior_lines(arena_index, cont1)
    cont2_lines = storage.get_warrior_lines(arena_index, cont2)
    if not cont1_lines or not cont2_lines:
        return None

    cont1_code = "".join(cont1_lines)
    cont2_code = "".join(cont2_lines)
    if not cont1_code.strip() or not cont2_code.strip():
        return None

    totals: defaultdict[int, int] = defaultdict(int)
    benchmarks_played = 0

    for bench_index, benchmark in enumerate(benchmark_warriors):
        bench_identifier = max(
            1, _BENCHMARK_WARRIOR_ID_BASE - (arena_index * 1000 + bench_index)
        )
        round_scores: dict[int, int] = {}
        for warrior_id, warrior_code in ((cont1, cont1_code), (cont2, cont2_code)):
            match_seed = _stable_internal_battle_seed(
                arena_index, warrior_id, bench_identifier, era
            )
            warriors, scores = execute_battle_with_sources(
                arena_index,
                warrior_id,
                warrior_code,
                bench_identifier,
                benchmark.code,
                era,
                verbose=False,
                seed=match_seed,
            )
            try:
                warrior_pos = warriors.index(warrior_id)
            except ValueError:
                return None
            round_scores[warrior_id] = scores[warrior_pos]

        if len(round_scores) < 2:
            return None

        for warrior_id, score in round_scores.items():
            totals[warrior_id] += score
        benchmarks_played += 1

    if benchmarks_played == 0:
        return None

    cont1_total = totals.get(cont1, 0)
    cont2_total = totals.get(cont2, 0)
    return BenchmarkBattleResult(
        warriors=[cont1, cont2],
        scores=[cont1_total, cont2_total],
        benchmarks_played=benchmarks_played,
    )


def load_configuration(path: str) -> EvolverConfig:
    parser = configparser.ConfigParser()
    read_files = parser.read(path)
    if not read_files:
        raise FileNotFoundError(f"Configuration file '{path}' not found")

    base_path = os.path.dirname(os.path.abspath(path)) or os.getcwd()

    def _normalize_spec(value: str, index: int) -> str:
        normalized = value.strip().lower()
        if normalized in {"1994", "94"}:
            return SPEC_1994
        if normalized in {"1988", "88"}:
            return SPEC_1988
        raise ValueError(
            "SPEC_LIST entries must be '1994' or '1988'. "
            f"Invalid value '{value}' at position {index + 1}."
        )

    def _read_config(key: str, data_type: str = 'int', default=None):
        value = parser['DEFAULT'].get(key, fallback=default)
        if value in (None, ''):
            return default
        if key not in parser['DEFAULT']:
            return value
        parser_fn = _CONFIG_PARSERS.get(data_type)
        if parser_fn is None:
            raise ValueError(f"Unsupported data type: {data_type}")
        return parser_fn(value, key=key, parser=parser)

    last_arena_value = _read_config('LAST_ARENA', data_type='int')
    if last_arena_value is None:
        raise ValueError("LAST_ARENA must be specified in the configuration.")

    spec_entries = _read_config('SPEC_LIST', data_type='string_list') or []
    arena_count = last_arena_value + 1
    normalized_specs: list[str] = []
    for idx in range(arena_count):
        if idx < len(spec_entries):
            normalized_specs.append(_normalize_spec(spec_entries[idx], idx))
        else:
            normalized_specs.append(SPEC_1994)

    battle_log_file = _read_config('BATTLE_LOG_FILE', data_type='str')
    if battle_log_file:
        battle_log_file = os.path.abspath(os.path.join(base_path, battle_log_file))

    benchmark_log_file = _read_config('BENCHMARK_LOG_FILE', data_type='str')
    if benchmark_log_file:
        benchmark_log_file = os.path.abspath(
            os.path.join(base_path, benchmark_log_file)
        )

    benchmark_log_generation_interval = (
        _read_config(
            'BENCHMARK_LOG_GENERATION_INTERVAL', data_type='int', default=0
        )
        or 0
    )

    final_tournament_csv = _read_config('FINAL_TOURNAMENT_CSV', data_type='str')
    if final_tournament_csv:
        final_tournament_csv = os.path.abspath(
            os.path.join(base_path, final_tournament_csv)
        )

    library_path = _read_config('LIBRARY_PATH', data_type='str')
    if library_path:
        library_path = os.path.abspath(os.path.join(base_path, library_path))

    benchmark_root = _read_config('BENCHMARK_ROOT', data_type='str')
    if benchmark_root:
        benchmark_root = os.path.abspath(os.path.join(base_path, benchmark_root))

    archive_path = _read_config('ARCHIVE_PATH', data_type='str')
    if archive_path:
        archive_path = os.path.expanduser(archive_path)
        if not os.path.isabs(archive_path):
            archive_path = os.path.abspath(os.path.join(base_path, archive_path))
        else:
            archive_path = os.path.abspath(archive_path)
    else:
        archive_path = os.path.abspath(os.path.join(base_path, "archive"))

    battlerounds_list = _read_config('BATTLEROUNDS_LIST', data_type='int_list') or []
    prefer_winner_list = _read_config('PREFER_WINNER_LIST', data_type='bool_list') or []
    legacy_champion_chance_list = (
        _read_config('CHAMPION_BATTLE_CHANCE_LIST', data_type='int_list') or []
    )
    champion_battle_frequency_list = (
        _read_config('CHAMPION_BATTLE_FREQUENCY_LIST', data_type='int_list') or []
    )
    random_pair_battle_frequency_list = (
        _read_config('RANDOM_PAIR_BATTLE_FREQUENCY_LIST', data_type='int_list') or []
    )

    archive_list = _read_config('ARCHIVE_LIST', data_type='int_list') or []
    unarchive_list = _read_config('UNARCHIVE_LIST', data_type='int_list') or []
    if 'ARCHIVE_LIST' not in parser['DEFAULT'] and battlerounds_list:
        archive_list = [0] * len(battlerounds_list)
    if 'UNARCHIVE_LIST' not in parser['DEFAULT'] and battlerounds_list:
        unarchive_list = [0] * len(battlerounds_list)

    benchmark_frequency_list = _read_config(
        'BENCHMARK_BATTLE_FREQUENCY_LIST', data_type='int_list'
    )
    if benchmark_frequency_list:
        benchmark_frequency_list = list(benchmark_frequency_list)
    else:
        fallback_frequency = _read_config(
            'BENCHMARK_BATTLE_FREQUENCY', data_type='int', default=0
        )
        if fallback_frequency is None:
            fallback_frequency = 0
        benchmark_frequency_list = [fallback_frequency]
        if battlerounds_list:
            benchmark_frequency_list = benchmark_frequency_list * len(battlerounds_list)

    if not champion_battle_frequency_list and legacy_champion_chance_list:
        champion_battle_frequency_list = list(legacy_champion_chance_list)
        if not random_pair_battle_frequency_list:
            random_pair_battle_frequency_list = [
                max(0, 100 - value) for value in legacy_champion_chance_list
            ]

    if battlerounds_list:
        era_len = len(battlerounds_list)
        if not champion_battle_frequency_list:
            champion_battle_frequency_list = [1] * era_len
        if not random_pair_battle_frequency_list:
            random_pair_battle_frequency_list = [1] * era_len

    active_config = EvolverConfig(
        battle_engine=_read_config('BATTLE_ENGINE', data_type='str', default='internal') or 'internal',
        last_arena=last_arena_value,
        base_path=base_path,
        archive_path=archive_path,
        coresize_list=_read_config('CORESIZE_LIST', data_type='int_list') or [],
        sanitize_list=_read_config('SANITIZE_LIST', data_type='int_list') or [],
        cycles_list=_read_config('CYCLES_LIST', data_type='int_list') or [],
        processes_list=_read_config('PROCESSES_LIST', data_type='int_list') or [],
        readlimit_list=_read_config('READLIMIT_LIST', data_type='int_list') or [],
        writelimit_list=_read_config('WRITELIMIT_LIST', data_type='int_list') or [],
        warlen_list=_read_config('WARLEN_LIST', data_type='int_list') or [],
        wardistance_list=_read_config('WARDISTANCE_LIST', data_type='int_list') or [],
        arena_spec_list=normalized_specs,
        numwarriors=_read_config('NUMWARRIORS', data_type='int'),
        alreadyseeded=False,
        use_in_memory_arenas=_read_config('IN_MEMORY_ARENAS', data_type='bool', default=False) or False,
        arena_checkpoint_interval=_read_config('ARENA_CHECKPOINT_INTERVAL', data_type='int', default=10000) or 10000,
        clock_time=_read_config('CLOCK_TIME', data_type='float'),
        battle_log_file=battle_log_file,
        benchmark_log_file=benchmark_log_file,
        benchmark_log_generation_interval=benchmark_log_generation_interval,
        final_era_only=_read_config('FINAL_ERA_ONLY', data_type='bool'),
        nothing_list=_read_config('NOTHING_LIST', data_type='int_list') or [],
        random_list=_read_config('RANDOM_LIST', data_type='int_list') or [],
        nab_list=_read_config('NAB_LIST', data_type='int_list') or [],
        mini_mut_list=_read_config('MINI_MUT_LIST', data_type='int_list') or [],
        micro_mut_list=_read_config('MICRO_MUT_LIST', data_type='int_list') or [],
        library_list=_read_config('LIBRARY_LIST', data_type='int_list') or [],
        magic_number_list=_read_config('MAGIC_NUMBER_LIST', data_type='int_list') or [],
        archive_list=archive_list,
        unarchive_list=unarchive_list,
        library_path=library_path,
        crossoverrate_list=_read_config('CROSSOVERRATE_LIST', data_type='int_list') or [],
        transpositionrate_list=_read_config('TRANSPOSITIONRATE_LIST', data_type='int_list') or [],
        battlerounds_list=battlerounds_list,
        prefer_winner_list=prefer_winner_list,
        champion_battle_frequency_list=champion_battle_frequency_list,
        random_pair_battle_frequency_list=random_pair_battle_frequency_list,
        instr_set=_read_config('INSTR_SET', data_type='string_list') or [],
        instr_modes=_read_config('INSTR_MODES', data_type='string_list') or [],
        instr_modif=_read_config('INSTR_MODIF', data_type='string_list') or [],
        run_final_tournament=_read_config('RUN_FINAL_TOURNAMENT', data_type='bool', default=False) or False,
        final_tournament_csv=final_tournament_csv,
        benchmark_root=benchmark_root,
        benchmark_final_tournament=_read_config('BENCHMARK_FINAL_TOURNAMENT', data_type='bool', default=False) or False,
        benchmark_battle_frequency_list=benchmark_frequency_list,
        arena_weight_list=_read_config('ARENA_WEIGHT_LIST', data_type='int_list') or [],
    )
    if not active_config.readlimit_list:
        active_config.readlimit_list = list(active_config.coresize_list)
    if not active_config.writelimit_list:
        active_config.writelimit_list = list(active_config.coresize_list)

    validate_config(active_config, config_path=path)
    if active_config.benchmark_root:
        active_config.benchmark_sets = _load_benchmark_sets(active_config)
    return active_config


class DataLogger:
    def __init__(self, filename: Optional[str]):
        self.filename = filename
        self.fieldnames = ['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with']
        self.file_handle: Optional[TextIO] = None
        self.writer: Optional[csv.DictWriter] = None

    def open(self) -> None:
        if not self.filename or self.file_handle is not None:
            return

        file_handle = open(self.filename, 'a', newline='')
        writer = csv.DictWriter(file_handle, fieldnames=self.fieldnames)
        if file_handle.tell() == 0:
            writer.writeheader()

        self.file_handle = file_handle
        self.writer = writer

    def close(self) -> None:
        if self.file_handle is not None:
            self.file_handle.close()
            self.file_handle = None
            self.writer = None

    def log_data(self, **kwargs):
        if not self.filename:
            return

        if self.writer is None:
            self.open()

        if self.writer is not None:
            self.writer.writerow(kwargs)
            if self.file_handle is not None:
                self.file_handle.flush()


class BenchmarkLogger:
    def __init__(self, filename: Optional[str]):
        self.filename = filename
        self.fieldnames = [
            "era",
            "generation",
            "arena",
            "champion",
            "benchmark",
            "score",
            "benchmark_path",
        ]
        self.file_handle: Optional[TextIO] = None
        self.writer: Optional[csv.DictWriter] = None

    @property
    def enabled(self) -> bool:
        return bool(self.filename)

    def open(self) -> None:
        if not self.filename or self.file_handle is not None:
            return

        file_handle = open(self.filename, "a", newline="")
        writer = csv.DictWriter(file_handle, fieldnames=self.fieldnames)
        if file_handle.tell() == 0:
            writer.writeheader()

        self.file_handle = file_handle
        self.writer = writer

    def close(self) -> None:
        if self.file_handle is not None:
            self.file_handle.close()
            self.file_handle = None
            self.writer = None

    def log_score(
        self,
        *,
        era: int,
        generation: int,
        arena: int,
        champion: int,
        benchmark: str,
        score: int,
        benchmark_path: Optional[str],
    ) -> None:
        if not self.filename:
            return

        if self.writer is None:
            self.open()

        if self.writer is not None:
            self.writer.writerow(
                {
                    "era": era,
                    "generation": generation,
                    "arena": arena,
                    "champion": champion,
                    "benchmark": benchmark,
                    "score": score,
                    "benchmark_path": benchmark_path or "",
                }
            )
            if self.file_handle is not None:
                self.file_handle.flush()


def _score_warrior_against_benchmarks(
    arena_index: int,
    warrior_id: int,
    era: int,
    active_config: EvolverConfig,
) -> list[tuple[BenchmarkWarrior, int]]:
    benchmark_warriors = active_config.benchmark_sets.get(arena_index)
    if not benchmark_warriors or era < 0:
        return []

    storage = get_arena_storage()
    warrior_lines = storage.get_warrior_lines(arena_index, warrior_id)
    if not warrior_lines:
        return []

    warrior_code = "".join(warrior_lines)
    if not warrior_code.strip():
        return []

    results: list[tuple[BenchmarkWarrior, int]] = []
    for bench_index, benchmark in enumerate(benchmark_warriors):
        bench_identifier = max(
            1, _BENCHMARK_WARRIOR_ID_BASE - (arena_index * 1000 + bench_index)
        )
        match_seed = _stable_internal_battle_seed(
            arena_index, warrior_id, bench_identifier, era
        )
        warriors, scores = execute_battle_with_sources(
            arena_index,
            warrior_id,
            warrior_code,
            bench_identifier,
            benchmark.code,
            era,
            verbose=False,
            seed=match_seed,
        )
        try:
            warrior_pos = warriors.index(warrior_id)
        except ValueError:
            continue
        results.append((benchmark, scores[warrior_pos]))

    return results


def _log_benchmark_scores_for_champions(
    *,
    era: int,
    generation: int,
    champions: dict[int, int],
    active_config: EvolverConfig,
    benchmark_logger: BenchmarkLogger,
) -> None:
    if era < 0 or generation <= 0 or not benchmark_logger.enabled:
        return

    for arena_index in range(active_config.last_arena + 1):
        champion_id = champions.get(arena_index)
        if champion_id is None:
            continue

        scores = _score_warrior_against_benchmarks(
            arena_index, champion_id, era, active_config
        )
        for benchmark, score in scores:
            benchmark_logger.log_score(
                era=era,
                generation=generation,
                arena=arena_index,
                champion=champion_id,
                benchmark=benchmark.name,
                score=score,
                benchmark_path=benchmark.path,
            )


def _count_instruction_library_entries(library_path: Optional[str]) -> int:
    if not library_path:
        return 0

    try:
        with open(library_path, "r") as library_handle:
            return sum(
                1
                for line in library_handle
                if line.strip() and not line.lstrip().startswith(";")
            )
    except FileNotFoundError:
        return 0
    except OSError as exc:
        warnings.warn(
            f"Unable to read instruction library '{library_path}': {exc}",
            RuntimeWarning,
        )
        return 0


def _print_run_configuration_summary(active_config: EvolverConfig) -> None:
    log_display = active_config.battle_log_file if active_config.battle_log_file else "Disabled"
    if active_config.benchmark_log_file:
        benchmark_log_display = (
            f"{active_config.benchmark_log_file} "
            f"(every {active_config.benchmark_log_generation_interval} generations)"
        )
    else:
        benchmark_log_display = "Disabled"
    arena_count = active_config.last_arena + 1 if active_config.last_arena is not None else 0
    archive_count = get_archive_storage().count()
    library_entries = _count_instruction_library_entries(active_config.library_path)
    if active_config.library_path:
        library_display = f"{library_entries} entries from {active_config.library_path}"
    else:
        library_display = f"{library_entries} entries (no library configured)"

    console_log("Run configuration summary:", minimum_level=VerbosityLevel.TERSE)
    console_log(
        f"  Battle log: {log_display}", minimum_level=VerbosityLevel.TERSE
    )
    console_log(
        f"  Benchmark log: {benchmark_log_display}",
        minimum_level=VerbosityLevel.TERSE,
    )
    console_log(f"  Arenas: {arena_count}", minimum_level=VerbosityLevel.TERSE)
    console_log(
        f"  Battle engine: {active_config.battle_engine}",
        minimum_level=VerbosityLevel.TERSE,
    )
    if active_config.use_in_memory_arenas:
        storage_display = (
            "In-memory (checkpoint every "
            f"{active_config.arena_checkpoint_interval} battles)"
        )
    else:
        storage_display = "On-disk"
    console_log(
        f"  Arena storage: {storage_display}",
        minimum_level=VerbosityLevel.TERSE,
    )
    console_log(
        "  Final tournament enabled: "
        f"{'Yes' if active_config.run_final_tournament else 'No'}",
        minimum_level=VerbosityLevel.TERSE,
    )
    csv_display = active_config.final_tournament_csv or "Disabled"
    console_log(
        f"  Final tournament CSV export: {csv_display}",
        minimum_level=VerbosityLevel.TERSE,
    )
    console_log("", minimum_level=VerbosityLevel.TERSE)


def _print_evolution_statistics(
    battles_per_era: Sequence[int],
    total_battles: int,
    runtime_seconds: float,
) -> None:
    console_log("Evolution statistics:", minimum_level=VerbosityLevel.TERSE)
    if not battles_per_era:
        console_log("  No battles were executed.", minimum_level=VerbosityLevel.TERSE)
    else:
        for index, battle_count in enumerate(battles_per_era, start=1):
            console_log(
                f"  Era {index}: {battle_count} battles",
                minimum_level=VerbosityLevel.TERSE,
            )
        console_log(
            f"  Total battles: {total_battles}", minimum_level=VerbosityLevel.TERSE
        )

    if runtime_seconds > 0 and total_battles > 0:
        battles_per_hour = total_battles / (runtime_seconds / 3600)
        console_log(
            f"  Approximate speed: {battles_per_hour:.2f} battles/hour",
            minimum_level=VerbosityLevel.TERSE,
        )
    else:
        console_log("  Approximate speed: n/a", minimum_level=VerbosityLevel.TERSE)
    console_log("", minimum_level=VerbosityLevel.TERSE)


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f} seconds"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)} minutes {secs:.2f} seconds"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)} hours {int(minutes)} minutes {secs:.2f} seconds"


def _get_progress_status(
    start_time: float, total_duration_hr: float, current_era: int
) -> tuple[str, str]:
    runtime_seconds = time.time() - start_time
    runtime_in_hours = runtime_seconds / 3600
    if total_duration_hr > 0:
        seconds_remaining = max((total_duration_hr - runtime_in_hours) * 3600, 0.0)
        percent_complete = (runtime_in_hours / total_duration_hr) * 100
        percent_complete = min(max(percent_complete, 0.0), 100.0)
    else:
        seconds_remaining = 0.0
        percent_complete = 100.0

    display_era = current_era + 1
    if current_era >= 0:
        progress_line = (
            f"{_format_duration(seconds_remaining)} remaining "
            f"({percent_complete:.2f}% complete) Era: {display_era}"
        )
        detail_line = f"Era {display_era}"
    else:
        progress_line = (
            f"{_format_duration(seconds_remaining)} remaining "
            f"({percent_complete:.2f}% complete)"
        )
        detail_line = "No active era"

    return progress_line, detail_line


def _update_final_tournament_status(
    *,
    battles_completed: int,
    total_battles: int,
    tournament_start: float,
    active_config: EvolverConfig,
    final_era_index: int,
    detail_line: Optional[str],
) -> None:
    percent_complete = (
        battles_completed / total_battles * 100 if total_battles else 100.0
    )
    time_progress, default_detail = _get_progress_status(
        tournament_start, active_config.clock_time, final_era_index
    )
    progress_segments = []
    if active_config.clock_time:
        progress_segments.append(time_progress)
    progress_segments.append(
        f"Final Tournament Progress: {battles_completed}/{total_battles} "
        f"battles ({percent_complete:.2f}% complete)"
    )
    progress_line = " | ".join(progress_segments)
    console_update_status(progress_line, detail_line or default_detail)


def _run_benchmark_tournament(
    arena: int,
    warrior_ids: Sequence[int],
    benchmark_warriors: Sequence[BenchmarkWarrior],
    *,
    storage: ArenaStorage,
    final_era_index: int,
    active_config: EvolverConfig,
    total_battles: int,
    tournament_start: float,
    battles_completed: int,
    warrior_scores_by_arena: dict[int, list[int]],
) -> tuple[dict[int, int], int, dict[int, float], dict[int, int]]:
    total_scores = {warrior_id: 0 for warrior_id in warrior_ids}
    benchmark_totals: dict[int, float] = {}
    benchmark_counts: dict[int, int] = {}
    missing_warriors: set[tuple[int, int]] = set()

    for bench_index, benchmark in enumerate(benchmark_warriors):
        benchmark_totals.setdefault(bench_index, 0.0)
        benchmark_counts.setdefault(bench_index, 0)
        bench_identifier = max(
            1,
            _BENCHMARK_WARRIOR_ID_BASE - (arena * 1000 + bench_index),
        )

        for warrior_id in warrior_ids:
            warrior_lines = storage.get_warrior_lines(arena, warrior_id)
            if not warrior_lines:
                if (arena, warrior_id) not in missing_warriors:
                    console_log(
                        f"Arena {arena}: warrior {warrior_id} has no code; skipping benchmark match.",
                        minimum_level=VerbosityLevel.TERSE,
                    )
                    missing_warriors.add((arena, warrior_id))
                continue
            warrior_code = "".join(warrior_lines)
            if not warrior_code.strip():
                if (arena, warrior_id) not in missing_warriors:
                    console_log(
                        f"Arena {arena}: warrior {warrior_id} is empty; skipping benchmark match.",
                        minimum_level=VerbosityLevel.TERSE,
                    )
                    missing_warriors.add((arena, warrior_id))
                continue

            match_seed = _stable_internal_battle_seed(
                arena, warrior_id, bench_identifier, final_era_index
            )
            warriors, scores = execute_battle_with_sources(
                arena,
                warrior_id,
                warrior_code,
                bench_identifier,
                benchmark.code,
                final_era_index,
                verbose=False,
                seed=match_seed,
            )

            try:
                warrior_pos = warriors.index(warrior_id)
                benchmark_pos = warriors.index(bench_identifier)
            except ValueError:
                console_log(
                    "Benchmark battle returned unexpected warrior identifiers; ignoring result.",
                    minimum_level=VerbosityLevel.TERSE,
                )
                continue

            warrior_score = scores[warrior_pos]
            benchmark_score = scores[benchmark_pos]
            total_scores[warrior_id] = total_scores.get(warrior_id, 0) + warrior_score
            warrior_scores_by_arena.setdefault(warrior_id, []).append(warrior_score)
            benchmark_totals[bench_index] += benchmark_score
            benchmark_counts[bench_index] += 1

            battles_completed += 1
            detail_line = (
                f"Arena {arena} | Warrior {warrior_id} ({warrior_score}) vs "
                f"benchmark {benchmark.name} ({benchmark_score})"
            )
            _update_final_tournament_status(
                battles_completed=battles_completed,
                total_battles=total_battles,
                tournament_start=tournament_start,
                active_config=active_config,
                final_era_index=final_era_index,
                detail_line=detail_line,
            )

    return total_scores, battles_completed, benchmark_totals, benchmark_counts


def _run_round_robin_tournament(
    arena: int,
    warrior_ids: Sequence[int],
    *,
    final_era_index: int,
    active_config: EvolverConfig,
    total_battles: int,
    tournament_start: float,
    battles_completed: int,
    warrior_scores_by_arena: dict[int, list[int]],
) -> tuple[dict[int, int], int]:
    total_scores = {warrior_id: 0 for warrior_id in warrior_ids}

    for idx, cont1 in enumerate(warrior_ids):
        for cont2 in warrior_ids[idx + 1 :]:
            match_seed = _stable_internal_battle_seed(
                arena, cont1, cont2, final_era_index
            )
            warriors, scores = execute_battle(
                arena,
                cont1,
                cont2,
                final_era_index,
                verbose=False,
                battlerounds_override=1,
                seed=match_seed,
            )
            for warrior_id, score in zip(warriors, scores):
                total_scores[warrior_id] = total_scores.get(warrior_id, 0) + score
                warrior_scores_by_arena.setdefault(warrior_id, []).append(score)

            battles_completed += 1
            if len(warriors) >= 2 and len(scores) >= 2:
                detail_line = (
                    f"Arena {arena} | {warriors[0]} ({scores[0]}) vs "
                    f"{warriors[1]} ({scores[1]})"
                )
            else:
                detail_line = f"Arena {arena} battle in progress"
            _update_final_tournament_status(
                battles_completed=battles_completed,
                total_battles=total_battles,
                tournament_start=tournament_start,
                active_config=active_config,
                final_era_index=final_era_index,
                detail_line=detail_line,
            )

    return total_scores, battles_completed


def _log_era_summary(
    era_index: int,
    battles_per_era: Sequence[int],
    archived_per_era: Sequence[int],
    unarchived_per_era: Sequence[int],
) -> None:
    if not (0 <= era_index < len(battles_per_era)):
        return
    era_number = era_index + 1
    summary_lines = [
        f"Era {era_number} summary:",
        f"  Battles: {battles_per_era[era_index]}",
        f"  Warriors archived: {archived_per_era[era_index]}",
        f"  Warriors unarchived: {unarchived_per_era[era_index]}",
    ]
    console_log("\n".join(summary_lines), minimum_level=VerbosityLevel.DEFAULT)


def _build_marble_bag(
    era: int, active_config: EvolverConfig
) -> list[BaseMutationStrategy]:
    bag: list[BaseMutationStrategy] = []

    bag.extend(DoNothingMutation() for _ in range(active_config.nothing_list[era]))
    bag.extend(MajorMutation() for _ in range(active_config.random_list[era]))
    bag.extend(NabInstruction() for _ in range(active_config.nab_list[era]))
    bag.extend(MinorMutation() for _ in range(active_config.mini_mut_list[era]))
    bag.extend(MicroMutation() for _ in range(active_config.micro_mut_list[era]))
    bag.extend(
        InstructionLibraryMutation()
        for _ in range(active_config.library_list[era])
    )
    bag.extend(
        MagicNumberMutation() for _ in range(active_config.magic_number_list[era])
    )

    return bag


def run_final_tournament(active_config: EvolverConfig):
    console_clear_status()
    if active_config.last_arena < 0:
        console_log(
            "No arenas configured. Skipping final tournament.",
            minimum_level=VerbosityLevel.TERSE,
        )
        return
    benchmark_available = (
        active_config.benchmark_final_tournament
        and any(active_config.benchmark_sets.values())
    )
    if active_config.numwarriors <= 1 and not benchmark_available:
        console_log(
            "Not enough warriors to run a final tournament.",
            minimum_level=VerbosityLevel.TERSE,
        )
        return
    if not active_config.battlerounds_list:
        console_log(
            "Battle rounds configuration missing. Cannot run final tournament.",
            minimum_level=VerbosityLevel.TERSE,
        )
        return

    final_era_index = max(0, len(active_config.battlerounds_list) - 1)
    use_in_memory_internal = (
        active_config.use_in_memory_arenas and active_config.battle_engine == 'internal'
    )
    storage = get_arena_storage()
    use_benchmarks = (
        active_config.benchmark_final_tournament
        and any(active_config.benchmark_sets.values())
    )
    console_log(
        "\n================ Final Tournament ================",
        minimum_level=VerbosityLevel.TERSE,
    )
    arenas_to_run: list[tuple[int, list[int], list[BenchmarkWarrior]]] = []
    total_battles = 0
    arena_summaries: list[dict[str, object]] = []
    warrior_scores_by_arena: dict[int, list[int]] = {}
    for arena in range(0, active_config.last_arena + 1):
        if not use_in_memory_internal:
            arena_dir = os.path.join(active_config.base_path, f"arena{arena}")
            if not os.path.isdir(arena_dir):
                console_log(
                    f"Arena {arena} directory '{arena_dir}' not found. Skipping.",
                    minimum_level=VerbosityLevel.TERSE,
                )
                continue

        warrior_ids = [
            warrior_id
            for warrior_id in range(1, active_config.numwarriors + 1)
            if storage.get_warrior_lines(arena, warrior_id)
        ]

        if not warrior_ids:
            console_log(
                f"Arena {arena}: no warriors available for the final tournament.",
                minimum_level=VerbosityLevel.TERSE,
            )
            continue

        benchmark_warriors = (
            list(active_config.benchmark_sets.get(arena, [])) if use_benchmarks else []
        )
        if use_benchmarks and not benchmark_warriors:
            console_log(
                f"Arena {arena}: no benchmark warriors configured; using round-robin scoring.",
                minimum_level=VerbosityLevel.TERSE,
            )

        if benchmark_warriors:
            arena_battles = len(warrior_ids) * len(benchmark_warriors)
        else:
            if len(warrior_ids) < 2:
                console_log(
                    f"Arena {arena}: not enough warriors for a round-robin tournament. Skipping.",
                    minimum_level=VerbosityLevel.TERSE,
                )
                continue
            arena_battles = len(warrior_ids) * (len(warrior_ids) - 1) // 2

        if arena_battles == 0:
            console_log(
                f"Arena {arena}: no battles scheduled; skipping.",
                minimum_level=VerbosityLevel.TERSE,
            )
            continue

        arenas_to_run.append((arena, warrior_ids, benchmark_warriors))
        total_battles += arena_battles

    if not arenas_to_run:
        console_log(
            "No arenas with enough warriors for the final tournament.",
            minimum_level=VerbosityLevel.TERSE,
        )
        return

    for _, warrior_ids, _ in arenas_to_run:
        for warrior_id in warrior_ids:
            warrior_scores_by_arena.setdefault(warrior_id, [])

    tournament_start = time.time()
    battles_completed = 0
    try:
        for arena, warrior_ids, benchmark_warriors in arenas_to_run:
            if benchmark_warriors:
                (
                    total_scores,
                    battles_completed,
                    benchmark_totals,
                    benchmark_counts,
                ) = _run_benchmark_tournament(
                    arena,
                    warrior_ids,
                    benchmark_warriors,
                    storage=storage,
                    final_era_index=final_era_index,
                    active_config=active_config,
                    total_battles=total_battles,
                    tournament_start=tournament_start,
                    battles_completed=battles_completed,
                    warrior_scores_by_arena=warrior_scores_by_arena,
                )
            else:
                benchmark_totals = {}
                benchmark_counts = {}
                total_scores, battles_completed = _run_round_robin_tournament(
                    arena,
                    warrior_ids,
                    final_era_index=final_era_index,
                    active_config=active_config,
                    total_battles=total_battles,
                    tournament_start=tournament_start,
                    battles_completed=battles_completed,
                    warrior_scores_by_arena=warrior_scores_by_arena,
                )

            console_clear_status()
            console_log(
                f"\nArena {arena} final standings:",
                minimum_level=VerbosityLevel.TERSE,
            )
            rankings = sorted(total_scores.items(), key=lambda item: item[1], reverse=True)
            standings_to_show = rankings[:_FINAL_STANDINGS_DISPLAY_LIMIT]
            for position, (warrior_id, score) in enumerate(standings_to_show, start=1):
                console_log(
                    f"{position}. Warrior {warrior_id}: {score} points",
                    minimum_level=VerbosityLevel.TERSE,
                )
            hidden_count = max(0, len(rankings) - len(standings_to_show))
            if hidden_count:
                if active_config.final_tournament_csv:
                    destination_hint = (
                        f"Full standings exported to {active_config.final_tournament_csv}."
                    )
                else:
                    destination_hint = (
                        "Configure FINAL_TOURNAMENT_CSV to export full standings."
                    )
                console_log(
                    f"  ...and {hidden_count} more warrior(s) not shown. {destination_hint}",
                    minimum_level=VerbosityLevel.TERSE,
                )
            champion_id, champion_score = rankings[0]
            console_log(
                f"Champion: Warrior {champion_id} with {champion_score} points",
                minimum_level=VerbosityLevel.TERSE,
            )
            arena_average = (
                statistics.mean(total_scores.values()) if total_scores else 0.0
            )
            summary_entry: dict[str, object] = {
                "arena": arena,
                "rankings": list(rankings),
                "average": arena_average,
                "mode": "benchmark" if benchmark_warriors else "round_robin",
            }

            if benchmark_warriors:
                benchmark_summary: list[dict[str, object]] = []
                for bench_index, benchmark in enumerate(benchmark_warriors):
                    count = benchmark_counts.get(bench_index, 0)
                    average = (
                        benchmark_totals.get(bench_index, 0.0) / count
                        if count
                        else 0.0
                    )
                    benchmark_summary.append(
                        {
                            "name": benchmark.name,
                            "average": average,
                            "matches": count,
                            "path": benchmark.path,
                        }
                    )
                if benchmark_summary:
                    summary_entry["benchmark"] = benchmark_summary
                    console_log(
                        "Benchmark reference (scores from the benchmark perspective):",
                        minimum_level=VerbosityLevel.TERSE,
                    )
                    for entry in benchmark_summary:
                        console_log(
                            "  {name}: {avg:.2f} over {count} match(es)".format(
                                name=entry["name"],
                                avg=entry["average"],
                                count=entry["matches"],
                            ),
                            minimum_level=VerbosityLevel.TERSE,
                        )

            arena_summaries.append(summary_entry)
    except KeyboardInterrupt:
        console_clear_status()
        console_log(
            "Final tournament interrupted by user.",
            minimum_level=VerbosityLevel.TERSE,
        )
        return

    console_clear_status()
    duration = time.time() - tournament_start
    _report_final_tournament_statistics(arena_summaries, warrior_scores_by_arena)
    _export_final_tournament_results(arena_summaries, active_config)
    console_log(
        f"Final tournament completed in {_format_duration(duration)}.",
        minimum_level=VerbosityLevel.TERSE,
    )


def _report_final_tournament_statistics(
    arena_summaries: Sequence[dict[str, object]],
    warrior_scores_by_arena: dict[int, list[int]],
) -> None:
    if not arena_summaries:
        return

    console_log(
        "\nTournament statistics:", minimum_level=VerbosityLevel.TERSE
    )
    aggregated_benchmarks: dict[str, dict[str, float]] = {}

    for summary in arena_summaries:
        arena_id = summary.get("arena")
        arena_average = float(summary.get("average", 0.0))
        console_log(
            f"  Arena {arena_id} average score: {arena_average:.2f}",
            minimum_level=VerbosityLevel.TERSE,
        )
        benchmark_info = summary.get("benchmark")
        if benchmark_info:
            total_matches = 0
            for entry in benchmark_info:
                name = entry.get("name", "unknown")
                average = float(entry.get("average", 0.0))
                count = int(entry.get("matches", 0))
                total_matches += count
                aggregate = aggregated_benchmarks.setdefault(
                    name, {"total": 0.0, "matches": 0}
                )
                aggregate["total"] += average * count
                aggregate["matches"] += count
            console_log(
                f"    Benchmarks played: {total_matches} match(es) across {len(benchmark_info)} warrior(s)",
                minimum_level=VerbosityLevel.TERSE,
            )

    if aggregated_benchmarks:
        console_log(
            "\nBenchmark performance summary (benchmark perspective):",
            minimum_level=VerbosityLevel.TERSE,
        )
        for name in sorted(aggregated_benchmarks):
            matches = int(aggregated_benchmarks[name]["matches"])
            total = float(aggregated_benchmarks[name]["total"])
            average = total / matches if matches else 0.0
            console_log(
                f"  {name}: {average:.2f} over {matches} match(es)",
                minimum_level=VerbosityLevel.TERSE,
            )

    all_scores = [score for scores in warrior_scores_by_arena.values() for score in scores]
    if all_scores:
        overall_average = statistics.mean(all_scores)
        console_log(
            f"  Overall average score: {overall_average:.2f}",
            minimum_level=VerbosityLevel.TERSE,
        )

    warrior_stats: list[dict[str, object]] = []
    for warrior_id in sorted(warrior_scores_by_arena):
        scores = warrior_scores_by_arena[warrior_id]
        if not scores:
            continue
        average_score = statistics.mean(scores)
        deviation = statistics.pstdev(scores) if len(scores) > 1 else 0.0
        warrior_stats.append(
            {
                "warrior_id": warrior_id,
                "average": average_score,
                "stdev": deviation,
                "appearances": len(scores),
            }
        )

    if not warrior_stats:
        return

    console_log(
        "\nPer-warrior performance summary:",
        minimum_level=VerbosityLevel.TERSE,
    )
    sorted_warriors = sorted(
        warrior_stats,
        key=lambda data: (
            -float(data["average"]),
            float(data["stdev"]),
            int(data["warrior_id"]),
        ),
    )
    warriors_to_show = sorted_warriors[:_PER_WARRIOR_SUMMARY_LIMIT]
    for entry in warriors_to_show:
        console_log(
            "  Warrior {warrior_id}: avg {avg:.2f}, σ {stdev:.2f} across {count} match(es)".format(
                warrior_id=entry["warrior_id"],
                avg=entry["average"],
                stdev=entry["stdev"],
                count=entry["appearances"],
            ),
            minimum_level=VerbosityLevel.TERSE,
        )
    hidden_warriors = max(0, len(sorted_warriors) - len(warriors_to_show))
    if hidden_warriors:
        console_log(
            f"  ...and {hidden_warriors} more warrior(s) not shown.",
            minimum_level=VerbosityLevel.TERSE,
        )

    consistent_candidates = [
        entry
        for entry in warrior_stats
        if int(entry["appearances"]) > 1 and float(entry["average"]) > 0.0
    ]
    if not consistent_candidates:
        consistent_candidates = [
            entry for entry in warrior_stats if int(entry["appearances"]) > 1
        ]
    if not consistent_candidates:
        consistent_candidates = list(warrior_stats)

    consistent_candidates.sort(
        key=lambda data: (
            float(data["stdev"]),
            -float(data["average"]),
            int(data["warrior_id"]),
        )
    )
    top_consistent = consistent_candidates[: min(3, len(consistent_candidates))]
    if top_consistent:
        console_log(
            "\nMost consistent performers:",
            minimum_level=VerbosityLevel.TERSE,
        )
        for entry in top_consistent:
            console_log(
                "  Warrior {warrior_id}: σ {stdev:.2f} across {count} match(es) (avg {avg:.2f})".format(
                    warrior_id=entry["warrior_id"],
                    stdev=entry["stdev"],
                    count=entry["appearances"],
                    avg=entry["average"],
                ),
                minimum_level=VerbosityLevel.TERSE,
            )


def _export_final_tournament_results(
    arena_summaries: Sequence[dict[str, object]], active_config: EvolverConfig
) -> None:
    if not active_config.final_tournament_csv or not arena_summaries:
        return

    output_path = active_config.final_tournament_csv
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    try:
        with open(output_path, "w", newline="") as csv_file:
            fieldnames = ["arena", "warrior_id", "rank", "score"]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for summary in arena_summaries:
                arena_id = summary.get("arena")
                rankings = summary.get("rankings", [])
                for rank, result in enumerate(rankings, start=1):
                    warrior_id, score = result
                    writer.writerow(
                        {
                            "arena": arena_id,
                            "warrior_id": warrior_id,
                            "rank": rank,
                            "score": score,
                        }
                    )
        console_log(
            f"Final tournament results exported to {output_path}",
            minimum_level=VerbosityLevel.TERSE,
        )
    except OSError as exc:
        console_log(
            f"Unable to write final tournament CSV '{output_path}': {exc}",
            minimum_level=VerbosityLevel.TERSE,
        )

def _main_impl(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Python Evolver Stage")
    parser.add_argument(
        "--config",
        default="settings.ini",
        help="Path to configuration INI file (default: settings.ini)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Seed the RNG for reproducible runs",
    )
    parser.add_argument(
        "--verbosity",
        choices=[level.value for level in VerbosityLevel],
        default=VerbosityLevel.DEFAULT.value,
        help="Console verbosity: terse, default, verbose, or pseudo-graphical",
    )
    args = parser.parse_args(argv)

    verbosity = VerbosityLevel(args.verbosity)

    verbosity = set_console_verbosity(verbosity)

    active_config = load_configuration(args.config)

    set_active_config(active_config)

    archive_storage = DiskArchiveStorage(archive_path=active_config.archive_path)
    set_archive_storage(archive_storage)
    archive_storage.initialize()

    _print_run_configuration_summary(active_config)

    seed_enabled = args.seed is not None
    if seed_enabled:
        random.seed(args.seed)

    storage = create_arena_storage(active_config)
    set_arena_storage(storage)
    storage.load_existing()

    if not active_config.alreadyseeded:
        console_log("Seeding", minimum_level=VerbosityLevel.TERSE)
        for arena in range(0, active_config.last_arena + 1):
            arena_dir = os.path.join(active_config.base_path, f"arena{arena}")
            os.makedirs(arena_dir, exist_ok=True)
            for warrior_id in range(1, active_config.numwarriors + 1):
                new_lines = [
                    instruction_to_line(generate_random_instruction(arena), arena)
                    for _ in range(1, active_config.warlen_list[arena] + 1)
                ]
                storage.set_warrior_lines(arena, warrior_id, new_lines)
        storage.flush_all()

    start_time = time.time()
    era = -1
    data_logger = DataLogger(filename=active_config.battle_log_file)
    benchmark_logger = BenchmarkLogger(
        filename=active_config.benchmark_log_file
    )
    bag: list[BaseMutationStrategy] = []
    interrupted = False
    era_count = len(active_config.battlerounds_list)
    era_duration = active_config.clock_time / era_count
    battles_per_era = [0 for _ in range(era_count)]
    archived_per_era = [0 for _ in range(era_count)]
    unarchived_per_era = [0 for _ in range(era_count)]
    total_battles = 0
    generation_counter = 0
    champions: dict[int, int] = {
        arena_index: 1 for arena_index in range(active_config.last_arena + 1)
    }

    def _sync_champion_display() -> None:
        champion_payload: dict[int, ChampionDisplay] = {}
        for arena_index, warrior_id in champions.items():
            lines = storage.get_warrior_lines(arena_index, warrior_id)
            sanitized = tuple(line.rstrip("\r\n") for line in lines)
            champion_payload[arena_index] = ChampionDisplay(
                warrior_id=warrior_id, lines=sanitized
            )
        console_update_champions(champion_payload)

    _sync_champion_display()

    data_logger.open()
    benchmark_logger.open()

    try:
        while True:
            previous_era = era
            runtime_seconds = time.time() - start_time
            runtime_in_hours = runtime_seconds / 3600

            if runtime_in_hours > active_config.clock_time:
                console_clear_status()
                console_log(
                    "Clock time exceeded. Ending evolution loop.",
                    minimum_level=VerbosityLevel.TERSE,
                )
                break

            if active_config.final_era_only:
                era = era_count - 1
            else:
                era = min(int(runtime_in_hours / era_duration), era_count - 1)

            if era != previous_era:
                console_clear_status()
                if previous_era >= 0:
                    _log_era_summary(
                        previous_era,
                        battles_per_era,
                        archived_per_era,
                        unarchived_per_era,
                    )
                if previous_era < 0:
                    console_log(
                        f"========== Starting evolution in era {era + 1} of {era_count} ==========",
                        minimum_level=VerbosityLevel.DEFAULT,
                    )
                else:
                    console_log(
                        f"************** Advancing from era {previous_era + 1} to {era + 1} *******************",
                        minimum_level=VerbosityLevel.DEFAULT,
                    )
                    get_arena_storage().flush_all()
                bag = _build_marble_bag(era, active_config)

            arena_index = _select_arena_index(active_config)
            champion_id = champions.get(arena_index)
            random_pair_weight = active_config.random_pair_battle_frequency_list[era]
            champion_weight = active_config.champion_battle_frequency_list[era]
            benchmark_weight = active_config.benchmark_battle_frequency_list[era]
            benchmark_available = bool(active_config.benchmark_sets.get(arena_index))
            effective_benchmark_weight = benchmark_weight if benchmark_available else 0
            try:
                battle_type = choose_battle_type(
                    random_pair_weight,
                    champion_weight,
                    effective_benchmark_weight,
                )
            except ValueError:
                battle_type = BattleType.RANDOM_PAIR

            use_benchmark_battle = battle_type == BattleType.BENCHMARK and benchmark_available
            if battle_type == BattleType.BENCHMARK and not use_benchmark_battle:
                battle_type = BattleType.RANDOM_PAIR
            cont1, cont2 = select_opponents(
                active_config.numwarriors,
                champion_id,
                battle_type=battle_type,
            )
            display_era = era + 1
            benchmark_result: Optional[BenchmarkBattleResult] = None
            if use_benchmark_battle:
                battle_label = "Benchmark battle"
            elif battle_type == BattleType.CHAMPION:
                battle_label = "Champion battle"
            else:
                battle_label = "Battle"
            progress_line, _ = _get_progress_status(
                start_time, active_config.clock_time, era
            )
            pending_battle_line = (
                f"{battle_label}: "
                f"Era {display_era}, Arena {arena_index} | {cont1} vs {cont2} | Running..."
            )
            console_update_status(progress_line, pending_battle_line)

            if use_benchmark_battle:
                benchmark_result = _run_benchmark_battle(
                    arena_index, cont1, cont2, era, active_config
                )
                if benchmark_result is None:
                    use_benchmark_battle = False
                    battle_label = "Battle"
                    progress_line, _ = _get_progress_status(
                        start_time, active_config.clock_time, era
                    )
                    pending_battle_line = (
                        f"{battle_label}: "
                        f"Era {display_era}, Arena {arena_index} | {cont1} vs {cont2} | Running..."
                    )
                    console_update_status(progress_line, pending_battle_line)

            if use_benchmark_battle and benchmark_result is not None:
                warriors = benchmark_result.warriors
                scores = benchmark_result.scores
            else:
                battle_seed = _generate_internal_battle_seed()
                warriors, scores = execute_battle(
                    arena_index,
                    cont1,
                    cont2,
                    era,
                    verbose=verbosity == VerbosityLevel.VERBOSE,
                    seed=battle_seed,
                )
                benchmark_result = None
            if 0 <= era < len(battles_per_era):
                battles_per_era[era] += 1
            total_battles += 1
            if (
                active_config.arena_checkpoint_interval
                and total_battles % active_config.arena_checkpoint_interval == 0
            ):
                get_arena_storage().flush_all()
            winner, loser, was_draw = determine_winner_and_loser(warriors, scores)
            champion_id = champions.get(arena_index)
            if (
                champion_id in warriors
                and not was_draw
                and winner != champion_id
            ):
                champions[arena_index] = winner
                _sync_champion_display()
            get_console().record_battle(winner, loser, was_draw)

            if len(warriors) >= 2 and len(scores) >= 2:
                matchup = (
                    f"{warriors[0]} ({scores[0]}) vs {warriors[1]} ({scores[1]})"
                )
            else:
                matchup = " vs ".join(str(warrior) for warrior in warriors)
            if use_benchmark_battle and benchmark_result is not None:
                battle_result_description = None
            else:
                if was_draw:
                    battle_result_description = (
                        f"Result: Draw | Winner (selected): {winner} | Loser: {loser}"
                    )
                else:
                    battle_result_description = f"Winner: {winner} | Loser: {loser}"

            archiving_result = handle_archiving(
                winner, loser, arena_index, era, active_config
            )
            if archiving_result.events and 0 <= era < len(archived_per_era):
                for event in archiving_result.events:
                    if event.action == "archived":
                        archived_per_era[era] += 1
                    else:
                        unarchived_per_era[era] += 1

            if archiving_result.skip_breeding:
                continue

            partner_id = breed_offspring(
                winner,
                loser,
                arena_index,
                era,
                active_config,
                bag,
                data_logger,
                scores,
                warriors,
            )

            generation_counter += 1
            log_interval = active_config.benchmark_log_generation_interval
            if (
                log_interval > 0
                and generation_counter % log_interval == 0
                and benchmark_logger.enabled
            ):
                _log_benchmark_scores_for_champions(
                    era=era,
                    generation=generation_counter,
                    champions=champions,
                    active_config=active_config,
                    benchmark_logger=benchmark_logger,
                )

            battle_segments = [
                f"{battle_label}: Era {display_era}, Arena {arena_index}",
                matchup,
            ]
            if battle_result_description:
                battle_segments.append(battle_result_description)
            battle_segments.append(f"Partner: {partner_id}")
            battle_line = " | ".join(battle_segments)
            progress_line, default_detail = _get_progress_status(
                start_time, active_config.clock_time, era
            )
            console_update_status(progress_line, battle_line or default_detail)

        if 0 <= era < len(battles_per_era):
            _log_era_summary(
                era, battles_per_era, archived_per_era, unarchived_per_era
            )

    except KeyboardInterrupt:
        console_clear_status()
        console_log(
            "Evolution interrupted by user.",
            minimum_level=VerbosityLevel.TERSE,
        )
        interrupted = True

    finally:
        data_logger.close()
        benchmark_logger.close()

    end_time = time.time()

    if not interrupted:
        console_clear_status()
        console_log(
            "Evolution loop completed.",
            minimum_level=VerbosityLevel.TERSE,
        )

    _print_evolution_statistics(
        battles_per_era=battles_per_era,
        total_battles=total_battles,
        runtime_seconds=end_time - start_time,
    )

    flush_in_main_cleanup = (
        active_config.use_in_memory_arenas
        and active_config.battle_engine == "internal"
    )
    if not flush_in_main_cleanup:
        get_arena_storage().flush_all()

    if active_config.run_final_tournament:
        run_final_tournament(active_config)

    return 0


def _count_archive_warriors(archive_dir: str) -> int:
    """Legacy helper retained for tests; delegates to :class:`DiskArchiveStorage`."""

    storage = DiskArchiveStorage(archive_path=archive_dir)
    return storage.count()


def main(argv: Optional[List[str]] = None) -> int:
    try:
        return _main_impl(argv)
    finally:
        try:
            active_config = get_active_config()
        except RuntimeError:
            active_config = None
        try:
            storage = get_arena_storage()
        except RuntimeError:
            storage = None
        if storage is not None:
            try:
                should_flush = True
                if should_flush:
                    wrote_any = storage.flush_all()
            except RuntimeError:
                pass
        close_console()


if __name__ == "__main__" and os.getenv("PYTHONEVOLVER_SKIP_MAIN") != "1":
    sys.exit(main())
