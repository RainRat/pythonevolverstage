"""Core battle and evolutionary logic for the Core War evolver stage."""

from __future__ import annotations

import ctypes
import hashlib
import os
import platform
import random
import re
import shutil
import subprocess
import tempfile
import time
import sys
import uuid
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Callable,
    Iterable,
    Literal,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    cast,
)

from ui import VerbosityLevel, console_log

if TYPE_CHECKING:  # pragma: no cover - imported only for type checking
    from evolverstage import DataLogger, EvolverConfig


T = TypeVar("T")


_active_config: Optional["EvolverConfig"] = None


def set_engine_config(config: "EvolverConfig") -> None:
    """Register the active configuration for helpers that require it."""

    global _active_config
    _active_config = config
    rebuild_instruction_tables(config)


def _require_config() -> "EvolverConfig":
    if _active_config is None:
        raise RuntimeError(
            "Engine configuration has not been set. Call set_active_config() first."
        )
    return _active_config


_rng_int: Callable[[int, int], int] = random.randint
_rng_choice: Callable[[Sequence[T]], T] = random.choice  # type: ignore[assignment]


MAX_WARRIOR_FILENAME_ID = 65534


def configure_rng(
    random_int_func: Callable[[int, int], int],
    random_choice_func: Callable[[Sequence[T]], T],
) -> None:
    """Wire in evolverstage's deterministic RNG helpers."""

    global _rng_int, _rng_choice
    _rng_int = random_int_func
    _rng_choice = random_choice_func


def _sync_export(name: str, value) -> None:
    module = sys.modules.get("evolverstage")
    if module is not None:
        setattr(module, name, value)


def _get_evolverstage_override(name: str, default):
    module = sys.modules.get("evolverstage")
    if module is not None and hasattr(module, name):
        return getattr(module, name)
    return default


DEFAULT_MODE = "$"
DEFAULT_MODIFIER = "F"
BASE_ADDRESSING_MODES = {"$", "#", "@", "<", ">", "*", "{", "}"}
ADDRESSING_MODES: set[str] = set(BASE_ADDRESSING_MODES)
_sync_export("ADDRESSING_MODES", ADDRESSING_MODES)

CANONICAL_SUPPORTED_OPCODES = {
    "DAT",
    "MOV",
    "ADD",
    "SUB",
    "MUL",
    "DIV",
    "MOD",
    "JMP",
    "JMZ",
    "JMN",
    "DJN",
    "CMP",
    "SEQ",
    "SNE",
    "SLT",
    "SPL",
    "NOP",
}
OPCODE_ALIASES = {
    "SEQ": "CMP",
}
SUPPORTED_OPCODES = CANONICAL_SUPPORTED_OPCODES | set(OPCODE_ALIASES)
UNSUPPORTED_OPCODES = {"LDP", "STP"}

SPEC_1994 = "1994"
SPEC_1988 = "1988"

SPEC_ALLOWED_OPCODES = {
    SPEC_1994: CANONICAL_SUPPORTED_OPCODES,
    SPEC_1988: {
        "DAT",
        "MOV",
        "ADD",
        "SUB",
        "JMP",
        "JMZ",
        "JMN",
        "DJN",
        "CMP",
        "SLT",
        "SPL",
    },
}

SPEC_ALLOWED_MODIFIERS = {
    SPEC_1994: {"A", "B", "AB", "BA", "F", "X", "I"},
    SPEC_1988: {"A", "B", "AB", "BA", "F"},
}

SPEC_ALLOWED_ADDRESSING_MODES = {
    SPEC_1994: {
        "#",
        "$",
        "@",
        "<",
        ">",
        "*",
        "{",
        "}",
    },
    SPEC_1988: {"#", "$", "@", "<", ">"},
}

DEFAULT_1988_GENERATION_POOL = [
    "MOV",
    "ADD",
    "SUB",
    "JMP",
    "JMZ",
    "JMN",
    "DJN",
    "CMP",
    "SLT",
    "SPL",
    "DAT",
]

DEFAULT_1988_MODIFIERS = ["A", "B", "AB", "BA", "F"]
DEFAULT_1988_MODES = ["#", "$", "@", "<", ">"]


def canonicalize_opcode(opcode: str) -> str:
    return OPCODE_ALIASES.get(opcode, opcode)


GENERATION_OPCODE_POOL: list[str] = []
_sync_export("GENERATION_OPCODE_POOL", GENERATION_OPCODE_POOL)
GENERATION_OPCODE_POOL_1988: list[str] = []
_sync_export("GENERATION_OPCODE_POOL_1988", GENERATION_OPCODE_POOL_1988)


def rebuild_instruction_tables(active_config: "EvolverConfig") -> None:
    global ADDRESSING_MODES, GENERATION_OPCODE_POOL, GENERATION_OPCODE_POOL_1988

    ADDRESSING_MODES = set(BASE_ADDRESSING_MODES)
    if active_config.instr_modes:
        ADDRESSING_MODES.update(
            mode.strip() for mode in active_config.instr_modes if mode.strip()
        )
    _sync_export("ADDRESSING_MODES", ADDRESSING_MODES)

    invalid_generation_opcodes = set()
    GENERATION_OPCODE_POOL = []
    invalid_reasons: list[str] = []
    allowed_1994 = SPEC_ALLOWED_OPCODES[SPEC_1994]
    instr_set = active_config.instr_set or []
    for instr in instr_set:
        normalized = instr.strip().upper()
        if not normalized:
            continue
        canonical_opcode = OPCODE_ALIASES.get(normalized, normalized)
        if (
            canonical_opcode in UNSUPPORTED_OPCODES
            or canonical_opcode not in allowed_1994
        ):
            invalid_generation_opcodes.add(normalized)
            continue
        GENERATION_OPCODE_POOL.append(canonical_opcode)

    if invalid_generation_opcodes:
        invalid_reasons.append(
            "contains unsupported opcode(s): "
            + ", ".join(sorted(invalid_generation_opcodes))
        )

    if not GENERATION_OPCODE_POOL:
        invalid_reasons.append("must include at least one supported opcode other than DAT")
    elif all(opcode == "DAT" for opcode in GENERATION_OPCODE_POOL):
        invalid_reasons.append("must include at least one opcode other than DAT")

    if invalid_reasons:
        raise ValueError(
            "Invalid INSTR_SET configuration: " + "; ".join(invalid_reasons) + "."
        )

    _sync_export("GENERATION_OPCODE_POOL", GENERATION_OPCODE_POOL)

    allowed_1988 = SPEC_ALLOWED_OPCODES[SPEC_1988]
    filtered_1988: list[str] = []
    for instr in instr_set:
        normalized = instr.strip().upper()
        if not normalized:
            continue
        canonical_opcode = OPCODE_ALIASES.get(normalized, normalized)
        if canonical_opcode in allowed_1988 and canonical_opcode not in UNSUPPORTED_OPCODES:
            filtered_1988.append(canonical_opcode)

    if not filtered_1988:
        GENERATION_OPCODE_POOL_1988 = list(DEFAULT_1988_GENERATION_POOL)
    else:
        GENERATION_OPCODE_POOL_1988 = filtered_1988
        if not any(opcode != "DAT" for opcode in GENERATION_OPCODE_POOL_1988):
            non_dat_defaults = [
                opcode for opcode in DEFAULT_1988_GENERATION_POOL if opcode != "DAT"
            ]
            GENERATION_OPCODE_POOL_1988.extend(non_dat_defaults)

    _sync_export("GENERATION_OPCODE_POOL_1988", GENERATION_OPCODE_POOL_1988)


def get_arena_spec(arena: int) -> str:
    config = _require_config()
    if (
        getattr(config, "arena_spec_list", None)
        and arena < len(config.arena_spec_list)
        and config.arena_spec_list[arena]
    ):
        return config.arena_spec_list[arena]
    return SPEC_1994


def _is_allowed_for_spec(value: str, spec: str, allowed_map: dict[str, set[str]]) -> bool:
    allowed = allowed_map.get(spec)
    if not allowed:
        return True
    return value in allowed


def _get_opcode_pool_for_arena(arena: int) -> list[str]:
    spec = get_arena_spec(arena)
    if spec == SPEC_1988:
        return _get_evolverstage_override(
            "GENERATION_OPCODE_POOL_1988", GENERATION_OPCODE_POOL_1988
        )
    return _get_evolverstage_override("GENERATION_OPCODE_POOL", GENERATION_OPCODE_POOL)


def weighted_random_number(size: int, length: int) -> int:
    if _rng_int(1, 4) == 1:
        return _rng_int(-size, size)
    return _rng_int(-length, length)


def coremod(num: int, modulus: int) -> int:
    if modulus == 0:
        raise ValueError("Modulus cannot be zero")
    return ((num % modulus) + modulus) % modulus


def corenorm(num: int, modulus: int) -> int:
    modded = coremod(num, modulus)
    if modded > modulus // 2:
        modded -= modulus
    return modded


@dataclass
class RedcodeInstruction:
    opcode: str
    modifier: str
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


_INT_LITERAL_RE = re.compile(r"^[+-]?\d+$")

_REDCODE_PREFIX_RE = re.compile(
    r"""
    ^\s*
    (?:(?P<label>[A-Za-z_.$][\w.$]*)(?::)?\s+)?
    (?P<opcode>[A-Za-z]+)
    (?P<modifier_part>(?:\s*\.\s*[A-Za-z]+)?)
    """,
    re.VERBOSE,
)

_REDCODE_INSTRUCTION_RE = re.compile(
    r"""
    ^\s*
    (?:(?P<label>[A-Za-z_.$][\w.$]*)(?::)?\s+)?
    (?P<opcode>[A-Za-z]+)
    \s*\.\s*
    (?P<modifier>[A-Za-z]+)
    \s*
    (?P<a_operand>[^,]+?)
    \s*,\s*
    (?P<b_operand>[^,]+?)
    \s*$
    """,
    re.VERBOSE,
)

_PMARS_SCORE_RE = re.compile(
    r"^\s*(?:(?P<slot>\d+)\s*:\s*)?.*?\bscores\s+(?P<score>-?\d+)\b",
    re.IGNORECASE,
)


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


def _parse_operand(operand: str, operand_name: str) -> Tuple[str, int]:
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


def parse_redcode_instruction(line: str) -> Optional[RedcodeInstruction]:
    if not line:
        return None
    code_part = line.split(";", 1)[0].strip()
    if not code_part:
        return None

    prefix_match = _REDCODE_PREFIX_RE.match(code_part)
    if not prefix_match:
        raise ValueError(f"Invalid instruction format: '{code_part}'")
    if not prefix_match.group("modifier_part"):
        raise ValueError("Instruction is missing a modifier")

    match = _REDCODE_INSTRUCTION_RE.match(code_part)
    if not match:
        raise ValueError(f"Invalid instruction format: '{code_part}'")

    label = match.group("label")
    opcode = match.group("opcode").upper()
    modifier = match.group("modifier").upper()
    canonical_opcode = canonicalize_opcode(opcode)
    if canonical_opcode in UNSUPPORTED_OPCODES:
        return default_instruction()
    if canonical_opcode not in CANONICAL_SUPPORTED_OPCODES:
        raise ValueError(f"Unknown opcode '{opcode}'")

    a_operand = match.group("a_operand")
    b_operand = match.group("b_operand")
    a_mode, a_field = _parse_operand(a_operand, "A")
    b_mode, b_field = _parse_operand(b_operand, "B")

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
        opcode="DAT",
        modifier=DEFAULT_MODIFIER,
        a_mode=DEFAULT_MODE,
        a_field=0,
        b_mode=DEFAULT_MODE,
        b_field=0,
    )


def sanitize_instruction(instr: RedcodeInstruction, arena: int) -> RedcodeInstruction:
    config = _require_config()
    sanitized = instr.copy()
    original_opcode = (sanitized.opcode or "").upper()
    canonical_opcode = canonicalize_opcode(original_opcode)
    sanitized.opcode = canonical_opcode
    if canonical_opcode in UNSUPPORTED_OPCODES:
        raise ValueError(f"Opcode '{original_opcode}' is not supported")
    if canonical_opcode not in CANONICAL_SUPPORTED_OPCODES:
        raise ValueError(f"Unknown opcode '{original_opcode}'")
    spec = get_arena_spec(arena)
    if not _is_allowed_for_spec(
        canonical_opcode, spec, SPEC_ALLOWED_OPCODES
    ):
        return default_instruction()
    if not sanitized.modifier:
        raise ValueError("Missing modifier for instruction")
    sanitized.modifier = sanitized.modifier.upper()
    if not _is_allowed_for_spec(
        sanitized.modifier, spec, SPEC_ALLOWED_MODIFIERS
    ):
        return default_instruction()
    if sanitized.a_mode not in ADDRESSING_MODES:
        raise ValueError(
            f"Invalid addressing mode '{sanitized.a_mode}' for A-field operand"
        )
    if sanitized.b_mode not in ADDRESSING_MODES:
        raise ValueError(
            f"Invalid addressing mode '{sanitized.b_mode}' for B-field operand"
        )
    if not _is_allowed_for_spec(
        sanitized.a_mode, spec, SPEC_ALLOWED_ADDRESSING_MODES
    ):
        return default_instruction()
    if not _is_allowed_for_spec(
        sanitized.b_mode, spec, SPEC_ALLOWED_ADDRESSING_MODES
    ):
        return default_instruction()
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
        f"{instr.a_mode}{instr.a_field},"
        f"{instr.b_mode}{instr.b_field}\n"
    )


def instruction_to_line(instr: RedcodeInstruction, arena: int) -> str:
    return format_redcode_instruction(sanitize_instruction(instr, arena))


def parse_instruction_or_default(line: str) -> RedcodeInstruction:
    parsed = parse_redcode_instruction(line)
    return parsed if parsed else default_instruction()


def choose_random_opcode(arena: int) -> str:
    opcode_pool = _get_opcode_pool_for_arena(arena)
    if opcode_pool:
        return _rng_choice(opcode_pool)
    return "DAT"


def choose_random_modifier(arena: int) -> str:
    config = _require_config()
    spec = get_arena_spec(arena)
    modifier_pool = [
        item.strip().upper()
        for item in (config.instr_modif or [])
        if item.strip()
    ]
    if spec == SPEC_1988:
        modifier_pool = [
            modifier
            for modifier in modifier_pool
            if _is_allowed_for_spec(
                modifier, spec, SPEC_ALLOWED_MODIFIERS
            )
        ]
        if not modifier_pool:
            modifier_pool = list(DEFAULT_1988_MODIFIERS)
    if modifier_pool:
        return _rng_choice(modifier_pool)
    return DEFAULT_MODIFIER


def choose_random_mode(arena: int) -> str:
    config = _require_config()
    spec = get_arena_spec(arena)
    mode_pool = [mode.strip() for mode in (config.instr_modes or []) if mode.strip()]
    if spec == SPEC_1988:
        allowed_modes = SPEC_ALLOWED_ADDRESSING_MODES[spec]
        mode_pool = [mode for mode in mode_pool if mode in allowed_modes]
        if not mode_pool:
            mode_pool = list(DEFAULT_1988_MODES)
    if mode_pool:
        return _rng_choice(mode_pool)
    return DEFAULT_MODE


def generate_random_instruction(arena: int) -> RedcodeInstruction:
    config = _require_config()
    num1 = weighted_random_number(config.coresize_list[arena], config.warlen_list[arena])
    num2 = weighted_random_number(config.coresize_list[arena], config.warlen_list[arena])
    opcode = choose_random_opcode(arena)
    canonical_opcode = canonicalize_opcode(opcode)
    return RedcodeInstruction(
        opcode=canonical_opcode,
        modifier=choose_random_modifier(arena),
        a_mode=choose_random_mode(arena),
        a_field=num1,
        b_mode=choose_random_mode(arena),
        b_field=num2,
    )


def _can_generate_non_dat_opcode(arena: int) -> bool:
    opcode_pool = _get_opcode_pool_for_arena(arena)
    return any(opcode != "DAT" for opcode in opcode_pool)


def generate_warrior_lines_until_non_dat(
    generator: Callable[[], list[str]],
    context: str,
    arena: int,
) -> list[str]:
    if not _can_generate_non_dat_opcode(arena):
        raise RuntimeError(
            f"{context}: configuration cannot generate non-DAT opcodes. "
            "Check the INSTR_SET configuration to include at least one opcode other than DAT."
        )

    lines: list[str] = []
    while True:
        lines = generator()
        if not lines:
            continue
        if any(
            parse_instruction_or_default(line).opcode != "DAT" for line in lines if line
        ):
            return lines


class Marble(Enum):
    DO_NOTHING = 0
    MAJOR_MUTATION = 1
    NAB_INSTRUCTION = 2
    MINOR_MUTATION = 3
    MICRO_MUTATION = 4
    INSTRUCTION_LIBRARY = 5
    MAGIC_NUMBER_MUTATION = 6


CPP_WORKER_LIB = None
_sync_export("CPP_WORKER_LIB", CPP_WORKER_LIB)

CPP_WORKER_MIN_DISTANCE = 0
CPP_WORKER_MIN_CORE_SIZE = 2
CPP_WORKER_MAX_CORE_SIZE = 262_144
CPP_WORKER_MAX_CYCLES = 5_000_000
CPP_WORKER_MAX_PROCESSES = 131_072
CPP_WORKER_MAX_WARRIOR_LENGTH = CPP_WORKER_MAX_CORE_SIZE
CPP_WORKER_MAX_ROUNDS = 100_000


def _worker_library_extension() -> str:
    system = platform.system()
    if system == "Windows":
        return ".dll"
    if system == "Darwin":
        return ".dylib"
    return ".so"


def _deduplicate_paths(candidates: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique_candidates: list[Path] = []
    for candidate in candidates:
        expanded = candidate.expanduser()
        try:
            key_path = (
                expanded if expanded.is_absolute() else expanded.resolve(strict=False)
            )
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
    base_dirs: Sequence[Path | str] | None = None,
    additional_dirs: Sequence[Path | str] | None = None,
    include_plain_name: bool = True,
) -> list[Path]:
    module_dir = Path(__file__).resolve().parent
    project_root = module_dir.parent
    candidates: list[Path] = []

    env_override = os.environ.get(env_var)
    if env_override:
        env_path = Path(env_override).expanduser()
        candidates.append(env_path)
        if env_path.is_dir():
            candidates.append((env_path / name).expanduser())

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


def _format_candidate(path: Path | str) -> str:
    path_obj = Path(path)
    if path_obj.is_absolute():
        return str(path_obj)
    try:
        return str(path_obj.resolve())
    except FileNotFoundError:
        return str(path_obj)


def _candidate_worker_paths() -> list[Path]:
    module_dir = Path(__file__).resolve().parent
    project_root = module_dir.parent
    candidates: list[Path] = []

    env_override = os.environ.get("CPP_WORKER_LIB")
    if env_override:
        candidates.append(Path(env_override))

    extension = _worker_library_extension()
    library_names = [
        f"libredcode_worker{extension}",
        f"redcode_worker{extension}",
    ]

    for lib_name in library_names:
        project_candidates = [
            module_dir / lib_name,
            project_root / lib_name,
            project_root / "build" / lib_name,
            project_root / "build" / "Debug" / lib_name,
            project_root / "build" / "Release" / lib_name,
        ]
        candidates.extend(project_candidates)

    return _deduplicate_paths(candidates)


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
                f"{_format_candidate(loaded_path)}.",
                minimum_level=VerbosityLevel.TERSE,
            )
        else:
            CPP_WORKER_LIB = None
            tried_paths = ", ".join(_format_candidate(path) for path in candidates)
            console_log(
                f"Could not load C++ Redcode worker. Tried: {tried_paths}",
                minimum_level=VerbosityLevel.TERSE,
            )
            console_log(
                "Internal battle engine will not be available.",
                minimum_level=VerbosityLevel.TERSE,
            )
    except Exception as exc:  # pragma: no cover - defensive logging
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

    tried_paths = ", ".join(_format_candidate(path) for path in tried) or "<no candidates>"
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
    config = _require_config()
    resolve_command = _get_evolverstage_override(
        "_resolve_external_command", _resolve_external_command
    )
    run_command = _get_evolverstage_override(
        "_run_external_command", _run_external_command
    )
    rounds = (
        battlerounds
        if battlerounds is not None
        else config.battlerounds_list[era_index]
    )
    warrior_files = [warrior1_path, warrior2_path]

    if engine_name == "pmars":
        candidate_fn = _get_evolverstage_override(
            "_candidate_pmars_paths", _candidate_pmars_paths
        )
        engine_label = "pMARS"
        flag_args: dict[str, Optional[object]] = {
            "-r": rounds,
            "-p": config.processes_list[arena_index],
            "-c": config.cycles_list[arena_index],
            "-s": config.coresize_list[arena_index],
            "-l": config.warlen_list[arena_index],
            "-d": config.wardistance_list[arena_index],
        }
        if seed is not None:
            flag_args["-F"] = _normalize_pmars_seed(seed)
    else:
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

    executable = resolve_command(engine_label, candidate_fn())
    return run_command(executable, warrior_files, flag_args)


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


_INTERNAL_ENGINE_MAX_SEED = 2_147_483_646
_PMARS_MAX_SEED = 1_073_741_824


def _generate_internal_battle_seed() -> int:
    return _rng_int(1, _INTERNAL_ENGINE_MAX_SEED)


def _stable_internal_battle_seed(arena: int, cont1: int, cont2: int, era: int) -> int:
    data = f"{arena}:{cont1}:{cont2}:{era}".encode("utf-8")
    digest = hashlib.blake2s(data, digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return _normalize_internal_seed(value)


def _get_internal_worker_library():
    module = sys.modules.get("evolverstage")
    override_applied = False
    module_lib = None
    if module is not None and "CPP_WORKER_LIB" in module.__dict__:
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
    config = _require_config()
    worker_lib = _get_internal_worker_library()

    try:
        if config.use_in_memory_arenas:
            storage = get_arena_storage()
            w1_lines = storage.get_warrior_lines(arena, cont1)
            w2_lines = storage.get_warrior_lines(arena, cont2)
            if not w1_lines or not w2_lines:
                raise RuntimeError(
                    "Warrior source missing from in-memory storage; "
                    "ensure warriors are initialized before battling."
                )
            w1_code = "".join(w1_lines)
            w2_code = "".join(w2_lines)
        else:
            arena_dir = os.path.join(config.base_path, f"arena{arena}")
            w1_path = os.path.join(arena_dir, f"{cont1}.red")
            w2_path = os.path.join(arena_dir, f"{cont2}.red")
            with open(w1_path, "r") as handle:
                w1_code = handle.read()
            with open(w2_path, "r") as handle:
                w2_code = handle.read()

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

        if not result_ptr:
            raise RuntimeError("C++ worker returned no result")

        result_str = result_ptr.decode("utf-8")
        if result_str.strip().startswith("ERROR:"):
            raise RuntimeError(
                f"C++ worker reported an error: {result_str.strip()}"
            )
        return result_str

    except Exception as exc:
        raise RuntimeError(
            f"An error occurred while running the internal battle: {exc}"
        )


def _parse_battle_output(
    raw_output: str,
    engine_name: str,
    verbose: bool,
    expected_warriors: Sequence[int],
) -> tuple[list[int], list[int]]:
    scores: list[int] = []
    warriors: list[int] = []
    numline = 0
    output_lines = raw_output.splitlines()
    if not output_lines:
        raise RuntimeError("Battle engine produced no output to parse")

    is_pmars = engine_name == "pmars"
    score_lines_found = 0
    pmars_slots: list[int] = []
    pmars_scores: dict[int, int] = {}
    for line in output_lines:
        numline += 1
        if "scores" in line:
            score_lines_found += 1
            if verbose:
                console_log(line.strip(), minimum_level=VerbosityLevel.VERBOSE)
            if is_pmars:
                match = _PMARS_SCORE_RE.search(line)
                if not match:
                    raise RuntimeError(
                        f"Unexpected pMARS score line format: {line.strip()}"
                    )
                slot_text = match.group("slot")
                if slot_text is not None:
                    slot = int(slot_text)
                else:
                    slot = next(
                        (
                            candidate
                            for candidate in range(1, len(expected_warriors) + 1)
                            if candidate not in pmars_scores
                        ),
                        None,
                    )
                    if slot is None:
                        raise RuntimeError(
                            "pMARS reported more score lines than expected warriors."
                        )
                score_value = int(match.group("score"))
                if slot not in pmars_scores:
                    pmars_slots.append(slot)
                pmars_scores[slot] = score_value
            else:
                splittedline = line.split()
                if len(splittedline) < 5:
                    raise RuntimeError(
                        f"Unexpected score line format: {line.strip()}"
                    )
                scores.append(int(splittedline[4]))
                warriors.append(int(splittedline[0]))
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
    config = _require_config()
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


def _ensure_trailing_newline(source: str) -> str:
    if not source.endswith("\n"):
        return source + "\n"
    return source


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
    config = _require_config()
    engine_name = config.battle_engine
    battlerounds = (
        battlerounds_override
        if battlerounds_override is not None
        else config.battlerounds_list[era]
    )

    normalized_w1 = _ensure_trailing_newline(cont1_code)
    normalized_w2 = _ensure_trailing_newline(cont2_code)

    if engine_name == "internal":
        worker_lib = _get_internal_worker_library()
        internal_seed = -1 if seed is None else _normalize_internal_seed(seed)
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


class _ArenaStorageNotLoaded:
    pass


class ArenaStorage:
    """Abstract storage backend for warrior source code."""

    def load_existing(self) -> None:
        raise NotImplementedError

    def get_warrior_lines(self, arena: int, warrior_id: int) -> list[str]:
        raise NotImplementedError

    def set_warrior_lines(
        self, arena: int, warrior_id: int, lines: Sequence[str]
    ) -> None:
        raise NotImplementedError

    def ensure_warriors_on_disk(
        self, arena: int, warrior_ids: Sequence[int]
    ) -> None:
        """Ensure the specified warriors are available on disk for battle engines."""

    def flush_arena(self, arena: int) -> bool:
        """Persist all warriors for a specific arena to disk."""

    def flush_all(self) -> bool:
        """Persist all arenas to disk."""


class DiskArenaStorage(ArenaStorage):
    """Storage backend that writes warrior changes directly to disk."""

    def load_existing(self) -> None:
        return None

    def get_warrior_lines(self, arena: int, warrior_id: int) -> list[str]:
        config = _require_config()
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
        try:
            with open(warrior_path, "r") as handle:
                return handle.readlines()
        except OSError:
            return []

    def set_warrior_lines(
        self, arena: int, warrior_id: int, lines: Sequence[str]
    ) -> None:
        config = _require_config()
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        os.makedirs(arena_dir, exist_ok=True)
        warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
        with open(warrior_path, "w") as handle:
            handle.writelines(lines)

    def ensure_warriors_on_disk(
        self, arena: int, warrior_ids: Sequence[int]
    ) -> None:
        return None

    def flush_arena(self, arena: int) -> bool:
        return False

    def flush_all(self) -> bool:
        return False


class InMemoryArenaStorage(ArenaStorage):
    """Store arena warriors in memory and persist on demand."""

    def __init__(self) -> None:
        self._arenas: dict[int, dict[int, list[str]]] = defaultdict(dict)
        self._dirty: set[tuple[int, int]] = set()

    def load_existing(self) -> None:
        config = _require_config()
        for arena in range(0, config.last_arena + 1):
            arena_dir = os.path.join(config.base_path, f"arena{arena}")
            if not os.path.isdir(arena_dir):
                continue
            for warrior_id in range(1, config.numwarriors + 1):
                warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
                try:
                    with open(warrior_path, "r") as handle:
                        self._arenas[arena][warrior_id] = handle.readlines()
                except OSError:
                    self._arenas[arena][warrior_id] = []
        self._dirty.clear()

    def get_warrior_lines(self, arena: int, warrior_id: int) -> list[str]:
        config = _require_config()
        if arena in self._arenas and warrior_id in self._arenas[arena]:
            return list(self._arenas[arena][warrior_id])
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
        try:
            with open(warrior_path, "r") as handle:
                lines = handle.readlines()
                self._arenas[arena][warrior_id] = list(lines)
                return list(lines)
        except OSError:
            return []

    def set_warrior_lines(
        self, arena: int, warrior_id: int, lines: Sequence[str]
    ) -> None:
        self._arenas[arena][warrior_id] = list(lines)
        self._dirty.add((arena, warrior_id))

    def ensure_warriors_on_disk(
        self, arena: int, warrior_ids: Sequence[int]
    ) -> None:
        for warrior_id in warrior_ids:
            if (arena, warrior_id) in self._dirty or not self._warrior_exists_on_disk(
                arena, warrior_id
            ):
                self._write_warrior(arena, warrior_id)

    def _warrior_exists_on_disk(self, arena: int, warrior_id: int) -> bool:
        config = _require_config()
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
        return os.path.isfile(warrior_path)

    def _write_warrior(self, arena: int, warrior_id: int) -> None:
        config = _require_config()
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        os.makedirs(arena_dir, exist_ok=True)
        warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
        lines = self._arenas.get(arena, {}).get(warrior_id, [])
        with open(warrior_path, "w") as handle:
            handle.writelines(lines)
        self._dirty.discard((arena, warrior_id))

    def flush_arena(self, arena: int) -> bool:
        wrote_any = False
        config = _require_config()
        for warrior_id in range(1, config.numwarriors + 1):
            if (arena, warrior_id) in self._dirty:
                self._write_warrior(arena, warrior_id)
                wrote_any = True
        return wrote_any

    def flush_all(self) -> bool:
        wrote_any = False
        config = _require_config()
        for arena in range(0, config.last_arena + 1):
            if self.flush_arena(arena):
                wrote_any = True
        return wrote_any


_ARENA_STORAGE: Union[ArenaStorage, _ArenaStorageNotLoaded] = _ArenaStorageNotLoaded()


def set_arena_storage(storage: ArenaStorage) -> None:
    global _ARENA_STORAGE
    _ARENA_STORAGE = storage


def get_arena_storage() -> ArenaStorage:
    storage = _ARENA_STORAGE
    if isinstance(storage, _ArenaStorageNotLoaded):
        raise RuntimeError(
            "Arena storage has not been initialized. Call set_arena_storage() before use."
        )
    return storage


def create_arena_storage(config: "EvolverConfig") -> ArenaStorage:
    if config.use_in_memory_arenas:
        return InMemoryArenaStorage()
    return DiskArenaStorage()


class ArchiveStorage:
    """Abstract storage backend for warrior archives."""

    def initialize(self) -> None:
        """Prepare the archive backend for use."""
        raise NotImplementedError

    def archive_warrior(
        self,
        warrior_id: int,
        lines: Sequence[str],
        config: "EvolverConfig",
        get_random_int: Callable[[int, int], int],
    ) -> Optional[str]:
        """Persist a warrior in the archive and return its filename if successful."""
        raise NotImplementedError

    def unarchive_warrior(
        self,
        config: "EvolverConfig",
        get_random_choice: Callable[[Sequence[T]], T],
    ) -> Optional[Tuple[str, list[str]]]:
        """Retrieve a random warrior from the archive, returning its filename and lines."""
        raise NotImplementedError

    def count(self) -> int:
        """Return the number of warriors currently stored in the archive."""
        raise NotImplementedError


class DiskArchiveStorage(ArchiveStorage):
    """Archive storage implementation that reads and writes warriors on disk."""

    def __init__(self, archive_path: str) -> None:
        self._archive_path = os.path.abspath(archive_path)

    @property
    def archive_path(self) -> str:
        return self._archive_path

    def initialize(self) -> None:
        os.makedirs(self._archive_path, exist_ok=True)

    def archive_warrior(
        self,
        warrior_id: int,
        lines: Sequence[str],
        config: "EvolverConfig",
        get_random_int: Callable[[int, int], int],
    ) -> Optional[str]:
        archive_dir = self._archive_path
        configured_archive_path = os.path.abspath(config.archive_path)
        if configured_archive_path == archive_dir:
            archive_dir = configured_archive_path

        archive_filename: Optional[str] = None
        os.makedirs(archive_dir, exist_ok=True)
        for _ in range(10):
            candidate = f"{get_random_int(1, MAX_WARRIOR_FILENAME_ID)}.red"
            candidate_path = os.path.join(archive_dir, candidate)
            try:
                fd = os.open(
                    candidate_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o644,
                )
            except FileExistsError:
                continue
            else:
                with os.fdopen(fd, "w") as handle:
                    handle.writelines(lines)
                archive_filename = candidate
                break

        if archive_filename is None:
            archive_filename = f"{uuid.uuid4().hex}.red"
            fallback_path = os.path.join(archive_dir, archive_filename)
            with open(fallback_path, "w") as handle:
                handle.writelines(lines)

        return archive_filename

    def unarchive_warrior(
        self,
        _config: "EvolverConfig",
        get_random_choice: Callable[[Sequence[T]], T],
    ) -> Optional[Tuple[str, list[str]]]:
        if not os.path.isdir(self._archive_path):
            return None
        archive_files = os.listdir(self._archive_path)
        if not archive_files:
            return None
        archive_choice = get_random_choice(archive_files)
        archive_path = os.path.join(self._archive_path, archive_choice)
        try:
            with open(archive_path, "r") as handle:
                sourcelines = handle.readlines()
        except OSError:
            return None
        return archive_choice, sourcelines

    def count(self) -> int:
        archive_dir = self._archive_path
        try:
            entries = os.listdir(archive_dir)
        except FileNotFoundError:
            return 0
        except OSError as exc:
            warnings.warn(
                f"Unable to inspect archive directory '{archive_dir}': {exc}",
                RuntimeWarning,
            )
            return 0

        total = 0
        for entry in entries:
            if not entry.lower().endswith(".red"):
                continue
            full_path = os.path.join(archive_dir, entry)
            if os.path.isfile(full_path):
                total += 1
        return total


_ARCHIVE_STORAGE: Union[ArchiveStorage, _ArenaStorageNotLoaded] = _ArenaStorageNotLoaded()


def set_archive_storage(storage: ArchiveStorage) -> None:
    global _ARCHIVE_STORAGE
    _ARCHIVE_STORAGE = storage


def get_archive_storage() -> ArchiveStorage:
    storage = _ARCHIVE_STORAGE
    if isinstance(storage, _ArenaStorageNotLoaded):
        raise RuntimeError(
            "Archive storage has not been initialized. Call set_archive_storage() before use."
        )
    return storage
MutationHandler = Callable[[RedcodeInstruction, int, "EvolverConfig", int], RedcodeInstruction]


def apply_major_mutation(
    _instruction: RedcodeInstruction,
    arena: int,
    _config: "EvolverConfig",
    _magic_number: int,
) -> RedcodeInstruction:
    return generate_random_instruction(arena)


def apply_nab_instruction(
    instruction: RedcodeInstruction,
    arena: int,
    config: "EvolverConfig",
    _magic_number: int,
) -> RedcodeInstruction:
    if config.last_arena == 0:
        return instruction

    donor_arena = _rng_int(0, config.last_arena)
    while donor_arena == arena and config.last_arena > 0:
        donor_arena = _rng_int(0, config.last_arena)

    console_log(
        "Nab instruction from arena " + str(donor_arena),
        minimum_level=VerbosityLevel.VERBOSE,
    )
    storage = get_arena_storage()
    donor_warrior = _rng_int(1, config.numwarriors)
    donor_lines = storage.get_warrior_lines(donor_arena, donor_warrior)

    if donor_lines:
        return parse_instruction_or_default(_rng_choice(donor_lines))

    console_log(
        "Donor warrior empty; skipping mutation.",
        minimum_level=VerbosityLevel.VERBOSE,
    )
    return instruction


def apply_minor_mutation(
    instruction: RedcodeInstruction,
    arena: int,
    config: "EvolverConfig",
    _magic_number: int,
) -> RedcodeInstruction:
    r = _rng_int(1, 6)
    if r == 1:
        instruction.opcode = choose_random_opcode(arena)
    elif r == 2:
        instruction.modifier = choose_random_modifier(arena)
    elif r == 3:
        instruction.a_mode = choose_random_mode(arena)
    elif r == 4:
        instruction.a_field = weighted_random_number(
            config.coresize_list[arena], config.warlen_list[arena]
        )
    elif r == 5:
        instruction.b_mode = choose_random_mode(arena)
    elif r == 6:
        instruction.b_field = weighted_random_number(
            config.coresize_list[arena], config.warlen_list[arena]
        )
    return instruction


def apply_micro_mutation(
    instruction: RedcodeInstruction,
    _arena: int,
    _config: "EvolverConfig",
    _magic_number: int,
) -> RedcodeInstruction:
    target_field = "a_field" if _rng_int(1, 2) == 1 else "b_field"
    current_value = _ensure_int(getattr(instruction, target_field))
    if _rng_int(1, 2) == 1:
        current_value += 1
    else:
        current_value -= 1
    setattr(instruction, target_field, current_value)
    return instruction


def apply_instruction_library(
    instruction: RedcodeInstruction,
    _arena: int,
    config: "EvolverConfig",
    _magic_number: int,
) -> RedcodeInstruction:
    if not config.library_path or not os.path.exists(config.library_path):
        return instruction

    with open(config.library_path, "r") as library_handle:
        library_lines = library_handle.readlines()
    if library_lines:
        return parse_instruction_or_default(_rng_choice(library_lines))
    return default_instruction()


def apply_magic_number_mutation(
    instruction: RedcodeInstruction,
    _arena: int,
    _config: "EvolverConfig",
    magic_number: int,
) -> RedcodeInstruction:
    if _rng_int(1, 2) == 1:
        instruction.a_field = magic_number
    else:
        instruction.b_field = magic_number
    return instruction


MUTATION_HANDLERS: dict[Marble, MutationHandler] = {
    Marble.DO_NOTHING: lambda instr, *_: instr,
    Marble.MAJOR_MUTATION: apply_major_mutation,
    Marble.NAB_INSTRUCTION: apply_nab_instruction,
    Marble.MINOR_MUTATION: apply_minor_mutation,
    Marble.MICRO_MUTATION: apply_micro_mutation,
    Marble.INSTRUCTION_LIBRARY: apply_instruction_library,
    Marble.MAGIC_NUMBER_MUTATION: apply_magic_number_mutation,
}


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
    winner: int, loser: int, arena: int, era: int, config: "EvolverConfig"
) -> ArchivingResult:
    events: list[ArchivingEvent] = []
    storage = get_arena_storage()
    archive_storage = get_archive_storage()

    if config.archive_list[era] != 0 and _rng_int(1, config.archive_list[era]) == 1:
        winlines = storage.get_warrior_lines(arena, winner)
        archive_filename = archive_storage.archive_warrior(
            warrior_id=winner,
            lines=winlines,
            config=config,
            get_random_int=_rng_int,
        )
        events.append(
            ArchivingEvent(
                action="archived",
                warrior_id=winner,
                archive_filename=archive_filename,
            )
        )

    if config.unarchive_list[era] != 0 and _rng_int(1, config.unarchive_list[era]) == 1:
        unarchive_result = archive_storage.unarchive_warrior(config, _rng_choice)
        if not unarchive_result:
            return ArchivingResult(events=events)
        archive_choice, sourcelines = unarchive_result

        instructions_written = 0
        new_lines: list[str] = []
        for line in sourcelines:
            instruction = parse_redcode_instruction(line)
            if instruction is None:
                continue
            new_lines.append(instruction_to_line(instruction, arena))
            instructions_written += 1
            if instructions_written >= config.warlen_list[arena]:
                break
        while instructions_written < config.warlen_list[arena]:
            new_lines.append(instruction_to_line(default_instruction(), arena))
            instructions_written += 1
        storage.set_warrior_lines(arena, loser, new_lines)
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
    config: "EvolverConfig",
    bag: list[Marble],
    data_logger: "DataLogger",
    scores: list[int],
    warriors: list[int],
) -> int:
    storage = get_arena_storage()
    winlines = storage.get_warrior_lines(arena, winner)

    partner_id = _rng_int(1, config.numwarriors)
    ranlines = storage.get_warrior_lines(arena, partner_id)

    if _rng_int(1, config.transpositionrate_list[era]) == 1:
        transpositions = _rng_int(1, int((config.warlen_list[arena] + 1) / 2))
        for _ in range(1, transpositions):
            fromline = _rng_int(0, config.warlen_list[arena] - 1)
            toline = _rng_int(0, config.warlen_list[arena] - 1)
            if _rng_int(1, 2) == 1:
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

    def _breed_offspring_once() -> list[str]:
        if config.prefer_winner_list[era] is True:
            pickingfrom = 1
        else:
            pickingfrom = _rng_int(1, 2)

        magic_number = weighted_random_number(
            config.coresize_list[arena], config.warlen_list[arena]
        )
        offspring_lines: list[str] = []
        for i in range(0, config.warlen_list[arena]):
            if _rng_int(1, config.crossoverrate_list[era]) == 1:
                pickingfrom = 2 if pickingfrom == 1 else 1

            if pickingfrom == 1:
                source_line = winlines[i] if i < len(winlines) else ""
            else:
                source_line = ranlines[i] if i < len(ranlines) else ""

            instruction = parse_instruction_or_default(source_line)
            chosen_marble = _rng_choice(bag)
            handler = MUTATION_HANDLERS.get(chosen_marble)
            if handler:
                instruction = handler(instruction, arena, config, magic_number)

            offspring_lines.append(instruction_to_line(instruction, arena))
            magic_number -= 1

        return offspring_lines

    new_lines = generate_warrior_lines_until_non_dat(
        _breed_offspring_once,
        context=f"Breeding offspring for arena {arena}, warrior {loser}",
        arena=arena,
    )

    storage.set_warrior_lines(arena, loser, new_lines)

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


def determine_winner_and_loser(
    warriors: list[int], scores: list[int]
) -> tuple[int, int, bool]:
    if len(warriors) < 2 or len(scores) < 2:
        raise ValueError("Expected scores for two warriors")

    if scores[1] == scores[0]:
        draw_rng = _get_evolverstage_override("get_random_int", _rng_int)
        draw_selection = draw_rng(1, 2)
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


def select_opponents(
    num_warriors: int, champion: Optional[int] = None
) -> tuple[int, int]:
    if champion is not None and _rng_int(0, 1) == 0:
        challenger = champion
        while challenger == champion:
            challenger = _rng_int(1, num_warriors)
        return champion, challenger

    cont1 = _rng_int(1, num_warriors)
    cont2 = cont1
    while cont2 == cont1:
        cont2 = _rng_int(1, num_warriors)
    return cont1, cont2


__all__ = [
    "set_engine_config",
    "configure_rng",
    "rebuild_instruction_tables",
    "SPEC_1994",
    "SPEC_1988",
    "DEFAULT_MODE",
    "DEFAULT_MODIFIER",
    "BASE_ADDRESSING_MODES",
    "ADDRESSING_MODES",
    "CANONICAL_SUPPORTED_OPCODES",
    "SUPPORTED_OPCODES",
    "UNSUPPORTED_OPCODES",
    "canonicalize_opcode",
    "GENERATION_OPCODE_POOL_1988",
    "get_arena_spec",
    "weighted_random_number",
    "coremod",
    "corenorm",
    "MAX_WARRIOR_FILENAME_ID",
    "RedcodeInstruction",
    "parse_redcode_instruction",
    "default_instruction",
    "sanitize_instruction",
    "format_redcode_instruction",
    "instruction_to_line",
    "parse_instruction_or_default",
    "choose_random_opcode",
    "choose_random_modifier",
    "choose_random_mode",
    "generate_random_instruction",
    "generate_warrior_lines_until_non_dat",
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
    "run_internal_battle",
    "execute_battle",
    "execute_battle_with_sources",
    "ArenaStorage",
    "DiskArenaStorage",
    "InMemoryArenaStorage",
    "set_arena_storage",
    "get_arena_storage",
    "create_arena_storage",
    "ArchiveStorage",
    "DiskArchiveStorage",
    "set_archive_storage",
    "get_archive_storage",
    "Marble",
    "MutationHandler",
    "apply_major_mutation",
    "apply_nab_instruction",
    "apply_minor_mutation",
    "apply_micro_mutation",
    "apply_instruction_library",
    "apply_magic_number_mutation",
    "MUTATION_HANDLERS",
    "ArchivingEvent",
    "ArchivingResult",
    "handle_archiving",
    "breed_offspring",
    "determine_winner_and_loser",
    "select_opponents",
]

