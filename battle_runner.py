from __future__ import annotations

import ctypes
import hashlib
import os
import platform
import random
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union

from config import get_active_config, get_arena_spec
from constants import (
    CPP_WORKER_MAX_CORE_SIZE,
    CPP_WORKER_MAX_CYCLES,
    CPP_WORKER_MAX_PROCESSES,
    CPP_WORKER_MAX_ROUNDS,
    CPP_WORKER_MAX_WARRIOR_LENGTH,
    CPP_WORKER_MIN_CORE_SIZE,
    CPP_WORKER_MIN_DISTANCE,
)
from redcode import SPEC_1988, _PMARS_SCORE_RE
from storage import get_arena_storage
from ui import VerbosityLevel, console_log

CPP_WORKER_LIB = None

_rng_int = random.randint

_sync_export = lambda name, value: None


def _get_evolverstage_override(name: str, default):
    module = sys.modules.get("evolverstage")
    if module is not None and hasattr(module, name):
        return getattr(module, name)
    return default


def set_sync_export(helper) -> None:
    global _sync_export
    _sync_export = helper


def configure_battle_rng(random_int_func) -> None:
    global _rng_int
    _rng_int = random_int_func


def _require_battle_config():
    active_config = get_active_config()
    config_module = sys.modules.get("config")
    placeholder_cls = getattr(config_module, "_ConfigNotLoaded", None)
    if placeholder_cls is not None and isinstance(active_config, placeholder_cls):
        active_config = None

    if active_config is not None:
        return active_config

    engine_module = sys.modules.get("engine")
    if engine_module is not None and hasattr(engine_module, "_require_config"):
        return engine_module._require_config()  # type: ignore[attr-defined]

    raise RuntimeError(
        "Active evolver configuration has not been set. Call set_active_config() "
        "or main() before using module-level helpers."
    )


def _deduplicate_paths(candidates: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique_candidates: list[Path] = []
    for candidate in candidates:
        expanded = candidate.expanduser()
        try:
            key_path = expanded if expanded.is_absolute() else expanded.resolve(strict=False)
        except RuntimeError:
            key_path = expanded
        key = str(key_path)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(expanded)
    return unique_candidates


def _find_command_candidates(
    name: str,
    env_var: str,
    *,
    use_shutil: bool = True,
    project_dirs: Sequence[Path | str] | None = None,
    project_parent_dirs: Sequence[Path | str] | None = None,
    additional_dirs: Sequence[Path | str] | None = None,
    base_dirs: Sequence[Path | str] | None = None,
    include_plain_name: bool = True,
    module_dir: Path | None = None,
    project_root: Path | None = None,
) -> list[Path]:
    if module_dir is None:
        module_dir = Path(__file__).resolve().parent
    if project_root is None:
        project_root = module_dir.parent
    env_override = os.environ.get(env_var)
    candidates: list[Path] = []
    if env_override:
        candidates.append(Path(env_override))

    if use_shutil:
        detected = shutil.which(name)
        if detected:
            candidates.append(Path(detected))

    if project_dirs:
        for rel_dir in project_dirs:
            candidate_dir = module_dir / Path(rel_dir)
            candidates.append(candidate_dir / name)

    if project_parent_dirs:
        for rel_dir in project_parent_dirs:
            parent_dir = project_root / Path(rel_dir)
            candidates.append(parent_dir / name)

    if base_dirs:
        for base_dir in base_dirs:
            candidates.append(Path(base_dir) / name)

    if additional_dirs:
        for additional in additional_dirs:
            candidates.append(Path(additional) / name)

    if include_plain_name:
        candidates.append(Path(name))

    return _deduplicate_paths(candidates)


def _candidate_worker_paths() -> list[Path]:
    module_dir = Path(__file__).resolve().parent
    project_root = module_dir.parent
    if not (project_root / "CMakeLists.txt").exists():
        project_root = module_dir

    candidates: list[Path] = []

    env_override = os.environ.get("CPP_WORKER_LIB")
    if env_override:
        candidates.append(Path(env_override))

    system = platform.system()
    if system == "Windows":
        extension = ".dll"
    elif system == "Darwin":
        extension = ".dylib"
    else:
        extension = ".so"

    library_names = [
        f"redcode_worker{extension}",
        f"libredcode_worker{extension}",
    ]

    build_dir = project_root / "build"
    multi_config_dirs = [
        build_dir / "Debug",
        build_dir / "Release",
    ]
    system_dirs = [Path("/usr/local/lib")]

    for lib_name in library_names:
        candidates.append(project_root / lib_name)
        candidates.append(build_dir / lib_name)
        for multi_config_dir in multi_config_dirs:
            candidates.append(multi_config_dir / lib_name)
        for system_dir in system_dirs:
            candidates.append(system_dir / lib_name)

    return _deduplicate_paths(candidates)


def _format_path(path: Path | str) -> str:
    path_obj = Path(path)
    if path_obj.is_absolute():
        return str(path_obj)
    try:
        return str(path_obj.resolve())
    except FileNotFoundError:
        return str(path_obj)


def _load_cpp_worker_library() -> None:
    global CPP_WORKER_LIB

    try:
        candidates = _candidate_worker_paths()
        loaded_path: Path | None = None
        for path in candidates:
            try:
                CPP_WORKER_LIB = ctypes.CDLL(str(path))
                loaded_path = path
                break
            except OSError:
                continue

        if CPP_WORKER_LIB is not None and loaded_path is not None:
            CPP_WORKER_LIB.run_battle.argtypes = [
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
            ]
            CPP_WORKER_LIB.run_battle.restype = ctypes.c_char_p
            console_log(
                "Successfully loaded C++ Redcode worker from "
                f"{_format_path(loaded_path)}.",
                minimum_level=VerbosityLevel.TERSE,
            )
        else:
            CPP_WORKER_LIB = None
            tried_paths = ", ".join(_format_path(path) for path in candidates)
            console_log(
                f"Could not load C++ Redcode worker. Tried: {tried_paths}",
                minimum_level=VerbosityLevel.TERSE,
            )
            console_log(
                "Internal battle engine will not be available.",
                minimum_level=VerbosityLevel.TERSE,
            )
    except (OSError, ImportError) as exc:  # pragma: no cover - defensive logging
        CPP_WORKER_LIB = None
        console_log(
            f"Could not load C++ Redcode worker: {exc}",
            minimum_level=VerbosityLevel.TERSE,
        )
        console_log(
            "Internal battle engine will not be available.",
            minimum_level=VerbosityLevel.TERSE,
        )
    finally:
        _sync_export("CPP_WORKER_LIB", CPP_WORKER_LIB)


def _find_mars_executable(base_name: str, env_var: str) -> list[str]:
    exe_name = f"{base_name}.exe" if os.name == "nt" else base_name
    candidates = _find_command_candidates(
        exe_name,
        env_var,
        project_dirs=[Path("pMars"), Path("pMars/src"), Path(".")],
        base_dirs=[Path("pMars"), Path("pMars/src"), Path(".")],
    )
    return [str(candidate) for candidate in candidates]


def _candidate_pmars_paths() -> list[str]:
    return _find_mars_executable("pmars", "PMARS_CMD")


def _candidate_nmars_paths() -> list[str]:
    return _find_mars_executable("nmars", "NMARS_CMD")


def _resolve_external_command(engine_name: str, candidates: Sequence[str]) -> str:
    tried: list[str] = []
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        tried.append(candidate)

    tried_paths = ", ".join(_format_path(path) for path in tried) or "<no candidates>"
    raise RuntimeError(f"Could not locate {engine_name} executable. Tried: {tried_paths}")


def _run_external_command(
    executable: str,
    warrior_files: Sequence[str],
    flag_args: dict[str, Optional[object]] | None = None,
    *,
    prefix_args: Sequence[str] | None = None,
    warriors_first: bool = False,
) -> Optional[str]:
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
    except FileNotFoundError as exc:
        console_log(
            f"Unable to run {executable}: {exc}",
            minimum_level=VerbosityLevel.TERSE,
        )
        return None
    except subprocess.SubprocessError as exc:
        console_log(
            f"An error occurred: {exc}",
            minimum_level=VerbosityLevel.TERSE,
        )
        return None

    output = result.stdout or ""
    if not output and result.stderr:
        output = result.stderr
    return output


def _run_external_battle(
    engine_name: str,
    arena_index: int,
    era_index: int,
    battlerounds: Optional[int],
    seed: Optional[int],
    warrior1_path: str,
    warrior2_path: str,
) -> Optional[str]:
    config = get_active_config()
    resolve_command = _get_evolverstage_override(
        "_resolve_external_command", _resolve_external_command
    )
    run_command = _get_evolverstage_override(
        "_run_external_command", _run_external_command
    )
    rounds = battlerounds if battlerounds is not None else config.battlerounds_list[era_index]
    warrior_files = [warrior1_path, warrior2_path]

    if engine_name == "pmars":
        candidate_fn = _get_evolverstage_override(
            "_candidate_pmars_paths", _candidate_pmars_paths
        )
        engine_label = "pMARS"
        flag_args: dict[str, Optional[object]] = {
            "-r": rounds,
            "-p": config.processes_list[arena_index],
            "-s": config.coresize_list[arena_index],
            "-c": config.cycles_list[arena_index],
            "-l": config.warlen_list[arena_index],
            "-d": config.wardistance_list[arena_index],
        }
        if seed is not None:
            flag_args["-F"] = _normalize_pmars_seed(seed)
        flag_args["-b"] = None
    elif engine_name == "nmars":
        candidate_fn = _get_evolverstage_override(
            "_candidate_nmars_paths", _candidate_nmars_paths
        )
        engine_label = "nMars"
        flag_args = {
            "-r": rounds,
            "-p": config.processes_list[arena_index],
            "-c": config.cycles_list[arena_index],
            "-s": config.coresize_list[arena_index],
            "-l": config.warlen_list[arena_index],
            "-d": config.wardistance_list[arena_index],
        }
    else:
        raise ValueError(f"Unknown battle engine: {engine_name}")

    executable = resolve_command(engine_label, candidate_fn())
    return run_command(executable, warrior_files, flag_args)


_INTERNAL_ENGINE_MAX_SEED = 2_147_483_646
_PMARS_MAX_SEED = 1_073_741_824


def _normalize_pmars_seed(seed: int) -> int:
    modulus = _PMARS_MAX_SEED + 1
    normalized = seed % modulus
    if normalized < 0:
        normalized += modulus
    return normalized


def _normalize_internal_seed(seed: int) -> int:
    modulus = _INTERNAL_ENGINE_MAX_SEED
    normalized = seed % modulus
    if normalized <= 0:
        normalized += modulus
    return normalized


def _generate_internal_battle_seed() -> int:
    return _rng_int(1, _INTERNAL_ENGINE_MAX_SEED)


def _stable_internal_battle_seed(arena: int, cont1: int, cont2: int, era: int) -> int:
    data = f"{arena}:{cont1}:{cont2}:{era}".encode("utf-8")
    digest = hashlib.blake2s(data, digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return _normalize_internal_seed(value)


def _get_internal_worker_library():
    module = sys.modules.get("evolverstage")
    module_lib = None
    override_applied = False
    if module is not None and "CPP_WORKER_LIB" in getattr(module, "__dict__", {}):
        module_lib = module.__dict__["CPP_WORKER_LIB"]
        if module_lib is not CPP_WORKER_LIB:
            override_applied = True

    worker_lib = module_lib if override_applied else CPP_WORKER_LIB
    if worker_lib is None and not override_applied:
        _load_cpp_worker_library()
        worker_lib = _get_evolverstage_override("CPP_WORKER_LIB", CPP_WORKER_LIB)
    if worker_lib is None:
        raise RuntimeError(
            "Internal battle engine is required by the configuration but the "
            "C++ worker library is not loaded."
        )
    return worker_lib


def run_internal_battle(
    arena,
    cont1,
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
):
    config = get_active_config()
    worker_lib = _get_internal_worker_library()

    def _load_warrior_code_from_disk(warrior_id: int) -> str:
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
        with open(warrior_path, "r") as handle:
            return handle.read()

    try:
        if config.use_in_memory_arenas:
            try:
                storage = get_arena_storage()
            except RuntimeError:
                storage = None
            if storage is not None:
                w1_lines = storage.get_warrior_lines(arena, cont1)
                w2_lines = storage.get_warrior_lines(arena, cont2)
                if w1_lines and w2_lines:
                    w1_code = "".join(w1_lines)
                    w2_code = "".join(w2_lines)
                else:
                    w1_code = _load_warrior_code_from_disk(cont1)
                    w2_code = _load_warrior_code_from_disk(cont2)
            else:
                w1_code = _load_warrior_code_from_disk(cont1)
                w2_code = _load_warrior_code_from_disk(cont2)
        else:
            w1_code = _load_warrior_code_from_disk(cont1)
            w2_code = _load_warrior_code_from_disk(cont2)

        use_1988_rules = 1 if get_arena_spec(arena) == SPEC_1988 else 0
        result_ptr = worker_lib.run_battle(
            w1_code.encode("utf-8"),
            cont1,
            w2_code.encode("utf-8"),
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
            use_1988_rules,
        )
        if isinstance(result_ptr, bytes):
            return result_ptr.decode("utf-8")
        return result_ptr
    except Exception as exc:
        raise RuntimeError(f"An error occurred while running the internal battle: {exc}")


def _parse_battle_output(
    raw_output: str, engine_name: str, verbose: bool, expected_warriors: Sequence[int]
) -> tuple[list[int], list[int]]:
    if raw_output is None:
        raise RuntimeError("Battle engine returned no output")
    scores: list[int] = []
    warriors: list[int] = []
    score_lines_found = 0
    numline = ""
    is_pmars = engine_name == "pmars"
    pmars_slots: list[int] = []
    pmars_scores: dict[int, int] = {}

    for numline in raw_output.split("\n"):
        if numline.startswith("ERROR:"):
            raise RuntimeError(f"Battle engine reported an error: {numline}")
        match = _PMARS_SCORE_RE.search(numline)
        if match or (not is_pmars and "scores" in numline.lower()):
            score_lines_found += 1
            line = numline
            if not is_pmars:
                splittedline = line.split()
                if len(splittedline) < 5:
                    raise RuntimeError(f"Unexpected score line format: {line.strip()}")
                try:
                    scores.append(int(splittedline[4]))
                    warriors.append(int(splittedline[0]))
                except ValueError as exc:
                    raise RuntimeError(
                        f"Unexpected score line format: {line.strip()}"
                    ) from exc
                continue
            if is_pmars and "(" not in line:
                slot_str = match.group("slot")
                slot = int(slot_str) if slot_str is not None else len(pmars_slots) + 1
                score_value = int(match.group("score"))
                if slot not in pmars_scores:
                    pmars_slots.append(slot)
                pmars_scores[slot] = score_value
                continue
            scoreline = line.split("scores")
            if len(scoreline) < 2:
                raise RuntimeError(f"Unexpected score line format: {line.strip()}")
            scoresegment = scoreline[1].split("(")
            if len(scoresegment) < 2:
                raise RuntimeError(f"Unexpected score line format: {line.strip()}")
            scoreblock = scoresegment[1].split(")")[0]
            scoreblocks = scoreblock.split(",")
            if len(scoreblocks) < 2:
                raise RuntimeError(f"Unexpected score line format: {line.strip()}")
            for scoreset in scoreblocks:
                slot_and_score = scoreset.split(":")
                if len(slot_and_score) != 2:
                    raise RuntimeError(f"Unexpected score line format: {line.strip()}")
                try:
                    candidate = int(slot_and_score[0])
                    score_value = int(slot_and_score[1])
                except ValueError as exc:
                    raise RuntimeError(
                        f"Unexpected score line format: {line.strip()}"
                    ) from exc
                if candidate not in pmars_scores:
                    pmars_slots.append(candidate)
                pmars_scores[candidate] = score_value
    if is_pmars:
        if not pmars_slots:
            raise RuntimeError(
                "pMARS output did not include any lines containing 'scores'."
            )
        for slot in pmars_slots:
            warrior_index = slot - 1
            if warrior_index < 0 or warrior_index >= len(expected_warriors):
                raise RuntimeError(
                    "pMARS returned an unexpected warrior slot "
                    f"identifier: {slot}"
                )
            warriors.append(int(expected_warriors[warrior_index]))
            scores.append(pmars_scores[slot])
    elif score_lines_found == 0:
        raise RuntimeError("nMars output did not include any lines containing 'scores'.")
    if len(scores) < 2:
        raise RuntimeError("Battle engine output did not include scores for both warriors")
    expected_set = {int(warrior) for warrior in expected_warriors}
    returned_warriors = set(warriors)
    if returned_warriors != expected_set:
        raise RuntimeError(
            "Battle engine returned mismatched warrior IDs: "
            f"expected {sorted(expected_set)}, got {sorted(returned_warriors)}"
        )
    if verbose:
        console_log(str(numline), minimum_level=VerbosityLevel.VERBOSE)
    return warriors, scores


def _process_battle_output(
    raw_output: Union[str, bytes, None],
    engine_name: str,
    verbose: bool,
    expected_warriors: Sequence[int],
) -> tuple[list[int], list[int]]:
    if raw_output is None:
        raise RuntimeError("Battle engine returned no output")
    if isinstance(raw_output, bytes):
        raw_output = raw_output.decode("utf-8")
    raw_output_stripped = raw_output.strip()
    if raw_output_stripped.startswith("ERROR:"):
        raise RuntimeError(f"Battle engine reported an error: {raw_output_stripped}")
    return _parse_battle_output(raw_output, engine_name, verbose, expected_warriors)


def execute_battle(
    arena: int,
    cont1: int,
    cont2: int,
    era: int,
    verbose: bool = True,
    battlerounds_override: Optional[int] = None,
    seed: Optional[int] = None,
):
    config = get_active_config()
    engine_name = config.battle_engine
    storage = get_arena_storage()
    if not (config.use_in_memory_arenas and engine_name == "internal"):
        storage.ensure_warriors_on_disk(arena, [cont1, cont2])
    battlerounds = (
        battlerounds_override
        if battlerounds_override is not None
        else config.battlerounds_list[era]
    )
    if engine_name == "internal":
        internal_seed = -1 if seed is None else _normalize_internal_seed(seed)
        battle_impl = _get_evolverstage_override(
            "run_internal_battle", run_internal_battle
        )
        raw_output = battle_impl(
            arena,
            cont1,
            cont2,
            config.coresize_list[arena],
            config.cycles_list[arena],
            config.processes_list[arena],
            config.readlimit_list[arena],
            config.writelimit_list[arena],
            config.wardistance_list[arena],
            config.warlen_list[arena],
            battlerounds,
            internal_seed,
        )
    else:
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        raw_output = _run_external_battle(
            engine_name,
            arena,
            era,
            battlerounds,
            seed,
            os.path.join(arena_dir, f"{cont1}.red"),
            os.path.join(arena_dir, f"{cont2}.red"),
        )

    return _process_battle_output(
        raw_output,
        engine_name,
        verbose,
        [cont1, cont2],
    )


def execute_battle_with_sources(
    arena: int,
    cont1: int,
    cont1_code: str,
    cont2: int,
    cont2_code: str,
    era: int,
    verbose: bool = False,
    battlerounds_override: Optional[int] = None,
    seed: Optional[int] = None,
) -> tuple[list[int], list[int]]:
    config = _require_battle_config()
    engine_name = config.battle_engine
    battlerounds = (
        battlerounds_override
        if battlerounds_override is not None
        else config.battlerounds_list[era]
    )

    normalized_w1 = cont1_code if cont1_code.endswith("\n") else cont1_code + "\n"
    normalized_w2 = cont2_code if cont2_code.endswith("\n") else cont2_code + "\n"

    if engine_name == "internal":
        worker_lib = _get_internal_worker_library()
        internal_seed = -1 if seed is None else _normalize_internal_seed(seed)
        use_1988_rules = 1 if get_arena_spec(arena) == SPEC_1988 else 0
        result_ptr = worker_lib.run_battle(
            normalized_w1.encode("utf-8"),
            cont1,
            normalized_w2.encode("utf-8"),
            cont2,
            config.coresize_list[arena],
            config.cycles_list[arena],
            config.processes_list[arena],
            config.readlimit_list[arena],
            config.writelimit_list[arena],
            config.wardistance_list[arena],
            config.warlen_list[arena],
            battlerounds,
            internal_seed,
            use_1988_rules,
        )
        raw_output = result_ptr
    else:
        with tempfile.TemporaryDirectory() as tmp_dir:
            warrior1_path = os.path.join(tmp_dir, f"{cont1}.red")
            warrior2_path = os.path.join(tmp_dir, f"{cont2}.red")
            with open(warrior1_path, "w") as handle:
                handle.write(normalized_w1)
            with open(warrior2_path, "w") as handle:
                handle.write(normalized_w2)
            raw_output = _run_external_battle(
                engine_name,
                arena,
                era,
                battlerounds,
                seed,
                warrior1_path,
                warrior2_path,
            )

    return _process_battle_output(raw_output, engine_name, verbose, [cont1, cont2])


__all__ = [
    "CPP_WORKER_LIB",
    "CPP_WORKER_MIN_DISTANCE",
    "CPP_WORKER_MIN_CORE_SIZE",
    "CPP_WORKER_MAX_CORE_SIZE",
    "CPP_WORKER_MAX_CYCLES",
    "CPP_WORKER_MAX_PROCESSES",
    "CPP_WORKER_MAX_WARRIOR_LENGTH",
    "CPP_WORKER_MAX_ROUNDS",
    "_normalize_internal_seed",
    "_generate_internal_battle_seed",
    "_stable_internal_battle_seed",
    "_candidate_pmars_paths",
    "_candidate_nmars_paths",
    "_resolve_external_command",
    "_run_external_command",
    "_run_external_battle",
    "run_internal_battle",
    "execute_battle",
    "execute_battle_with_sources",
    "configure_battle_rng",
    "set_sync_export",
]
