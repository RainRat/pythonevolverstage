import configparser
import os
import warnings
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple, cast

from constants import (
    CPP_WORKER_MAX_CORE_SIZE,
    CPP_WORKER_MAX_CYCLES,
    CPP_WORKER_MAX_PROCESSES,
    CPP_WORKER_MAX_ROUNDS,
    CPP_WORKER_MAX_WARRIOR_LENGTH,
    CPP_WORKER_MIN_CORE_SIZE,
    CPP_WORKER_MIN_DISTANCE,
)
from ui import VerbosityLevel, console_log

BASE_ADDRESSING_MODES = {"$", "#", "@", "<", ">", "*", "{", "}"}
MAX_WARRIOR_FILENAME_ID = 65534


@dataclass
class BenchmarkWarrior:
    name: str
    code: str
    path: str


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
    final_tournament_only: bool
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


def _parse_int(value: str, *, key: str, parser: configparser.ConfigParser) -> int:
    return int(value)


def _parse_float(value: str, *, key: str, parser: configparser.ConfigParser) -> float:
    return float(value)


def _parse_bool(value: str, *, key: str, parser: configparser.ConfigParser) -> bool:
    value_lower = value.strip().lower()
    if value_lower in {"1", "true", "yes", "on"}:
        return True
    if value_lower in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value for {key}: {value}")


def _parse_int_list(value: str, *, key: str, parser: configparser.ConfigParser) -> list[int]:
    if not value.strip():
        return []
    try:
        return [int(item.strip()) for item in value.split(",")]
    except ValueError as exc:
        raise ValueError(f"Invalid integer list for {key}: {value}") from exc


def _parse_bool_list(value: str, *, key: str, parser: configparser.ConfigParser) -> list[bool]:
    if not value.strip():
        return []
    return [_parse_bool(item, key=key, parser=parser) for item in value.split(",")]


def _parse_string_list(value: str, *, key: str, parser: configparser.ConfigParser) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]

_CONFIG_PARSERS: dict[str, Callable[..., object]] = {
    "int": _parse_int,
    "float": _parse_float,
    "bool": _parse_bool,
    "int_list": _parse_int_list,
    "bool_list": _parse_bool_list,
    "string_list": _parse_string_list,
    "str": lambda value, **_: value,
}


def set_active_config(new_config: EvolverConfig) -> None:
    global config
    config = new_config


def get_active_config() -> EvolverConfig:
    return config


def get_arena_spec(arena: int) -> str:
    active_config = get_active_config()
    specs = getattr(active_config, "arena_spec_list", None)
    if specs and arena < len(specs) and specs[arena]:
        return specs[arena]
    return "1994"


def _validate_arena_parameters(idx: int, active_config: EvolverConfig) -> None:
    min_core_size = CPP_WORKER_MIN_CORE_SIZE
    max_core_size = CPP_WORKER_MAX_CORE_SIZE
    max_cycles = CPP_WORKER_MAX_CYCLES
    max_processes = CPP_WORKER_MAX_PROCESSES
    max_warrior_length = CPP_WORKER_MAX_WARRIOR_LENGTH
    min_distance = CPP_WORKER_MIN_DISTANCE

    core_size = active_config.coresize_list[idx]
    sanitize_limit = active_config.sanitize_list[idx]
    cycles_limit = active_config.cycles_list[idx]
    process_limit = active_config.processes_list[idx]
    warrior_length = active_config.warlen_list[idx]
    wardistance = active_config.wardistance_list[idx]
    read_limit = active_config.readlimit_list[idx]
    write_limit = active_config.writelimit_list[idx]

    max_min_distance = core_size // 2

    if core_size < min_core_size:
        raise ValueError(
            f"CORESIZE_LIST[{idx + 1}] must be at least {min_core_size} (got {core_size})."
        )
    if core_size > max_core_size:
        raise ValueError(
            f"CORESIZE_LIST[{idx + 1}] cannot exceed {max_core_size} (got {core_size})."
        )
    if cycles_limit <= 0 or cycles_limit > max_cycles:
        raise ValueError(
            f"CYCLES_LIST[{idx + 1}] must be between 1 and {max_cycles} (got {cycles_limit})."
        )
    if process_limit <= 0 or process_limit > max_processes:
        raise ValueError(
            f"PROCESSES_LIST[{idx + 1}] must be between 1 and {max_processes} (got {process_limit})."
        )
    if warrior_length <= 0 or warrior_length > max_warrior_length:
        raise ValueError(
            "WARLEN_LIST[{idx + 1}] must be between 1 and "
            f"{max_warrior_length} (got {warrior_length})."
        )
    if warrior_length > core_size:
        raise ValueError(
            f"WARLEN_LIST[{idx + 1}] cannot exceed the arena's core size (got {warrior_length})."
        )
    if wardistance < min_distance or wardistance > max_min_distance:
        raise ValueError(
            f"WARDISTANCE_LIST[{idx + 1}] must be between {min_distance} and "
            f"{max_min_distance} (CORESIZE/2) (got {wardistance})."
        )
    if wardistance < warrior_length:
        raise ValueError(
            "WARDISTANCE_LIST values must be greater than or equal to their corresponding "
            "WARLEN_LIST values and fall within 0..(CORESIZE/2) to prevent overlap ("
            f"got wardistance={wardistance}, warlen={warrior_length} at index {idx + 1})."
        )
    if sanitize_limit < 1 or sanitize_limit > core_size:
        raise ValueError(
            f"SANITIZE_LIST[{idx + 1}] must be between 1 and the arena's core size (got {sanitize_limit})."
        )
    if read_limit <= 0 or read_limit > core_size:
        raise ValueError(
            f"READLIMIT_LIST[{idx + 1}] must be between 1 and the arena's core size (got {read_limit})."
        )
    if write_limit <= 0 or write_limit > core_size:
        raise ValueError(
            f"WRITELIMIT_LIST[{idx + 1}] must be between 1 and the arena's core size (got {write_limit})."
        )


def _detect_existing_seed(active_config: EvolverConfig) -> tuple[bool, list[str]]:
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
    from battle_runner import CPP_WORKER_MAX_ROUNDS

    if active_config.last_arena is None:
        raise ValueError("LAST_ARENA must be specified in the configuration.")

    if active_config.benchmark_final_tournament and not active_config.benchmark_root:
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
        raise ValueError("ARENA_CHECKPOINT_INTERVAL must be a positive integer.")

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
            "BENCHMARK_BATTLE_FREQUENCY_LIST must contain either 1 value or one value per era."
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

    for value in champion_frequency_list:
        if value < 0:
            raise ValueError(
                "CHAMPION_BATTLE_FREQUENCY_LIST entries cannot be negative."
            )

    for value in random_pair_frequency_list:
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

    if active_config.benchmark_log_generation_interval < 0:
        raise ValueError("BENCHMARK_LOG_GENERATION_INTERVAL cannot be negative.")

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


def load_configuration(path: str) -> EvolverConfig:
    parser = configparser.ConfigParser()
    read_files = parser.read(path)
    if not read_files:
        raise FileNotFoundError(f"Configuration file '{path}' not found")

    base_path = os.path.dirname(os.path.abspath(path)) or os.getcwd()

    def _normalize_spec(value: str, index: int) -> str:
        normalized = value.strip().lower()
        if normalized in {"1994", "94"}:
            return "1994"
        if normalized in {"1988", "88"}:
            return "1988"
        raise ValueError(
            "SPEC_LIST entries must be '1994' or '1988'. "
            f"Invalid value '{value}' at position {index + 1}."
        )

    def _read_config(key: str, data_type: str = "int", default=None):
        value = parser["DEFAULT"].get(key, fallback=default)
        if value in (None, ""):
            return default
        if key not in parser["DEFAULT"]:
            return value
        parser_fn = _CONFIG_PARSERS.get(data_type)
        if parser_fn is None:
            raise ValueError(f"Unsupported data type: {data_type}")
        return parser_fn(value, key=key, parser=parser)

    last_arena_value = _read_config("LAST_ARENA", data_type="int")
    if last_arena_value is None:
        raise ValueError("LAST_ARENA must be specified in the configuration.")

    spec_entries = _read_config("SPEC_LIST", data_type="string_list") or []
    arena_count = last_arena_value + 1
    normalized_specs: list[str] = []
    for idx in range(arena_count):
        if idx < len(spec_entries):
            normalized_specs.append(_normalize_spec(spec_entries[idx], idx))
        else:
            normalized_specs.append("1994")

    battle_log_file = _read_config("BATTLE_LOG_FILE", data_type="str")
    if battle_log_file:
        battle_log_file = os.path.abspath(os.path.join(base_path, battle_log_file))

    benchmark_log_file = _read_config("BENCHMARK_LOG_FILE", data_type="str")
    if benchmark_log_file:
        benchmark_log_file = os.path.abspath(
            os.path.join(base_path, benchmark_log_file)
        )

    benchmark_log_generation_interval = (
        _read_config("BENCHMARK_LOG_GENERATION_INTERVAL", data_type="int", default=0)
        or 0
    )

    final_tournament_csv = _read_config("FINAL_TOURNAMENT_CSV", data_type="str")
    if final_tournament_csv:
        final_tournament_csv = os.path.abspath(
            os.path.join(base_path, final_tournament_csv)
        )

    library_path = _read_config("LIBRARY_PATH", data_type="str")
    if library_path:
        library_path = os.path.abspath(os.path.join(base_path, library_path))

    benchmark_root = _read_config("BENCHMARK_ROOT", data_type="str")
    if benchmark_root:
        benchmark_root = os.path.abspath(os.path.join(base_path, benchmark_root))

    archive_path = _read_config("ARCHIVE_PATH", data_type="str")
    if archive_path:
        archive_path = os.path.expanduser(archive_path)
        if not os.path.isabs(archive_path):
            archive_path = os.path.abspath(os.path.join(base_path, archive_path))
        else:
            archive_path = os.path.abspath(archive_path)
    else:
        archive_path = os.path.abspath(os.path.join(base_path, "archive"))

    battlerounds_list = _read_config("BATTLEROUNDS_LIST", data_type="int_list") or []
    prefer_winner_list = _read_config("PREFER_WINNER_LIST", data_type="bool_list") or []
    legacy_champion_chance_list = (
        _read_config("CHAMPION_BATTLE_CHANCE_LIST", data_type="int_list") or []
    )
    champion_battle_frequency_list = (
        _read_config("CHAMPION_BATTLE_FREQUENCY_LIST", data_type="int_list") or []
    )
    random_pair_battle_frequency_list = (
        _read_config("RANDOM_PAIR_BATTLE_FREQUENCY_LIST", data_type="int_list") or []
    )

    archive_list = _read_config("ARCHIVE_LIST", data_type="int_list") or []
    # Cap archive and unarchive chances to a minimum 1-in-10 probability
    archive_list = [max(10, x) if x != 0 else 0 for x in archive_list]
    unarchive_list = _read_config("UNARCHIVE_LIST", data_type="int_list") or []
    unarchive_list = [max(10, x) if x != 0 else 0 for x in unarchive_list]
    if "ARCHIVE_LIST" not in parser["DEFAULT"] and battlerounds_list:
        archive_list = [0] * len(battlerounds_list)
    if "UNARCHIVE_LIST" not in parser["DEFAULT"] and battlerounds_list:
        unarchive_list = [0] * len(battlerounds_list)

    benchmark_frequency_list = _read_config(
        "BENCHMARK_BATTLE_FREQUENCY_LIST", data_type="int_list"
    )
    if benchmark_frequency_list:
        benchmark_frequency_list = list(benchmark_frequency_list)
    else:
        fallback_frequency = _read_config(
            "BENCHMARK_BATTLE_FREQUENCY", data_type="int", default=0
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
        battle_engine=_read_config(
            "BATTLE_ENGINE", data_type="str", default="internal"
        )
        or "internal",
        last_arena=last_arena_value,
        base_path=base_path,
        archive_path=archive_path,
        coresize_list=_read_config("CORESIZE_LIST", data_type="int_list") or [],
        sanitize_list=_read_config("SANITIZE_LIST", data_type="int_list") or [],
        cycles_list=_read_config("CYCLES_LIST", data_type="int_list") or [],
        processes_list=_read_config("PROCESSES_LIST", data_type="int_list") or [],
        readlimit_list=_read_config("READLIMIT_LIST", data_type="int_list") or [],
        writelimit_list=_read_config("WRITELIMIT_LIST", data_type="int_list") or [],
        warlen_list=_read_config("WARLEN_LIST", data_type="int_list") or [],
        wardistance_list=_read_config("WARDISTANCE_LIST", data_type="int_list") or [],
        arena_spec_list=normalized_specs,
        arena_weight_list=_read_config("ARENA_WEIGHT_LIST", data_type="int_list") or [],
        numwarriors=_read_config("NUMWARRIORS", data_type="int"),
        alreadyseeded=False,
        use_in_memory_arenas=_read_config(
            "IN_MEMORY_ARENAS", data_type="bool", default=False
        )
        or False,
        arena_checkpoint_interval=_read_config(
            "ARENA_CHECKPOINT_INTERVAL", data_type="int", default=10000
        )
        or 10000,
        clock_time=_read_config("CLOCK_TIME", data_type="float"),
        battle_log_file=battle_log_file,
        benchmark_log_file=benchmark_log_file,
        benchmark_log_generation_interval=benchmark_log_generation_interval,
        final_era_only=_read_config("FINAL_ERA_ONLY", data_type="bool"),
        final_tournament_only=
        _read_config("FINAL_TOURNAMENT_ONLY", data_type="bool") or False,
        nothing_list=_read_config("NOTHING_LIST", data_type="int_list") or [],
        random_list=_read_config("RANDOM_LIST", data_type="int_list") or [],
        nab_list=_read_config("NAB_LIST", data_type="int_list") or [],
        mini_mut_list=_read_config("MINI_MUT_LIST", data_type="int_list") or [],
        micro_mut_list=_read_config("MICRO_MUT_LIST", data_type="int_list") or [],
        library_list=_read_config("LIBRARY_LIST", data_type="int_list") or [],
        magic_number_list=_read_config("MAGIC_NUMBER_LIST", data_type="int_list") or [],
        archive_list=archive_list,
        unarchive_list=unarchive_list,
        library_path=library_path,
        crossoverrate_list=_read_config("CROSSOVERRATE_LIST", data_type="int_list") or [],
        transpositionrate_list=_read_config("TRANSPOSITIONRATE_LIST", data_type="int_list")
        or [],
        battlerounds_list=battlerounds_list,
        prefer_winner_list=prefer_winner_list,
        champion_battle_frequency_list=champion_battle_frequency_list,
        random_pair_battle_frequency_list=random_pair_battle_frequency_list,
        instr_set=_read_config("INSTR_SET", data_type="string_list") or [],
        instr_modes=_read_config("INSTR_MODES", data_type="string_list") or [],
        instr_modif=_read_config("INSTR_MODIF", data_type="string_list") or [],
        run_final_tournament=
        _read_config("RUN_FINAL_TOURNAMENT", data_type="bool", default=False) or False,
        final_tournament_csv=final_tournament_csv,
        benchmark_root=benchmark_root,
        benchmark_final_tournament=
        _read_config("BENCHMARK_FINAL_TOURNAMENT", data_type="bool", default=False)
        or False,
        benchmark_battle_frequency_list=benchmark_frequency_list,
    )

    if not active_config.readlimit_list:
        active_config.readlimit_list = list(active_config.coresize_list)
    if not active_config.writelimit_list:
        active_config.writelimit_list = list(active_config.coresize_list)
    validate_config(active_config, config_path=path)

    if active_config.benchmark_root:
        active_config.benchmark_sets = _load_benchmark_sets(active_config)

    return active_config
