import argparse
import random
import os
import sys
import time
#import psutil #Not currently active. See bottom of code for how it could be used.
import configparser
import subprocess
import shutil
from enum import Enum
import csv
import ctypes
import platform
from pathlib import Path
import re
import warnings
from dataclasses import dataclass, field
from typing import Callable, List, Literal, Optional, Sequence, TypeVar, cast


@dataclass
class EvolverConfig:
    battle_engine: str
    last_arena: int
    base_path: str
    coresize_list: list[int]
    sanitize_list: list[int]
    cycles_list: list[int]
    processes_list: list[int]
    readlimit_list: list[int]
    writelimit_list: list[int]
    warlen_list: list[int]
    wardistance_list: list[int]
    numwarriors: int
    alreadyseeded: bool
    clock_time: float
    battle_log_file: Optional[str]
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
    instr_set: list[str]
    instr_modes: list[str]
    instr_modif: list[str]
    run_final_tournament: bool


class _ConfigNotLoaded:
    def __getattr__(self, item: str):
        raise RuntimeError(
            "Active evolver configuration has not been set. Call set_active_config() "
            "or main() before using module-level helpers."
        )


config = cast(EvolverConfig, _ConfigNotLoaded())


_RNG_SEQUENCE: Optional[list[int]] = None
_RNG_INDEX: int = 0


T = TypeVar("T")


class StatusDisplay:
    """Utility for maintaining a two-line rolling status output."""

    def __init__(self) -> None:
        self._active_lines = 0

    def _stream(self):
        return sys.stdout

    def _supports_ansi(self, stream) -> bool:
        return bool(getattr(stream, "isatty", lambda: False)())

    def update(self, line1: str, line2: str) -> None:
        stream = self._stream()
        supports_ansi = self._supports_ansi(stream)
        lines = [line1, line2]

        if supports_ansi and self._active_lines:
            stream.write(f"\x1b[{self._active_lines}F")

        for line in lines:
            if supports_ansi:
                stream.write("\x1b[2K")
                stream.write(line)
                stream.write("\n")
            else:
                stream.write(line + "\n")

        stream.flush()
        self._active_lines = len(lines) if supports_ansi else 0

    def clear(self) -> None:
        if not self._active_lines:
            return

        stream = self._stream()
        supports_ansi = self._supports_ansi(stream)
        if supports_ansi:
            stream.write(f"\x1b[{self._active_lines}F")
            for index in range(self._active_lines):
                stream.write("\x1b[2K")
                if index < self._active_lines - 1:
                    stream.write("\x1b[1E")
            stream.write("\r")
            stream.flush()
        self._active_lines = 0


status_display = StatusDisplay()


def set_rng_sequence(sequence: list[int]) -> None:
    """Set a deterministic RNG sequence for tests.

    Passing an empty list disables deterministic behaviour and returns to the
    standard :mod:`random` generator.
    """

    global _RNG_SEQUENCE, _RNG_INDEX
    if sequence:
        _RNG_SEQUENCE = list(sequence)
    else:
        _RNG_SEQUENCE = None
    _RNG_INDEX = 0


def get_random_int(min_val: int, max_val: int) -> int:
    """Return a random integer within ``[min_val, max_val]``.

    When a deterministic sequence is configured via :func:`set_rng_sequence`,
    this function returns the next value from that sequence and validates that
    it lies within the requested range.
    """

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


def set_active_config(new_config: EvolverConfig) -> None:
    global config
    config = new_config
    _rebuild_instruction_tables(new_config)


def get_active_config() -> EvolverConfig:
    return config


def validate_config(config: EvolverConfig, config_path: Optional[str] = None) -> None:
    if config.last_arena is None:
        raise ValueError("LAST_ARENA must be specified in the configuration.")

    valid_engines = {"external", "internal", "pmars"}
    if config.battle_engine not in valid_engines:
        raise ValueError(
            "BATTLE_ENGINE must be one of "
            + ", ".join(sorted(valid_engines))
            + f" (got {config.battle_engine!r})."
        )

    arena_count = config.last_arena + 1
    if arena_count <= 0:
        raise ValueError(
            "LAST_ARENA must be greater than or equal to 0 (implies at least one arena)."
        )

    per_arena_lists = {
        "CORESIZE_LIST": config.coresize_list,
        "SANITIZE_LIST": config.sanitize_list,
        "CYCLES_LIST": config.cycles_list,
        "PROCESSES_LIST": config.processes_list,
        "READLIMIT_LIST": config.readlimit_list,
        "WRITELIMIT_LIST": config.writelimit_list,
        "WARLEN_LIST": config.warlen_list,
        "WARDISTANCE_LIST": config.wardistance_list,
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

    for idx in range(arena_count):
        core_size = config.coresize_list[idx]
        sanitize_limit = config.sanitize_list[idx]
        read_limit = config.readlimit_list[idx]
        write_limit = config.writelimit_list[idx]

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

    if config.numwarriors is None or config.numwarriors <= 0:
        raise ValueError("NUMWARRIORS must be a positive integer.")

    if not config.battlerounds_list:
        raise ValueError("BATTLEROUNDS_LIST must contain at least one value.")

    for idx, rounds in enumerate(config.battlerounds_list, start=1):
        if rounds < 1:
            raise ValueError(
                f"BATTLEROUNDS_LIST[{idx}] must be at least 1 (got {rounds})."
            )

    era_count = len(config.battlerounds_list)

    era_lists = {
        "NOTHING_LIST": config.nothing_list,
        "RANDOM_LIST": config.random_list,
        "NAB_LIST": config.nab_list,
        "MINI_MUT_LIST": config.mini_mut_list,
        "MICRO_MUT_LIST": config.micro_mut_list,
        "LIBRARY_LIST": config.library_list,
        "MAGIC_NUMBER_LIST": config.magic_number_list,
        "ARCHIVE_LIST": config.archive_list,
        "UNARCHIVE_LIST": config.unarchive_list,
        "CROSSOVERRATE_LIST": config.crossoverrate_list,
        "TRANSPOSITIONRATE_LIST": config.transpositionrate_list,
        "PREFER_WINNER_LIST": config.prefer_winner_list,
    }

    for name, values in era_lists.items():
        if len(values) != era_count:
            raise ValueError(
                f"{name} must contain {era_count} entries (one for each era),"
                f" but {len(values)} value(s) were provided."
            )

    marble_probability_limits = {
        "NOTHING_LIST": config.nothing_list,
        "RANDOM_LIST": config.random_list,
        "NAB_LIST": config.nab_list,
        "MINI_MUT_LIST": config.mini_mut_list,
        "MICRO_MUT_LIST": config.micro_mut_list,
        "LIBRARY_LIST": config.library_list,
        "MAGIC_NUMBER_LIST": config.magic_number_list,
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

    for idx, value in enumerate(config.crossoverrate_list, start=1):
        if value < 1:
            raise ValueError(
                f"CROSSOVERRATE_LIST[{idx}] must be at least 1 (got {value})."
            )

    for idx, value in enumerate(config.transpositionrate_list, start=1):
        if value < 1:
            raise ValueError(
                f"TRANSPOSITIONRATE_LIST[{idx}] must be at least 1 (got {value})."
            )

    base_path = getattr(config, "base_path", None) or os.getcwd()
    if config_path and not getattr(config, "base_path", None):
        config_directory = os.path.dirname(os.path.abspath(config_path))
        if config_directory:
            base_path = config_directory

    required_directories = [os.path.join(base_path, f"arena{i}") for i in range(arena_count)]
    archive_dir = os.path.join(base_path, "archive")
    required_directories.append(archive_dir)

    if not os.path.isdir(base_path):
        raise FileNotFoundError(
            f"Configuration directory '{base_path}' does not exist or is not a directory."
        )

    missing_required_directories = [
        directory for directory in required_directories if not os.path.isdir(directory)
    ]

    if missing_required_directories and config.alreadyseeded:
        missing_arenas = [
            directory
            for directory in missing_required_directories
            if os.path.basename(directory) != "archive"
        ]
        if missing_arenas:
            print(
                "ALREADYSEEDED was True but required arenas/archive are missing. "
                "Automatically switching to fresh seeding so the evolver can "
                "initialise new warriors."
            )
            config.alreadyseeded = False

        if config.alreadyseeded and archive_dir in missing_required_directories:
            try:
                os.makedirs(archive_dir, exist_ok=True)
            except OSError as exc:
                raise OSError(
                    f"Failed to create archive directory '{archive_dir}': {exc}"
                ) from exc

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
            if config.alreadyseeded:
                raise FileNotFoundError(
                    f"Required directory '{directory}' does not exist but ALREADYSEEDED is true."
                )

    if config.clock_time is None or config.clock_time <= 0:
        raise ValueError("CLOCK_TIME must be a positive number of hours.")


def load_configuration(path: str) -> EvolverConfig:
    parser = configparser.ConfigParser()
    read_files = parser.read(path)
    if not read_files:
        raise FileNotFoundError(f"Configuration file '{path}' not found")

    base_path = os.path.dirname(os.path.abspath(path)) or os.getcwd()

    def _read_config(key: str, data_type: str = 'int', default=None):
        value = parser['DEFAULT'].get(key, fallback=default)
        if value in (None, ''):
            return default

        data_type_mapping = {
            'int': int,
            'int_list': lambda x: [int(i) for i in x.split(',')],
            'bool_list': lambda x: [s.strip().lower() == 'true' for s in x.split(',') if s.strip()],
            'string_list': lambda x: [i.strip() for i in x.split(',') if i.strip()],
            'bool': lambda x: parser['DEFAULT'].getboolean(key, fallback=default),
            'float': float,
        }
        return data_type_mapping.get(data_type, lambda x: x.strip() or None)(value)

    coresize_list = _read_config('CORESIZE_LIST', data_type='int_list') or []
    sanitize_list = _read_config('SANITIZE_LIST', data_type='int_list') or []
    cycles_list = _read_config('CYCLES_LIST', data_type='int_list') or []
    processes_list = _read_config('PROCESSES_LIST', data_type='int_list') or []
    readlimit_list = _read_config('READLIMIT_LIST', data_type='int_list')
    writelimit_list = _read_config('WRITELIMIT_LIST', data_type='int_list')
    warlen_list = _read_config('WARLEN_LIST', data_type='int_list') or []
    wardistance_list = _read_config('WARDISTANCE_LIST', data_type='int_list') or []

    if not readlimit_list:
        readlimit_list = list(coresize_list)
    if not writelimit_list:
        writelimit_list = list(coresize_list)

    battle_engine = _read_config('BATTLE_ENGINE', data_type='string', default='external')
    if battle_engine:
        battle_engine = battle_engine.strip().lower()
    else:
        battle_engine = 'external'

    battle_log_file = _read_config('BATTLE_LOG_FILE', data_type='string')
    if battle_log_file:
        if not os.path.isabs(battle_log_file):
            battle_log_file = os.path.abspath(os.path.join(base_path, battle_log_file))
    else:
        battle_log_file = None

    library_path = _read_config('LIBRARY_PATH', data_type='string')
    if library_path:
        if not os.path.isabs(library_path):
            library_path = os.path.abspath(os.path.join(base_path, library_path))
    else:
        library_path = None

    config = EvolverConfig(
        battle_engine=battle_engine,
        last_arena=_read_config('LAST_ARENA', data_type='int'),
        base_path=base_path,
        coresize_list=coresize_list,
        sanitize_list=sanitize_list,
        cycles_list=cycles_list,
        processes_list=processes_list,
        readlimit_list=readlimit_list,
        writelimit_list=writelimit_list,
        warlen_list=warlen_list,
        wardistance_list=wardistance_list,
        numwarriors=_read_config('NUMWARRIORS', data_type='int'),
        alreadyseeded=_read_config('ALREADYSEEDED', data_type='bool'),
        clock_time=_read_config('CLOCK_TIME', data_type='float'),
        battle_log_file=battle_log_file,
        final_era_only=_read_config('FINAL_ERA_ONLY', data_type='bool'),
        nothing_list=_read_config('NOTHING_LIST', data_type='int_list') or [],
        random_list=_read_config('RANDOM_LIST', data_type='int_list') or [],
        nab_list=_read_config('NAB_LIST', data_type='int_list') or [],
        mini_mut_list=_read_config('MINI_MUT_LIST', data_type='int_list') or [],
        micro_mut_list=_read_config('MICRO_MUT_LIST', data_type='int_list') or [],
        library_list=_read_config('LIBRARY_LIST', data_type='int_list') or [],
        magic_number_list=_read_config('MAGIC_NUMBER_LIST', data_type='int_list') or [],
        archive_list=_read_config('ARCHIVE_LIST', data_type='int_list') or [],
        unarchive_list=_read_config('UNARCHIVE_LIST', data_type='int_list') or [],
        library_path=library_path,
        crossoverrate_list=_read_config('CROSSOVERRATE_LIST', data_type='int_list') or [],
        transpositionrate_list=_read_config('TRANSPOSITIONRATE_LIST', data_type='int_list') or [],
        battlerounds_list=_read_config('BATTLEROUNDS_LIST', data_type='int_list') or [],
        prefer_winner_list=_read_config('PREFER_WINNER_LIST', data_type='bool_list') or [],
        instr_set=_read_config('INSTR_SET', data_type='string_list') or [],
        instr_modes=_read_config('INSTR_MODES', data_type='string_list') or [],
        instr_modif=_read_config('INSTR_MODIF', data_type='string_list') or [],
        run_final_tournament=_read_config('RUN_FINAL_TOURNAMENT', data_type='bool', default=False) or False,
    )
    validate_config(config, config_path=path)
    return config

class DataLogger:
    def __init__(self, filename):
        self.filename = filename
        self.fieldnames = ['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with']
    def log_data(self, **kwargs):
        if self.filename:
            with open(self.filename, 'a', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=self.fieldnames)
                if file.tell() == 0:
                    writer.writeheader()
                writer.writerow(kwargs)

class Marble(Enum):
  DO_NOTHING = 0
  MAJOR_MUTATION = 1
  NAB_INSTRUCTION = 2
  MINOR_MUTATION = 3
  MICRO_MUTATION = 4
  INSTRUCTION_LIBRARY = 5
  MAGIC_NUMBER_MUTATION = 6

# --- C++ Worker Library Loading ---
CPP_WORKER_LIB = None

CPP_WORKER_MIN_DISTANCE = 0
CPP_WORKER_MAX_MIN_DISTANCE = 200
_WARDISTANCE_CLAMP_LOGGED: set[int] = set()


def _clamp_wardistance(value: int) -> int:
    clamped_value = max(
        CPP_WORKER_MIN_DISTANCE, min(value, CPP_WORKER_MAX_MIN_DISTANCE)
    )
    if clamped_value != value and value not in _WARDISTANCE_CLAMP_LOGGED:
        print(
            f"Configured WARDISTANCE value {value} is outside the supported range "
            f"({CPP_WORKER_MIN_DISTANCE}-{CPP_WORKER_MAX_MIN_DISTANCE}) for the "
            f"internal battle engine. Clamping to {clamped_value}."
        )
        _WARDISTANCE_CLAMP_LOGGED.add(value)
    return clamped_value


def _worker_library_extension() -> str:
    system = platform.system()
    if system == "Windows":
        return ".dll"
    if system == "Darwin":
        return ".dylib"
    return ".so"


def _candidate_worker_paths() -> list[Path]:
    lib_name = f"redcode_worker{_worker_library_extension()}"
    module_dir = Path(__file__).resolve().parent
    project_root = module_dir.parent
    candidates: list[Path] = [
        (module_dir / lib_name).resolve(),
        (project_root / lib_name).resolve(),
    ]

    system_lib_dirs = [
        Path("/usr/local/lib"),
        Path("/usr/lib"),
    ]

    for lib_dir in system_lib_dirs:
        candidates.append((lib_dir / lib_name).resolve(strict=False))

    env_override = os.environ.get("REDCODE_WORKER_PATH")
    if env_override:
        env_path = Path(env_override).expanduser()
        try:
            candidates.append(env_path.resolve(strict=False))
        except RuntimeError:
            candidates.append(env_path)
        if env_path.is_dir():
            try:
                candidates.append((env_path / lib_name).resolve(strict=False))
            except RuntimeError:
                candidates.append(env_path / lib_name)

    # Remove duplicates while preserving order
    seen = set()
    unique_candidates = []
    for path in candidates:
        try:
            key = path if path.is_absolute() else path.resolve(strict=False)
        except RuntimeError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(path)
    return unique_candidates


def _format_candidate(path: Path) -> str:
    try:
        resolved = path if path.is_absolute() else path.resolve(strict=False)
    except RuntimeError:
        resolved = path
    return str(resolved)


try:
    candidates = _candidate_worker_paths()
    loaded_path: Optional[Path] = None
    for candidate in candidates:
        try:
            CPP_WORKER_LIB = ctypes.CDLL(str(candidate))
            loaded_path = candidate
            break
        except OSError:
            continue

    if CPP_WORKER_LIB is not None and loaded_path is not None:
        CPP_WORKER_LIB.run_battle.argtypes = [
            ctypes.c_char_p, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int,
        ]
        CPP_WORKER_LIB.run_battle.restype = ctypes.c_char_p
        print(
            "Successfully loaded C++ Redcode worker from "
            f"{_format_candidate(loaded_path)}."
        )
    else:
        tried_paths = ", ".join(_format_candidate(path) for path in candidates)
        print(f"Could not load C++ Redcode worker. Tried: {tried_paths}")
        print("Internal battle engine will not be available.")
except Exception as e:
    print(f"Could not load C++ Redcode worker: {e}")
    print("Internal battle engine will not be available.")


def _candidate_pmars_paths() -> list[str]:
    exe_name = "pmars.exe" if os.name == "nt" else "pmars"
    candidates: list[str] = []

    env_override = os.environ.get("PMARS_CMD")
    if env_override:
        candidates.append(env_override)

    detected = shutil.which(exe_name)
    if detected:
        candidates.append(detected)

    project_root = Path(__file__).resolve().parent
    candidates.append(str(project_root / "pMars" / exe_name))
    candidates.append(str(project_root / "pMars" / "src" / exe_name))

    try:
        base_path = Path(config.base_path)
    except Exception:
        base_path = None
    else:
        candidates.append(str(base_path / "pMars" / exe_name))
        candidates.append(str(base_path / "pMars" / "src" / exe_name))

    candidates.append(exe_name)

    unique_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)

    return unique_candidates


def _run_external_command(
    executable: str,
    warrior_files: Sequence[str],
    flag_args: dict[str, Optional[object]] | None = None,
    *,
    prefix_args: Sequence[str] | None = None,
    warriors_first: bool = False,
) -> Optional[str]:
    """Run an external battle engine command and return its output."""

    cmd: list[str] = [executable]
    if prefix_args:
        cmd.extend(prefix_args)

    if warriors_first:
        cmd.extend(warrior_files)

    if flag_args:
        for flag, value in flag_args.items():
            cmd.append(flag)
            if value is not None:
                cmd.append(str(value))

    if not warriors_first:
        cmd.extend(warrior_files)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as e:
        print(f"Unable to run {executable}: {e}")
        return None
    except subprocess.SubprocessError as e:
        print(f"An error occurred: {e}")
        return None

    output = result.stdout or ""
    if not output and result.stderr:
        output = result.stderr
    return output


def run_nmars_command(
    arena,
    cont1,
    cont2,
    coresize,
    cycles,
    processes,
    warlen,
    wardistance,
    battlerounds,
):
    """
    nMars reference
    Rules:
      -r #      Rounds to play [1]
      -s #      Size of core [8000]
      -c #      Cycle until tie [80000]
      -p #      Max. processes [8000]
      -l #      Max. warrior length [100]
      -d #      Min. warriors distance
      -S #      Size of P-space [500]
      -f #      Fixed position series
      -xp       Disable P-space
    """

    nmars_cmd = "nmars.exe" if os.name == "nt" else "nmars"
    arena_dir = os.path.join(config.base_path, f"arena{arena}")
    warrior_files = [
        os.path.join(arena_dir, f"{cont1}.red"),
        os.path.join(arena_dir, f"{cont2}.red"),
    ]
    args = {
        "-s": coresize,
        "-c": cycles,
        "-p": processes,
        "-l": warlen,
        "-d": wardistance,
        "-r": battlerounds,
    }
    return _run_external_command(
        nmars_cmd,
        warrior_files,
        args,
        warriors_first=True,
    )


def run_pmars_command(
    arena,
    cont1,
    cont2,
    coresize,
    cycles,
    processes,
    warlen,
    wardistance,
    battlerounds,
):
    pmars_cmd = None
    for candidate in _candidate_pmars_paths():
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            pmars_cmd = candidate
            break

    if pmars_cmd is None:
        pmars_cmd = "pmars.exe" if os.name == "nt" else "pmars"

    arena_dir = os.path.join(config.base_path, f"arena{arena}")
    warrior_files = [
        os.path.join(arena_dir, f"{cont1}.red"),
        os.path.join(arena_dir, f"{cont2}.red"),
    ]

    args = {
        "-r": battlerounds,
        "-s": coresize,
        "-c": cycles,
        "-p": processes,
        "-l": warlen,
        "-d": wardistance,
    }

    return _run_external_command(
        pmars_cmd,
        warrior_files,
        args,
        prefix_args=["-b"],
    )

def run_internal_battle(
    arena,
    cont1,
    cont2,
    coresize,
    cycles,
    processes,
    readlimit,
    writelimit,
    warlen,
    wardistance,
    battlerounds,
    seed: int = -1,
):
    if not CPP_WORKER_LIB:
        raise RuntimeError(
            "Internal battle engine is required by the configuration but the "
            "C++ worker library is not loaded."
        )

    wardistance = _clamp_wardistance(wardistance)

    try:
        # 1. Read warrior files
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        w1_path = os.path.join(arena_dir, f"{cont1}.red")
        w2_path = os.path.join(arena_dir, f"{cont2}.red")
        with open(w1_path, 'r') as f:
            w1_code = f.read()
        with open(w2_path, 'r') as f:
            w2_code = f.read()

        # 2. Call the C++ function
        result_ptr = CPP_WORKER_LIB.run_battle(
            w1_code.encode('utf-8'),
            cont1,
            w2_code.encode('utf-8'),
            cont2,
            coresize,
            cycles,
            processes,
            readlimit,
            writelimit,
            wardistance,
            warlen,
            battlerounds,
            seed,
        )

        if not result_ptr:
            raise RuntimeError("C++ worker returned no result")

        # 3. Decode the result
        result_str = result_ptr.decode('utf-8')
        if result_str.strip().startswith("ERROR:"):
            raise RuntimeError(
                f"C++ worker reported an error: {result_str.strip()}"
            )
        return result_str

    except Exception as e:
        raise RuntimeError(
            f"An error occurred while running the internal battle: {e}"
        )


def execute_battle(
    arena: int,
    cont1: int,
    cont2: int,
    era: int,
    verbose: bool = True,
    battlerounds_override: Optional[int] = None,
):
    engine = config.battle_engine
    battlerounds = (
        battlerounds_override
        if battlerounds_override is not None
        else config.battlerounds_list[era]
    )
    if engine == 'internal':
        raw_output = run_internal_battle(
            arena,
            cont1,
            cont2,
            config.coresize_list[arena],
            config.cycles_list[arena],
            config.processes_list[arena],
            config.readlimit_list[arena],
            config.writelimit_list[arena],
            config.warlen_list[arena],
            config.wardistance_list[arena],
            battlerounds,
        )
    elif engine == 'pmars':
        raw_output = run_pmars_command(
            arena,
            cont1,
            cont2,
            config.coresize_list[arena],
            config.cycles_list[arena],
            config.processes_list[arena],
            config.warlen_list[arena],
            config.wardistance_list[arena],
            battlerounds,
        )
    else:
        raw_output = run_nmars_command(
            arena,
            cont1,
            cont2,
            config.coresize_list[arena],
            config.cycles_list[arena],
            config.processes_list[arena],
            config.warlen_list[arena],
            config.wardistance_list[arena],
            battlerounds,
        )

    if raw_output is None:
        raise RuntimeError("Battle engine returned no output")
    if isinstance(raw_output, bytes):
        raw_output = raw_output.decode('utf-8')
    raw_output_stripped = raw_output.strip()
    if raw_output_stripped.startswith("ERROR:"):
        raise RuntimeError(f"Battle engine reported an error: {raw_output_stripped}")

    scores = []
    warriors = []
    numline = 0
    output_lines = raw_output.splitlines()
    if not output_lines:
        raise RuntimeError("Battle engine produced no output to parse")

    is_pmars = engine == 'pmars'
    for line in output_lines:
        numline += 1
        if "scores" in line:
            if verbose:
                print(line.strip())
            if is_pmars:
                match = re.search(r"scores\s+(-?\d+)", line)
                if not match:
                    raise RuntimeError(
                        f"Unexpected pMARS score line format: {line.strip()}"
                    )
                scores.append(int(match.group(1)))
            else:
                splittedline = line.split()
                if len(splittedline) < 5:
                    raise RuntimeError(f"Unexpected score line format: {line.strip()}")
                scores.append(int(splittedline[4]))
                warriors.append(int(splittedline[0]))
    if len(scores) < 2:
        raise RuntimeError("Battle engine output did not include scores for both warriors")
    if is_pmars:
        warriors = [cont1, cont2]
    expected_warriors = {cont1, cont2}
    returned_warriors = set(warriors)
    if returned_warriors != expected_warriors:
        raise RuntimeError(
            "Battle engine returned mismatched warrior IDs: "
            f"expected {sorted(expected_warriors)}, got {sorted(returned_warriors)}"
        )
    if verbose:
        print(numline)
    return warriors, scores

DEFAULT_MODE = '$'
DEFAULT_MODIFIER = 'F'
BASE_ADDRESSING_MODES = {'$', '#', '@', '<', '>', '*', '{', '}'}
ADDRESSING_MODES: set[str] = set(BASE_ADDRESSING_MODES)

CANONICAL_SUPPORTED_OPCODES = {
    'DAT', 'MOV', 'ADD', 'SUB', 'MUL', 'DIV', 'MOD',
    'JMP', 'JMZ', 'JMN', 'DJN', 'CMP', 'SEQ', 'SNE', 'SLT', 'SPL',
    'NOP',  # Extended spec opcode supported by the C++ worker.
}
OPCODE_ALIASES = {
    'SEQ': 'CMP',
}
SUPPORTED_OPCODES = CANONICAL_SUPPORTED_OPCODES | set(OPCODE_ALIASES)
UNSUPPORTED_OPCODES = {'LDP', 'STP'}


def canonicalize_opcode(opcode: str) -> str:
    return OPCODE_ALIASES.get(opcode, opcode)


GENERATION_OPCODE_POOL: list[str] = []


def _rebuild_instruction_tables(active_config: EvolverConfig) -> None:
    global ADDRESSING_MODES, GENERATION_OPCODE_POOL

    ADDRESSING_MODES = set(BASE_ADDRESSING_MODES)
    if active_config.instr_modes:
        ADDRESSING_MODES.update(
            mode.strip() for mode in active_config.instr_modes if mode.strip()
        )

    invalid_generation_opcodes = set()
    GENERATION_OPCODE_POOL = []
    for instr in active_config.instr_set or []:
        normalized = instr.strip().upper()
        if not normalized:
            continue
        canonical_opcode = OPCODE_ALIASES.get(normalized, normalized)
        if (
            canonical_opcode in UNSUPPORTED_OPCODES
            or canonical_opcode not in CANONICAL_SUPPORTED_OPCODES
        ):
            invalid_generation_opcodes.add(normalized)
            continue
        GENERATION_OPCODE_POOL.append(canonical_opcode)

    if invalid_generation_opcodes:
        raise ValueError(
            "Unsupported opcodes specified in INSTR_SET: "
            + ', '.join(sorted(invalid_generation_opcodes))
        )

def weighted_random_number(size, length):
    if get_random_int(1, 4) == 1:
        return get_random_int(-size, size)
    else:
        return get_random_int(-length, length)

#custom function, Python modulo doesn't work how we want with negative numbers
def coremod(x, y):
    numsign = -1 if x < 0 else 1
    return (abs(x) % y) * numsign

def corenorm(x, y):
    return -(y - x) if x > y // 2 else (y + x) if x <= -(y // 2) else x


@dataclass
class RedcodeInstruction:
    opcode: str
    modifier: str = DEFAULT_MODIFIER
    a_mode: str = DEFAULT_MODE
    a_field: int = 0
    b_mode: str = DEFAULT_MODE
    b_field: int = 0
    label: Optional[str] = None

    def copy(self) -> "RedcodeInstruction":
        return RedcodeInstruction(
            opcode=self.opcode,
            modifier=self.modifier,
            a_mode=self.a_mode,
            a_field=self.a_field,
            b_mode=self.b_mode,
            b_field=self.b_field,
            label=self.label,
        )


def _tokenize_instruction(line: str):
    tokens = []
    current: List[str] = []
    for ch in line:
        if ch.isspace():
            if current:
                tokens.append(''.join(current))
                current = []
        elif ch == ',':
            if current:
                tokens.append(''.join(current))
                current = []
            tokens.append(',')
        elif ch in ADDRESSING_MODES and current and (
            current[-1].isalnum() or current[-1] in '._:'
        ):
            tokens.append(''.join(current))
            current = [ch]
        else:
            current.append(ch)
    if current:
        tokens.append(''.join(current))
    return tokens


def _split_opcode_token(token: str):
    parts = token.split('.', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return token, None


def _is_opcode_token(token: str) -> bool:
    opcode, _ = _split_opcode_token(token)
    opcode = opcode.upper()
    canonical_opcode = canonicalize_opcode(opcode)
    return (
        canonical_opcode in CANONICAL_SUPPORTED_OPCODES
        or canonical_opcode in UNSUPPORTED_OPCODES
    )


_INT_LITERAL_RE = re.compile(r'^[+-]?\d+$')


def _safe_int(value: str) -> int:
    value = value.strip()
    if not value:
        raise ValueError("Empty integer literal")
    if not _INT_LITERAL_RE.fullmatch(value):
        raise ValueError(f"Invalid integer literal: '{value}'")
    return int(value, 10)


def _ensure_int(value) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return _safe_int(str(value))


def _parse_operand(operand: str, operand_name: str):
    operand = operand.strip()
    if not operand:
        raise ValueError(f"Missing {operand_name}-field operand")
    mode = operand[0]
    if mode not in ADDRESSING_MODES:
        raise ValueError(
            f"Missing addressing mode for {operand_name}-field operand '{operand}'"
        )
    value_part = operand[1:]
    if not value_part.strip():
        raise ValueError(f"Missing value for {operand_name}-field operand")
    try:
        value = _safe_int(value_part)
    except ValueError as exc:
        raise ValueError(
            f"Invalid {operand_name}-field operand '{operand}': {exc}"
        ) from exc
    return mode, value


_INSTRUCTION_HEADER_RE = re.compile(
    r"""
    ^
    (?P<opcode>[A-Za-z]+)
    (?:\s*\.\s*(?P<modifier>[A-Za-z]+))?
    (?P<rest>.*)
    $
    """,
    re.VERBOSE,
)


def parse_redcode_instruction(line: str) -> Optional[RedcodeInstruction]:
    if not line:
        return None
    code_part = line.split(';', 1)[0].strip()
    if not code_part:
        return None
    tokens = _tokenize_instruction(code_part)
    if not tokens:
        return None

    label: Optional[str] = None
    if len(tokens) >= 2 and not _is_opcode_token(tokens[0]) and _is_opcode_token(tokens[1]):
        label = tokens[0]

    remaining = code_part
    if label is not None:
        remaining = code_part[len(label) :].lstrip()

    header_match = _INSTRUCTION_HEADER_RE.match(remaining)
    if not header_match:
        raise ValueError(f"Unable to parse instruction '{code_part}'")

    opcode_part = header_match.group('opcode')
    modifier_part = header_match.group('modifier')
    rest = header_match.group('rest') or ''

    opcode = opcode_part.upper()
    canonical_opcode = canonicalize_opcode(opcode)
    if not modifier_part:
        raise ValueError(
            f"Instruction '{code_part}' is missing a modifier; expected opcode.modifier"
        )
    modifier = modifier_part.upper()

    if canonical_opcode in UNSUPPORTED_OPCODES:
        raise ValueError(f"Opcode '{opcode}' is not supported")
    if canonical_opcode not in CANONICAL_SUPPORTED_OPCODES:
        raise ValueError(f"Unknown opcode '{opcode}'")

    operand_tokens = _tokenize_instruction(rest)
    operands = []
    current_operand = ''
    idx = 0
    while idx < len(operand_tokens):
        tok = operand_tokens[idx]
        idx += 1
        if tok == ',':
            operands.append(current_operand)
            current_operand = ''
        else:
            current_operand += tok
    if current_operand or (operand_tokens and operand_tokens[-1] == ','):
        operands.append(current_operand)

    if not operands:
        raise ValueError(
            f"Instruction '{code_part}' is missing operands; expected two operands"
        )
    if len(operands) < 2:
        raise ValueError(
            f"Instruction '{code_part}' is missing operands; expected two operands"
        )
    if len(operands) > 2:
        raise ValueError(
            f"Instruction '{code_part}' has too many operands; expected exactly two"
        )

    a_mode, a_field = _parse_operand(operands[0], 'A')
    b_mode, b_field = _parse_operand(operands[1], 'B')

    return RedcodeInstruction(
        opcode=canonical_opcode,
        modifier=modifier,
        a_mode=a_mode,
        a_field=a_field,
        b_mode=b_mode,
        b_field=b_field,
        label=label,
    )


def default_instruction() -> RedcodeInstruction:
    return RedcodeInstruction(
        opcode='DAT',
        modifier=DEFAULT_MODIFIER,
        a_mode=DEFAULT_MODE,
        a_field=0,
        b_mode=DEFAULT_MODE,
        b_field=0,
    )


def sanitize_instruction(instr: RedcodeInstruction, arena: int) -> RedcodeInstruction:
    sanitized = instr.copy()
    original_opcode = (sanitized.opcode or '').upper()
    canonical_opcode = canonicalize_opcode(original_opcode)
    sanitized.opcode = canonical_opcode
    if not sanitized.modifier:
        raise ValueError("Missing modifier for instruction")
    sanitized.modifier = sanitized.modifier.upper()
    if canonical_opcode in UNSUPPORTED_OPCODES:
        raise ValueError(f"Opcode '{original_opcode}' is not supported")
    if canonical_opcode not in CANONICAL_SUPPORTED_OPCODES:
        raise ValueError(f"Unknown opcode '{original_opcode}'")
    if sanitized.a_mode not in ADDRESSING_MODES:
        raise ValueError(
            f"Invalid addressing mode '{sanitized.a_mode}' for A-field operand"
        )
    if sanitized.b_mode not in ADDRESSING_MODES:
        raise ValueError(
            f"Invalid addressing mode '{sanitized.b_mode}' for B-field operand"
        )
    sanitized.a_field = corenorm(
        coremod(_ensure_int(sanitized.a_field), config.sanitize_list[arena]),
        config.coresize_list[arena],
    )
    sanitized.b_field = corenorm(
        coremod(_ensure_int(sanitized.b_field), config.sanitize_list[arena]),
        config.coresize_list[arena],
    )
    sanitized.label = None
    return sanitized


def format_redcode_instruction(instr: RedcodeInstruction) -> str:
    return (
        f"{instr.opcode}.{instr.modifier} "
        f"{instr.a_mode}{_ensure_int(instr.a_field)},"
        f"{instr.b_mode}{_ensure_int(instr.b_field)}\n"
    )


def instruction_to_line(instr: RedcodeInstruction, arena: int) -> str:
    return format_redcode_instruction(sanitize_instruction(instr, arena))


def parse_instruction_or_default(line: str) -> RedcodeInstruction:
    parsed = parse_redcode_instruction(line)
    return parsed if parsed else default_instruction()


def choose_random_opcode() -> str:
    if GENERATION_OPCODE_POOL:
        return _get_random_choice(GENERATION_OPCODE_POOL)
    return 'DAT'


def choose_random_modifier() -> str:
    if config.instr_modif:
        return _get_random_choice(config.instr_modif).upper()
    return DEFAULT_MODIFIER


def choose_random_mode() -> str:
    if config.instr_modes:
        return _get_random_choice(config.instr_modes)
    return DEFAULT_MODE


def generate_random_instruction(arena: int) -> RedcodeInstruction:
    num1 = weighted_random_number(config.coresize_list[arena], config.warlen_list[arena])
    num2 = weighted_random_number(config.coresize_list[arena], config.warlen_list[arena])
    opcode = choose_random_opcode()
    canonical_opcode = canonicalize_opcode(opcode)
    return RedcodeInstruction(
        opcode=canonical_opcode,
        modifier=choose_random_modifier(),
        a_mode=choose_random_mode(),
        a_field=num1,
        b_mode=choose_random_mode(),
        b_field=num2,
    )

def create_directory_if_not_exists(directory):
    if not os.path.exists(directory):
        os.mkdir(directory)


MutationHandler = Callable[[RedcodeInstruction, int, EvolverConfig, int], RedcodeInstruction]


def _apply_major_mutation(
    _instruction: RedcodeInstruction,
    arena: int,
    _config: EvolverConfig,
    _magic_number: int,
) -> RedcodeInstruction:
    return generate_random_instruction(arena)


def _apply_nab_instruction(
    instruction: RedcodeInstruction,
    arena: int,
    config: EvolverConfig,
    _magic_number: int,
) -> RedcodeInstruction:
    if config.last_arena == 0:
        return instruction

    donor_arena = get_random_int(0, config.last_arena)
    while donor_arena == arena and config.last_arena > 0:
        donor_arena = get_random_int(0, config.last_arena)

    print("Nab instruction from arena " + str(donor_arena))
    donor_dir = os.path.join(config.base_path, f"arena{donor_arena}")
    donor_file = os.path.join(
        donor_dir,
        f"{get_random_int(1, config.numwarriors)}.red",
    )

    if not os.path.exists(donor_dir) or not os.path.exists(donor_file):
        print("Donor warrior missing; skipping mutation.")
        return instruction

    try:
        with open(donor_file, "r") as donor_handle:
            donor_lines = donor_handle.readlines()
    except OSError:
        print("Unable to read donor warrior; skipping mutation.")
        return instruction

    if donor_lines:
        return parse_instruction_or_default(_get_random_choice(donor_lines))

    print("Donor warrior empty; skipping mutation.")
    return instruction


def _apply_minor_mutation(
    instruction: RedcodeInstruction,
    arena: int,
    config: EvolverConfig,
    _magic_number: int,
) -> RedcodeInstruction:
    r = get_random_int(1, 6)
    if r == 1:
        instruction.opcode = choose_random_opcode()
    elif r == 2:
        instruction.modifier = choose_random_modifier()
    elif r == 3:
        instruction.a_mode = choose_random_mode()
    elif r == 4:
        instruction.a_field = weighted_random_number(
            config.coresize_list[arena], config.warlen_list[arena]
        )
    elif r == 5:
        instruction.b_mode = choose_random_mode()
    elif r == 6:
        instruction.b_field = weighted_random_number(
            config.coresize_list[arena], config.warlen_list[arena]
        )
    return instruction


def _apply_micro_mutation(
    instruction: RedcodeInstruction,
    _arena: int,
    _config: EvolverConfig,
    _magic_number: int,
) -> RedcodeInstruction:
    if get_random_int(1, 2) == 1:
        current_value = _ensure_int(instruction.a_field)
        if get_random_int(1, 2) == 1:
            current_value = current_value + 1
        else:
            current_value = current_value - 1
        instruction.a_field = current_value
    else:
        current_value = _ensure_int(instruction.b_field)
        if get_random_int(1, 2) == 1:
            current_value = current_value + 1
        else:
            current_value = current_value - 1
        instruction.b_field = current_value
    return instruction


def _apply_instruction_library(
    instruction: RedcodeInstruction,
    _arena: int,
    config: EvolverConfig,
    _magic_number: int,
) -> RedcodeInstruction:
    if not config.library_path or not os.path.exists(config.library_path):
        return instruction

    print("Instruction library")
    with open(config.library_path, "r") as library_handle:
        library_lines = library_handle.readlines()
    if library_lines:
        return parse_instruction_or_default(_get_random_choice(library_lines))
    return default_instruction()


def _apply_magic_number_mutation(
    instruction: RedcodeInstruction,
    _arena: int,
    _config: EvolverConfig,
    magic_number: int,
) -> RedcodeInstruction:
    if get_random_int(1, 2) == 1:
        instruction.a_field = magic_number
    else:
        instruction.b_field = magic_number
    return instruction


MUTATION_HANDLERS: dict[Marble, MutationHandler] = {
    Marble.MAJOR_MUTATION: _apply_major_mutation,
    Marble.NAB_INSTRUCTION: _apply_nab_instruction,
    Marble.MINOR_MUTATION: _apply_minor_mutation,
    Marble.MICRO_MUTATION: _apply_micro_mutation,
    Marble.INSTRUCTION_LIBRARY: _apply_instruction_library,
    Marble.MAGIC_NUMBER_MUTATION: _apply_magic_number_mutation,
}


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f} seconds"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)} minutes {secs:.2f} seconds"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)} hours {int(minutes)} minutes {secs:.2f} seconds"


def run_final_tournament(config: EvolverConfig):
    status_display.clear()
    if config.last_arena < 0:
        print("No arenas configured. Skipping final tournament.")
        return
    if config.numwarriors <= 1:
        print("Not enough warriors to run a final tournament.")
        return
    if not config.battlerounds_list:
        print("Battle rounds configuration missing. Cannot run final tournament.")
        return

    final_era_index = max(0, len(config.battlerounds_list) - 1)
    print("\n================ Final Tournament ================")
    arenas_to_run: list[tuple[int, list[int]]] = []
    total_battles = 0
    for arena in range(0, config.last_arena + 1):
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        if not os.path.isdir(arena_dir):
            print(f"Arena {arena} directory '{arena_dir}' not found. Skipping.")
            continue

        warrior_ids = [
            warrior_id
            for warrior_id in range(1, config.numwarriors + 1)
            if os.path.exists(os.path.join(arena_dir, f"{warrior_id}.red"))
        ]

        if len(warrior_ids) < 2:
            print(f"Arena {arena}: not enough warriors for a tournament. Skipping.")
            continue

        arenas_to_run.append((arena, warrior_ids))
        total_battles += len(warrior_ids) * (len(warrior_ids) - 1) // 2

    if not arenas_to_run:
        print("No arenas with enough warriors for the final tournament.")
        return

    tournament_start = time.time()
    battles_completed = 0
    for arena, warrior_ids in arenas_to_run:
        total_scores = {warrior_id: 0 for warrior_id in warrior_ids}

        for idx, cont1 in enumerate(warrior_ids):
            for cont2 in warrior_ids[idx + 1 :]:
                warriors, scores = execute_battle(
                    arena,
                    cont1,
                    cont2,
                    final_era_index,
                    verbose=False,
                    battlerounds_override=1,
                )
                for warrior_id, score in zip(warriors, scores):
                    total_scores[warrior_id] = total_scores.get(warrior_id, 0) + score

                battles_completed += 1
                percent_complete = (
                    battles_completed / total_battles * 100 if total_battles else 100.0
                )
                progress_line = (
                    f"Final Tournament Progress: {battles_completed}/{total_battles} "
                    f"battles ({percent_complete:.2f}% complete)"
                )
                if len(warriors) >= 2 and len(scores) >= 2:
                    battle_line = (
                        f"Arena {arena} | {warriors[0]} ({scores[0]}) vs "
                        f"{warriors[1]} ({scores[1]})"
                    )
                else:
                    battle_line = f"Arena {arena} battle in progress"
                status_display.update(progress_line, battle_line)

        status_display.clear()
        print(f"\nArena {arena} final standings:")
        rankings = sorted(total_scores.items(), key=lambda item: item[1], reverse=True)
        for position, (warrior_id, score) in enumerate(rankings, start=1):
            print(f"{position}. Warrior {warrior_id}: {score} points")
        champion_id, champion_score = rankings[0]
        print(
            f"Champion: Warrior {champion_id} with {champion_score} points"
        )

    status_display.clear()
    duration = time.time() - tournament_start
    print(f"Final tournament completed in {_format_duration(duration)}.")


def _build_marble_bag(era: int, config: EvolverConfig) -> list[Marble]:
    return (
        [Marble.DO_NOTHING] * config.nothing_list[era]
        + [Marble.MAJOR_MUTATION] * config.random_list[era]
        + [Marble.NAB_INSTRUCTION] * config.nab_list[era]
        + [Marble.MINOR_MUTATION] * config.mini_mut_list[era]
        + [Marble.MICRO_MUTATION] * config.micro_mut_list[era]
        + [Marble.INSTRUCTION_LIBRARY] * config.library_list[era]
        + [Marble.MAGIC_NUMBER_MUTATION] * config.magic_number_list[era]
    )


def select_opponents(num_warriors: int) -> tuple[int, int]:
    cont1 = random.randint(1, num_warriors)
    cont2 = cont1
    while cont2 == cont1:
        cont2 = random.randint(1, num_warriors)
    return cont1, cont2


def determine_winner_and_loser(
    warriors: list[int], scores: list[int]
) -> tuple[int, int, bool]:
    if len(warriors) < 2 or len(scores) < 2:
        raise ValueError("Expected scores for two warriors")

    if scores[1] == scores[0]:
        draw_selection = get_random_int(1, 2)
        if draw_selection == 1:
            winner = warriors[1]
            loser = warriors[0]
        else:
            winner = warriors[0]
            loser = warriors[1]
        return winner, loser, True
    if scores[1] > scores[0]:
        return warriors[1], warriors[0], False
    return warriors[0], warriors[1], False


@dataclass
class ArchivingEvent:
    action: Literal["archived", "unarchived"]
    warrior_id: int
    archive_filename: Optional[str] = None


@dataclass
class ArchivingResult:
    skip_breeding: bool = False
    events: list[ArchivingEvent] = field(default_factory=list)


def handle_archiving(
    winner: int, loser: int, arena: int, era: int, config: EvolverConfig
) -> ArchivingResult:
    arena_dir = os.path.join(config.base_path, f"arena{arena}")
    archive_dir = os.path.join(config.base_path, "archive")
    events: list[ArchivingEvent] = []

    if config.archive_list[era] != 0 and get_random_int(1, config.archive_list[era]) == 1:
        with open(os.path.join(arena_dir, f"{winner}.red"), "r") as fw:
            winlines = fw.readlines()
        archive_filename = f"{get_random_int(1, 9999)}.red"
        create_directory_if_not_exists(archive_dir)
        with open(os.path.join(archive_dir, archive_filename), "w") as fd:
            fd.writelines(winlines)
        events.append(
            ArchivingEvent(
                action="archived",
                warrior_id=winner,
                archive_filename=archive_filename,
            )
        )

    if config.unarchive_list[era] != 0 and get_random_int(1, config.unarchive_list[era]) == 1:
        if not os.path.isdir(archive_dir):
            return ArchivingResult(events=events)
        archive_files = os.listdir(archive_dir)
        if not archive_files:
            return ArchivingResult(events=events)
        archive_choice = _get_random_choice(archive_files)
        with open(os.path.join(archive_dir, archive_choice)) as fs:
            sourcelines = fs.readlines()

        instructions_written = 0
        with open(os.path.join(arena_dir, f"{loser}.red"), "w") as fl:
            for line in sourcelines:
                instruction = parse_redcode_instruction(line)
                if instruction is None:
                    continue
                fl.write(instruction_to_line(instruction, arena))
                instructions_written += 1
                if instructions_written >= config.warlen_list[arena]:
                    break
            while instructions_written < config.warlen_list[arena]:
                fl.write(instruction_to_line(default_instruction(), arena))
                instructions_written += 1
        events.append(
            ArchivingEvent(
                action="unarchived",
                warrior_id=loser,
                archive_filename=archive_choice,
            )
        )
        return ArchivingResult(skip_breeding=True, events=events)

    return ArchivingResult(events=events)


def breed_offspring(
    winner: int,
    loser: int,
    arena: int,
    era: int,
    config: EvolverConfig,
    bag: list[Marble],
    data_logger: DataLogger,
    scores: list[int],
    warriors: list[int],
):
    arena_dir = os.path.join(config.base_path, f"arena{arena}")
    with open(os.path.join(arena_dir, f"{winner}.red"), "r") as fw:
        winlines = fw.readlines()

    partner_id = get_random_int(1, config.numwarriors)
    with open(os.path.join(arena_dir, f"{partner_id}.red"), "r") as fr:
        ranlines = fr.readlines()

    if get_random_int(1, config.transpositionrate_list[era]) == 1:
        transpositions = get_random_int(1, int((config.warlen_list[arena] + 1) / 2))
        for _ in range(1, transpositions):
            fromline = get_random_int(0, config.warlen_list[arena] - 1)
            toline = get_random_int(0, config.warlen_list[arena] - 1)
            if get_random_int(1, 2) == 1:
                if fromline < len(winlines) and toline < len(winlines):
                    winlines[toline], winlines[fromline] = (
                        winlines[fromline],
                        winlines[toline],
                    )
            else:
                if fromline < len(ranlines) and toline < len(ranlines):
                    ranlines[toline], ranlines[fromline] = (
                        ranlines[fromline],
                        ranlines[toline],
                    )

    if config.prefer_winner_list[era] is True:
        pickingfrom = 1
    else:
        pickingfrom = get_random_int(1, 2)

    magic_number = weighted_random_number(
        config.coresize_list[arena], config.warlen_list[arena]
    )
    with open(os.path.join(arena_dir, f"{loser}.red"), "w") as fl:
        for i in range(0, config.warlen_list[arena]):
            if get_random_int(1, config.crossoverrate_list[era]) == 1:
                pickingfrom = 2 if pickingfrom == 1 else 1

            if pickingfrom == 1:
                source_line = winlines[i] if i < len(winlines) else ""
            else:
                source_line = ranlines[i] if i < len(ranlines) else ""

            instruction = parse_instruction_or_default(source_line)
            chosen_marble = _get_random_choice(bag)
            handler = MUTATION_HANDLERS.get(chosen_marble)
            if handler:
                instruction = handler(instruction, arena, config, magic_number)

            fl.write(instruction_to_line(instruction, arena))
            magic_number = magic_number - 1

    data_logger.log_data(
        era=era,
        arena=arena,
        winner=winner,
        loser=loser,
        score1=scores[0],
        score2=scores[1],
        bred_with=str(partner_id),
    )
    return partner_id

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Python Evolver Stage")
    parser.add_argument(
        "--config",
        default="settings.ini",
        help="Path to configuration INI file (default: settings.ini)",
    )
    parser.add_argument(
        "--engine",
        choices=["internal", "external", "pmars"],
        help="Override the configured battle engine",
    )
    parser.add_argument(
        "--final-tournament",
        action="store_true",
        help="Force a final tournament once the evolution loop completes",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Seed the RNG for reproducible runs",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print battle engine output while evolving",
    )

    args = parser.parse_args(argv)

    active_config = load_configuration(args.config)
    if args.engine:
        active_config.battle_engine = args.engine
    if args.final_tournament:
        active_config.run_final_tournament = True

    set_active_config(active_config)

    if args.seed is not None:
        random.seed(args.seed)

    if not active_config.alreadyseeded:
        print("Seeding")
        archive_dir = os.path.join(active_config.base_path, "archive")
        create_directory_if_not_exists(archive_dir)
        for arena in range(0, active_config.last_arena + 1):
            arena_dir = os.path.join(active_config.base_path, f"arena{arena}")
            create_directory_if_not_exists(arena_dir)
            for warrior_id in range(1, active_config.numwarriors + 1):
                with open(
                    os.path.join(arena_dir, f"{warrior_id}.red"), "w"
                ) as warrior_file:
                    for _ in range(1, active_config.warlen_list[arena] + 1):
                        instruction = generate_random_instruction(arena)
                        warrior_file.write(instruction_to_line(instruction, arena))

    start_time = time.time()
    era = -1
    data_logger = DataLogger(filename=active_config.battle_log_file)
    bag: list[Marble] = []
    interrupted = False
    era_count = len(active_config.battlerounds_list)
    era_duration = active_config.clock_time / era_count

    try:
        while True:
            previous_era = era
            runtime_in_hours = (time.time() - start_time) / 3600

            if runtime_in_hours > active_config.clock_time:
                status_display.clear()
                print("Clock time exceeded. Ending evolution loop.")
                break

            if active_config.final_era_only:
                era = era_count - 1
            else:
                era = min(int(runtime_in_hours / era_duration), era_count - 1)

            if era != previous_era:
                status_display.clear()
                if previous_era < 0:
                    print(
                        f"========== Starting evolution in era {era + 1} of {era_count} =========="
                    )
                else:
                    print(
                        f"************** Advancing from era {previous_era + 1} to {era + 1} *******************"
                    )
                bag = _build_marble_bag(era, active_config)

            arena_index = random.randint(0, active_config.last_arena)
            cont1, cont2 = select_opponents(active_config.numwarriors)
            hours_remaining = active_config.clock_time - runtime_in_hours
            percent_complete = runtime_in_hours / active_config.clock_time * 100
            display_era = era + 1
            pending_battle_line = (
                "Battle: "
                f"Era {display_era}, Arena {arena_index} | {cont1} vs {cont2} | Running..."
            )
            progress_line = (
                f"{hours_remaining:.2f} hours remaining ({percent_complete:.2f}% complete) "
                f"Era: {display_era}"
            )
            status_display.update(progress_line, pending_battle_line)
            warriors, scores = execute_battle(
                arena_index,
                cont1,
                cont2,
                era,
                verbose=args.verbose,
            )
            winner, loser, was_draw = determine_winner_and_loser(warriors, scores)

            if len(warriors) >= 2 and len(scores) >= 2:
                matchup = (
                    f"{warriors[0]} ({scores[0]}) vs {warriors[1]} ({scores[1]})"
                )
            else:
                matchup = " vs ".join(str(warrior) for warrior in warriors)
            if was_draw:
                battle_result_description = (
                    f"Result: Draw | Winner (selected): {winner} | Loser: {loser}"
                )
            else:
                battle_result_description = f"Winner: {winner} | Loser: {loser}"

            archiving_result = handle_archiving(
                winner, loser, arena_index, era, active_config
            )
            if archiving_result.events:
                runtime_in_hours = (time.time() - start_time) / 3600
                hours_remaining = max(active_config.clock_time - runtime_in_hours, 0.0)
                percent_complete = (
                    runtime_in_hours / active_config.clock_time * 100
                    if active_config.clock_time
                    else 100.0
                )
                progress_line = (
                    f"{hours_remaining:.2f} hours remaining ({percent_complete:.2f}% complete) "
                    f"Era: {display_era}"
                )
                status_display.clear()
                last_event_line = ""
                for event in archiving_result.events:
                    if event.action == "archived":
                        if event.archive_filename:
                            action_detail = (
                                f"Archived Warrior {event.warrior_id} to {event.archive_filename}"
                            )
                        else:
                            action_detail = f"Archived Warrior {event.warrior_id}"
                    else:
                        if event.archive_filename:
                            action_detail = (
                                f"Unarchived Warrior {event.warrior_id} from {event.archive_filename}"
                            )
                        else:
                            action_detail = (
                                f"Unarchived Warrior {event.warrior_id}"
                            )
                    last_event_line = (
                        "Battle: "
                        f"Era {display_era}, Arena {arena_index} | {matchup} | {battle_result_description} "
                        f"| Action: {action_detail}"
                    )
                    print(last_event_line, flush=True)
                status_display.update(progress_line, last_event_line)

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

            runtime_in_hours = (time.time() - start_time) / 3600
            hours_remaining = max(active_config.clock_time - runtime_in_hours, 0.0)
            percent_complete = (
                runtime_in_hours / active_config.clock_time * 100
                if active_config.clock_time
                else 100.0
            )
            battle_line = (
                "Battle: "
                f"Era {display_era}, Arena {arena_index} | {matchup} | {battle_result_description} "
                f"| Partner: {partner_id}"
            )
            progress_line = (
                f"{hours_remaining:.2f} hours remaining ({percent_complete:.2f}% complete) "
                f"Era: {display_era}"
            )
            status_display.update(progress_line, battle_line)

    except KeyboardInterrupt:
        status_display.clear()
        print("Evolution interrupted by user.")
        interrupted = True

    if not interrupted:
        status_display.clear()
        print("Evolution loop completed.")

    if active_config.run_final_tournament:
        run_final_tournament(active_config)

    return 0


if __name__ == "__main__" and os.getenv("PYTHONEVOLVER_SKIP_MAIN") != "1":
    sys.exit(main())
