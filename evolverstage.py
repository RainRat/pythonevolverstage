import random
import os
import time
#import psutil #Not currently active. See bottom of code for how it could be used.
import configparser
import subprocess
from enum import Enum
import csv
import ctypes
import platform
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class EvolverConfig:
    battle_engine: str
    last_arena: int
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


def validate_config(config: EvolverConfig, config_path: Optional[str] = None) -> None:
    if config.last_arena is None:
        raise ValueError("LAST_ARENA must be specified in the configuration.")

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

    for name, values in per_arena_lists.items():
        if len(values) != arena_count:
            raise ValueError(
                f"{name} must contain {arena_count} entries (one for each arena),"
                f" but {len(values)} value(s) were provided."
            )

    for idx in range(arena_count):
        core_size = config.coresize_list[idx]
        read_limit = config.readlimit_list[idx]
        write_limit = config.writelimit_list[idx]
        if read_limit <= 0 or read_limit > core_size:
            raise ValueError(
                "READLIMIT_LIST entries must be between 1 and the arena's core size."
            )
        if write_limit <= 0 or write_limit > core_size:
            raise ValueError(
                "WRITELIMIT_LIST entries must be between 1 and the arena's core size."
            )

    if config.numwarriors is None or config.numwarriors <= 0:
        raise ValueError("NUMWARRIORS must be a positive integer.")

    if not config.battlerounds_list:
        raise ValueError("BATTLEROUNDS_LIST must contain at least one value.")

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

    base_path = os.getcwd()
    if config_path:
        config_directory = os.path.dirname(os.path.abspath(config_path))
        if config_directory:
            base_path = config_directory

    required_directories = [os.path.join(base_path, f"arena{i}") for i in range(arena_count)]
    required_directories.append(os.path.join(base_path, "archive"))

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
            if config.alreadyseeded:
                raise FileNotFoundError(
                    f"Required directory '{directory}' does not exist but ALREADYSEEDED is true."
                )


def load_configuration(path: str) -> EvolverConfig:
    parser = configparser.ConfigParser()
    read_files = parser.read(path)
    if not read_files:
        raise FileNotFoundError(f"Configuration file '{path}' not found")

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

    config = EvolverConfig(
        battle_engine=_read_config('BATTLE_ENGINE', data_type='string', default='external') or 'external',
        last_arena=_read_config('LAST_ARENA', data_type='int'),
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
        battle_log_file=_read_config('BATTLE_LOG_FILE', data_type='string'),
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
        library_path=_read_config('LIBRARY_PATH', data_type='string'),
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
try:
    lib_name = "redcode_worker.so"
    if platform.system() == "Windows":
        lib_name = "redcode_worker.dll"
    elif platform.system() == "Darwin":
        lib_name = "redcode_worker.dylib"

    lib_path = os.path.abspath(lib_name)
    CPP_WORKER_LIB = ctypes.CDLL(lib_path)

    CPP_WORKER_LIB.run_battle.argtypes = [
        ctypes.c_char_p, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ]
    CPP_WORKER_LIB.run_battle.restype = ctypes.c_char_p
    print("Successfully loaded C++ Redcode worker.")
except Exception as e:
    print(f"Could not load C++ Redcode worker: {e}")
    print("Internal battle engine will not be available.")

def run_nmars_command(arena, cont1, cont2, coresize, cycles, processes, warlen, wardistance, battlerounds):
  try:
    '''
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
    '''
    nmars_cmd = "nmars.exe" if os.name == "nt" else "nmars"
    args = {
        "-s": coresize,
        "-c": cycles,
        "-p": processes,
        "-l": warlen,
        "-d": wardistance,
        "-r": battlerounds,
    }
    cmd = [
        nmars_cmd,
        os.path.join(f"arena{arena}", f"{cont1}.red"),
        os.path.join(f"arena{arena}", f"{cont2}.red"),
    ]
    for flag, value in args.items():
        cmd.extend([flag, str(value)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout
  except FileNotFoundError as e:
    print(f"Unable to run {nmars_cmd}: {e}")
  except subprocess.SubprocessError as e:
    print(f"An error occurred: {e}")
  return None

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
):
    if not CPP_WORKER_LIB:
        print("C++ worker not available. Cannot run internal battle. Returning a draw.")
        return f"{cont1} 0 0 0 0 scores\n{cont2} 0 0 0 0 scores"

    try:
        # 1. Read warrior files
        w1_path = os.path.join(f"arena{arena}", f"{cont1}.red")
        w2_path = os.path.join(f"arena{arena}", f"{cont2}.red")
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
            battlerounds
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


def execute_battle(arena: int, cont1: int, cont2: int, era: int, verbose: bool = True):
    if config.battle_engine == 'internal':
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
            config.battlerounds_list[era],
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
            config.battlerounds_list[era],
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

    for line in output_lines:
        numline += 1
        if "scores" in line:
            if verbose:
                print(line.strip())
            splittedline = line.split()
            if len(splittedline) < 5:
                raise RuntimeError(f"Unexpected score line format: {line.strip()}")
            scores.append(int(splittedline[4]))
            warriors.append(int(splittedline[0]))
    if len(scores) < 2:
        raise RuntimeError("Battle engine output did not include scores for both warriors")
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

config = load_configuration('settings.ini')

DEFAULT_MODE = '$'
DEFAULT_MODIFIER = 'F'
ADDRESSING_MODES = set(config.instr_modes) if config.instr_modes else set()
ADDRESSING_MODES.update({'$', '#', '@', '<', '>', '*', '{', '}'})

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

GENERATION_OPCODE_POOL = []
_invalid_generation_opcodes = set()
if config.instr_set:
    for instr in config.instr_set:
        normalized = instr.strip().upper()
        if not normalized:
            continue
        canonical_opcode = OPCODE_ALIASES.get(normalized, normalized)
        if canonical_opcode in UNSUPPORTED_OPCODES or canonical_opcode not in CANONICAL_SUPPORTED_OPCODES:
            _invalid_generation_opcodes.add(normalized)
            continue
        GENERATION_OPCODE_POOL.append(canonical_opcode)
if _invalid_generation_opcodes:
    raise ValueError(
        "Unsupported opcodes specified in INSTR_SET: "
        + ', '.join(sorted(_invalid_generation_opcodes))
    )
del _invalid_generation_opcodes

def weighted_random_number(size, length):
    if random.randint(1,4)==1:
        return random.randint(-size, size)
    else:
        return random.randint(-length, length)

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
        return random.choice(GENERATION_OPCODE_POOL)
    return 'DAT'


def choose_random_modifier() -> str:
    if config.instr_modif:
        return random.choice(config.instr_modif).upper()
    return DEFAULT_MODIFIER


def choose_random_mode() -> str:
    if config.instr_modes:
        return random.choice(config.instr_modes)
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


def run_final_tournament(config: EvolverConfig):
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
    for arena in range(0, config.last_arena + 1):
        arena_dir = f"arena{arena}"
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

        print(f"\nArena {arena} final standings:")
        total_scores = {warrior_id: 0 for warrior_id in warrior_ids}

        for idx, cont1 in enumerate(warrior_ids):
            for cont2 in warrior_ids[idx + 1:]:
                warriors, scores = execute_battle(
                    arena,
                    cont1,
                    cont2,
                    final_era_index,
                    verbose=False,
                )
                for warrior_id, score in zip(warriors, scores):
                    total_scores[warrior_id] = total_scores.get(warrior_id, 0) + score

        rankings = sorted(total_scores.items(), key=lambda item: item[1], reverse=True)
        for position, (warrior_id, score) in enumerate(rankings, start=1):
            print(f"{position}. Warrior {warrior_id}: {score} points")
        champion_id, champion_score = rankings[0]
        print(
            f"Champion: Warrior {champion_id} with {champion_score} points"
        )


def select_opponents(num_warriors: int) -> tuple[int, int]:
    cont1 = random.randint(1, num_warriors)
    cont2 = cont1
    while cont2 == cont1:
        cont2 = random.randint(1, num_warriors)
    return cont1, cont2


def determine_winner_and_loser(
    warriors: list[int], scores: list[int]
) -> tuple[int, int]:
    if len(warriors) < 2 or len(scores) < 2:
        raise ValueError("Expected scores for two warriors")

    if scores[1] == scores[0]:
        print("draw")
        if random.randint(1, 2) == 1:
            return warriors[1], warriors[0]
        return warriors[0], warriors[1]
    if scores[1] > scores[0]:
        return warriors[1], warriors[0]
    return warriors[0], warriors[1]


def handle_archiving(
    winner: int, loser: int, arena: int, era: int, config: EvolverConfig
) -> bool:
    if config.archive_list[era] != 0 and random.randint(1, config.archive_list[era]) == 1:
        print("storing in archive")
        with open(os.path.join(f"arena{arena}", f"{winner}.red"), "r") as fw:
            winlines = fw.readlines()
        archive_filename = f"{random.randint(1, 9999)}.red"
        with open(os.path.join("archive", archive_filename), "w") as fd:
            fd.writelines(winlines)

    if config.unarchive_list[era] != 0 and random.randint(1, config.unarchive_list[era]) == 1:
        print("unarchiving")
        archive_files = os.listdir("archive")
        if not archive_files:
            return False
        with open(os.path.join("archive", random.choice(archive_files))) as fs:
            sourcelines = fs.readlines()

        instructions_written = 0
        with open(os.path.join(f"arena{arena}", f"{loser}.red"), "w") as fl:
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
        return True

    return False


def breed_offspring(
    winner: int,
    loser: int,
    arena: int,
    era: int,
    config: EvolverConfig,
    bag: list[Marble],
    data_logger: DataLogger,
    scores: list[int],
):
    with open(os.path.join(f"arena{arena}", f"{winner}.red"), "r") as fw:
        winlines = fw.readlines()

    randomwarrior = str(random.randint(1, config.numwarriors))
    print("winner will breed with " + randomwarrior)
    with open(os.path.join(f"arena{arena}", f"{randomwarrior}.red"), "r") as fr:
        ranlines = fr.readlines()

    if random.randint(1, config.transpositionrate_list[era]) == 1:
        print("Transposition")
        for _ in range(1, random.randint(1, int((config.warlen_list[arena] + 1) / 2))):
            fromline = random.randint(0, config.warlen_list[arena] - 1)
            toline = random.randint(0, config.warlen_list[arena] - 1)
            if random.randint(1, 2) == 1:
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
        pickingfrom = random.randint(1, 2)

    magic_number = weighted_random_number(
        config.coresize_list[arena], config.warlen_list[arena]
    )
    with open(os.path.join(f"arena{arena}", f"{loser}.red"), "w") as fl:
        for i in range(0, config.warlen_list[arena]):
            if random.randint(1, config.crossoverrate_list[era]) == 1:
                pickingfrom = 2 if pickingfrom == 1 else 1

            if pickingfrom == 1:
                source_line = winlines[i] if i < len(winlines) else ""
            else:
                source_line = ranlines[i] if i < len(ranlines) else ""

            instruction = parse_instruction_or_default(source_line)
            chosen_marble = random.choice(bag)
            if chosen_marble == Marble.MAJOR_MUTATION:
                print("Major mutation")
                instruction = generate_random_instruction(arena)
            elif (
                chosen_marble == Marble.NAB_INSTRUCTION
                and config.last_arena != 0
            ):
                donor_arena = random.randint(0, config.last_arena)
                while donor_arena == arena:
                    donor_arena = random.randint(0, config.last_arena)
                print("Nab instruction from arena " + str(donor_arena))
                donor_file = os.path.join(
                    f"arena{donor_arena}", f"{random.randint(1, config.numwarriors)}.red"
                )
                with open(donor_file, "r") as donor_handle:
                    donor_lines = donor_handle.readlines()
                if donor_lines:
                    instruction = parse_instruction_or_default(random.choice(donor_lines))
                else:
                    instruction = default_instruction()
            elif chosen_marble == Marble.MINOR_MUTATION:
                print("Minor mutation")
                r = random.randint(1, 6)
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
            elif chosen_marble == Marble.MICRO_MUTATION:
                print("Micro mutation")
                if random.randint(1, 2) == 1:
                    current_value = _ensure_int(instruction.a_field)
                    if random.randint(1, 2) == 1:
                        current_value = current_value + 1
                    else:
                        current_value = current_value - 1
                    instruction.a_field = current_value
                else:
                    current_value = _ensure_int(instruction.b_field)
                    if random.randint(1, 2) == 1:
                        current_value = current_value + 1
                    else:
                        current_value = current_value - 1
                    instruction.b_field = current_value
            elif (
                chosen_marble == Marble.INSTRUCTION_LIBRARY
                and config.library_path
                and os.path.exists(config.library_path)
            ):
                print("Instruction library")
                with open(config.library_path, "r") as library_handle:
                    library_lines = library_handle.readlines()
                if library_lines:
                    instruction = parse_instruction_or_default(random.choice(library_lines))
                else:
                    instruction = default_instruction()
            elif chosen_marble == Marble.MAGIC_NUMBER_MUTATION:
                print("Magic number mutation")
                if random.randint(1, 2) == 1:
                    instruction.a_field = magic_number
                else:
                    instruction.b_field = magic_number

            fl.write(instruction_to_line(instruction, arena))
            magic_number = magic_number - 1

    data_logger.log_data(
        era=era,
        arena=arena,
        winner=winner,
        loser=loser,
        score1=scores[0],
        score2=scores[1],
        bred_with=randomwarrior,
    )

if os.getenv("PYTHONEVOLVER_SKIP_MAIN") == "1":
    pass
else:
    if not config.alreadyseeded:
      print("Seeding")
      create_directory_if_not_exists("archive")
      for arena in range (0,config.last_arena+1):
        create_directory_if_not_exists(f"arena{arena}")
        for i in range(1, config.numwarriors+1):
          with open(os.path.join(f"arena{arena}", f"{i}.red"), "w") as f:
              for j in range(1, config.warlen_list[arena]+1):
                #Biasing toward more viable warriors: 3 in 4 chance of choosing an address within the warrior.
                #Same bias in mutation.
                instruction = generate_random_instruction(arena)
                f.write(instruction_to_line(instruction, arena))

    starttime=time.time() #time in seconds
    era=-1
    data_logger = DataLogger(filename=config.battle_log_file)
    bag: list[Marble] = []
    interrupted = False

    try:
      while(True):
        #before we do anything, determine which era we are in.
        prevera=era
        curtime=time.time()
        runtime_in_hours=(curtime-starttime)/60/60
        era=0
        if runtime_in_hours>config.clock_time*(1/3):
          era=1
        if runtime_in_hours>config.clock_time*(2/3):
          era=2
        if runtime_in_hours>config.clock_time:
          print("Clock time exceeded. Ending evolution loop.")
          break
        if config.final_era_only==True:
          era=2
        if era!=prevera:
          print(f"************** Switching from era {prevera + 1} to {era + 1} *******************")
          bag = [Marble.DO_NOTHING]*config.nothing_list[era] + [Marble.MAJOR_MUTATION]*config.random_list[era] + \
                [Marble.NAB_INSTRUCTION]*config.nab_list[era] + [Marble.MINOR_MUTATION]*config.mini_mut_list[era] + \
                [Marble.MICRO_MUTATION]*config.micro_mut_list[era] + [Marble.INSTRUCTION_LIBRARY]*config.library_list[era] + \
                [Marble.MAGIC_NUMBER_MUTATION]*config.magic_number_list[era]

        print ("{0:.2f}".format(config.clock_time-runtime_in_hours) + \
               " hours remaining ({0:.2f}%".format(runtime_in_hours/config.clock_time*100)+" complete) Era: "+str(era+1))

        arena = random.randint(0, config.last_arena)
        cont1, cont2 = select_opponents(config.numwarriors)
        warriors, scores = execute_battle(arena, cont1, cont2, era)
        winner, loser = determine_winner_and_loser(warriors, scores)

        if handle_archiving(winner, loser, arena, era, config):
          continue

        breed_offspring(
          winner,
          loser,
          arena,
          era,
          config,
          bag,
          data_logger,
          scores,
        )

    except KeyboardInterrupt:
      print("Evolution interrupted by user.")
      interrupted = True

    if not interrupted:
      print("Evolution loop completed.")

    if config.run_final_tournament:
      run_final_tournament(config)

    #  time.sleep(3) #uncomment this for simple proportion of sleep if you're using computer for something else

    #experimental. detect if computer being used and yield to other processes.
    #  while psutil.cpu_percent()>30: #I'm not sure what percentage of CPU usage to watch for. Probably depends
                                      # from computer to computer and personal taste.
    #    print("High CPU Usage. Pausing for 3 seconds.")
    #    time.sleep(3)
