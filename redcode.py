from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple, TypeVar

from config import get_active_config, get_arena_spec

T = TypeVar("T")

DEFAULT_MODE = "$"
DEFAULT_MODIFIER = "F"
BASE_ADDRESSING_MODES = {"$", "#", "@", "<", ">", "*", "{", "}"}
ADDRESSING_MODES: set[str] = set(BASE_ADDRESSING_MODES)

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

GENERATION_OPCODE_POOL: list[str] = []
GENERATION_OPCODE_POOL_1988: list[str] = []

_rng_int: Callable[[int, int], int] = random.randint
_rng_choice: Callable[[Sequence[T]], T] = random.choice  # type: ignore[assignment]
_get_override: Callable[[str, object], object] = lambda name, default: default
_sync_export: Callable[[str, object], None] = lambda name, value: None


@dataclass
class InstructionTables:
    addressing_modes: set[str]
    generation_opcode_pool: list[str]
    generation_opcode_pool_1988: list[str]


def set_rng_helpers(
    random_int_func: Callable[[int, int], int],
    random_choice_func: Callable[[Sequence[T]], T],
) -> None:
    global _rng_int, _rng_choice
    _rng_int = random_int_func
    _rng_choice = random_choice_func


def set_override_helper(helper: Callable[[str, object], object]) -> None:
    global _get_override
    _get_override = helper


def set_sync_export(helper: Callable[[str, object], None]) -> None:
    global _sync_export
    _sync_export = helper


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


def set_pmars_score_pattern(pattern: re.Pattern[str]) -> None:
    global _PMARS_SCORE_RE
    _PMARS_SCORE_RE = pattern
def _build_opcode_pool(
    allowed_opcodes: set[str],
    default_pool: Sequence[str],
    *,
    instr_set: Sequence[str],
) -> tuple[list[str], set[str], bool]:
    pool: list[str] = []
    invalid_opcodes: set[str] = set()
    for instr in instr_set:
        normalized = instr.strip().upper()
        if not normalized:
            continue
        canonical_opcode = OPCODE_ALIASES.get(normalized, normalized)
        if (
            canonical_opcode in UNSUPPORTED_OPCODES
            or canonical_opcode not in allowed_opcodes
        ):
            invalid_opcodes.add(normalized)
            continue
        pool.append(canonical_opcode)

    if not pool and default_pool:
        return list(default_pool), invalid_opcodes, True

    return pool, invalid_opcodes, False


def set_instruction_tables(tables: InstructionTables) -> None:
    global ADDRESSING_MODES, GENERATION_OPCODE_POOL, GENERATION_OPCODE_POOL_1988

    ADDRESSING_MODES = set(tables.addressing_modes)
    GENERATION_OPCODE_POOL = list(tables.generation_opcode_pool)
    GENERATION_OPCODE_POOL_1988 = list(tables.generation_opcode_pool_1988)

    _sync_export("ADDRESSING_MODES", ADDRESSING_MODES)
    _sync_export("GENERATION_OPCODE_POOL", GENERATION_OPCODE_POOL)
    _sync_export("GENERATION_OPCODE_POOL_1988", GENERATION_OPCODE_POOL_1988)


def rebuild_instruction_tables(active_config) -> InstructionTables:
    invalid_reasons: list[str] = []
    allowed_1994 = SPEC_ALLOWED_OPCODES[SPEC_1994]
    instr_set = active_config.instr_set or []

    addressing_modes = set(BASE_ADDRESSING_MODES)
    if active_config.instr_modes:
        addressing_modes.update(
            mode.strip() for mode in active_config.instr_modes if mode.strip()
        )

    (
        generation_opcode_pool,
        invalid_generation_opcodes,
        _,
    ) = _build_opcode_pool(
        allowed_1994,
        [],
        instr_set=instr_set,
    )

    if invalid_generation_opcodes:
        invalid_reasons.append(
            "contains unsupported opcode(s): "
            + ", ".join(sorted(invalid_generation_opcodes))
        )

    if not generation_opcode_pool:
        invalid_reasons.append("must include at least one supported opcode other than DAT")
    elif all(opcode == "DAT" for opcode in generation_opcode_pool):
        invalid_reasons.append("must include at least one opcode other than DAT")

    if invalid_reasons:
        raise ValueError(
            "Invalid INSTR_SET configuration: " + "; ".join(invalid_reasons) + "."
        )

    (
        generation_opcode_pool_1988,
        _,
        used_default_1988,
    ) = _build_opcode_pool(
        SPEC_ALLOWED_OPCODES[SPEC_1988],
        DEFAULT_1988_GENERATION_POOL,
        instr_set=instr_set,
    )
    if not used_default_1988 and not any(
        opcode != "DAT" for opcode in generation_opcode_pool_1988
    ):
        non_dat_defaults = [
            opcode for opcode in DEFAULT_1988_GENERATION_POOL if opcode != "DAT"
        ]
        generation_opcode_pool_1988.extend(non_dat_defaults)

    tables = InstructionTables(
        addressing_modes=addressing_modes,
        generation_opcode_pool=generation_opcode_pool,
        generation_opcode_pool_1988=generation_opcode_pool_1988,
    )
    set_instruction_tables(tables)
    return tables


def coremod(num: int, modulus: int) -> int:
    if modulus == 0:
        raise ValueError("Modulus cannot be zero")
    return num % modulus


def corenorm(num: int, modulus: int) -> int:
    modded = coremod(num, modulus)
    if modded > modulus // 2:
        modded -= modulus
    return modded


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
        value = int(value_part)
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

    match = _REDCODE_INSTRUCTION_RE.match(code_part)
    if not match:
        before_comma = code_part.split(",", 1)[0]
        if "." not in before_comma:
            raise ValueError("Instruction is missing a modifier")
        raise ValueError(f"Invalid instruction format: '{code_part}'")

    label = match.group("label")
    opcode = match.group("opcode").upper()
    modifier = match.group("modifier").upper()
    canonical_opcode = OPCODE_ALIASES.get(opcode, opcode)
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


def _get_opcode_pool_for_arena(arena: int) -> list[str]:
    spec = get_arena_spec(arena)
    if spec == SPEC_1988:
        return _get_override("GENERATION_OPCODE_POOL_1988", GENERATION_OPCODE_POOL_1988)
    return _get_override("GENERATION_OPCODE_POOL", GENERATION_OPCODE_POOL)


def get_88_modifier(opcode: str, a_mode: str, b_mode: str) -> str:
    """Determine the ICWS'94 modifier that matches ICWS'88 behavior for an instruction."""
    if opcode in ("DAT", "NOP"):
        return "F"
    if opcode in ("MOV", "CMP", "SEQ", "SNE"):
        if a_mode == "#":
            return "AB"
        if b_mode == "#":
            return "B"
        return "I"
    if opcode in ("ADD", "SUB", "MUL", "DIV", "MOD"):
        if a_mode == "#":
            return "AB"
        if b_mode == "#":
            return "B"
        return "F"
    if opcode in ("SLT", "LDP", "STP"):
        if a_mode == "#":
            return "AB"
        return "B"
    return "B"


def sanitize_instruction(instr: RedcodeInstruction, arena: int) -> RedcodeInstruction:
    config = get_active_config()
    sanitized = instr.copy()
    original_opcode = (sanitized.opcode or "").upper()
    canonical_opcode = OPCODE_ALIASES.get(original_opcode, original_opcode)
    sanitized.opcode = canonical_opcode
    if canonical_opcode in UNSUPPORTED_OPCODES:
        raise ValueError(f"Opcode '{original_opcode}' is not supported")
    if canonical_opcode not in CANONICAL_SUPPORTED_OPCODES:
        raise ValueError(f"Unknown opcode '{original_opcode}'")

    spec = get_arena_spec(arena)
    allowed_opcodes = SPEC_ALLOWED_OPCODES.get(spec)
    if allowed_opcodes and canonical_opcode not in allowed_opcodes:
        # If the opcode is not allowed in this spec (e.g. MUL in 1988),
        # replace it with a default instruction.
        return default_instruction()

    # Quarantine logic for 1988 arenas: strip modifier and incompatible modes.
    if spec == SPEC_1988:
        if sanitized.a_mode not in SPEC_ALLOWED_ADDRESSING_MODES[SPEC_1988]:
            sanitized.a_mode = DEFAULT_MODE
        if sanitized.b_mode not in SPEC_ALLOWED_ADDRESSING_MODES[SPEC_1988]:
            sanitized.b_mode = DEFAULT_MODE

        # ICWS'88 specific constraints
        if sanitized.opcode == "DAT":
            if sanitized.a_mode not in {"#", "<"}:
                sanitized.a_mode = "#"
            if sanitized.b_mode not in {"#", "<"}:
                sanitized.b_mode = "#"
        elif sanitized.opcode in {"MOV", "ADD", "SUB", "CMP"}:
            if sanitized.b_mode == "#":
                sanitized.b_mode = "$"
        elif sanitized.opcode in {"JMP", "JMZ", "JMN", "DJN", "SPL"}:
            if sanitized.a_mode == "#":
                sanitized.a_mode = "$"

        sanitized.modifier = get_88_modifier(
            sanitized.opcode, sanitized.a_mode, sanitized.b_mode
        )
    else:
        if not sanitized.modifier:
            raise ValueError("Missing modifier for instruction")
        sanitized.modifier = sanitized.modifier.upper()
        allowed_modifiers = SPEC_ALLOWED_MODIFIERS.get(spec)
        if allowed_modifiers and sanitized.modifier not in allowed_modifiers:
            return default_instruction()

        if sanitized.a_mode not in ADDRESSING_MODES:
            raise ValueError(
                f"Invalid addressing mode '{sanitized.a_mode}' for A-field operand"
            )
        if sanitized.b_mode not in ADDRESSING_MODES:
            raise ValueError(
                f"Invalid addressing mode '{sanitized.b_mode}' for B-field operand"
            )
        allowed_modes = SPEC_ALLOWED_ADDRESSING_MODES.get(spec)
        if allowed_modes and sanitized.a_mode not in allowed_modes:
            return default_instruction()
        if allowed_modes and sanitized.b_mode not in allowed_modes:
            return default_instruction()

    sanitized.a_field = corenorm(
        coremod(int(sanitized.a_field), config.sanitize_list[arena]),
        config.coresize_list[arena],
    )
    sanitized.b_field = corenorm(
        coremod(int(sanitized.b_field), config.sanitize_list[arena]),
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
    config = get_active_config()
    spec = get_arena_spec(arena)
    modifier_pool = [
        item.strip().upper()
        for item in (config.instr_modif or [])
        if item.strip()
    ]
    if spec == SPEC_1988:
        allowed_modifiers = SPEC_ALLOWED_MODIFIERS.get(spec)
        modifier_pool = [
            modifier
            for modifier in modifier_pool
            if not allowed_modifiers or modifier in allowed_modifiers
        ]
        if not modifier_pool:
            modifier_pool = list(DEFAULT_1988_MODIFIERS)
    if modifier_pool:
        return _rng_choice(modifier_pool)
    return DEFAULT_MODIFIER


def choose_random_mode(arena: int) -> str:
    config = get_active_config()
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


def weighted_random_number(size: int, length: int) -> int:
    if _rng_int(1, 4) == 1:
        return _rng_int(-size, size)
    return _rng_int(-length, length)


def generate_random_instruction(arena: int) -> RedcodeInstruction:
    config = get_active_config()
    num1 = weighted_random_number(config.coresize_list[arena], config.warlen_list[arena])
    num2 = weighted_random_number(config.coresize_list[arena], config.warlen_list[arena])
    opcode = choose_random_opcode(arena)
    return RedcodeInstruction(
        opcode=opcode,
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
            "cannot generate non-DAT opcodes. "
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
