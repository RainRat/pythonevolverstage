import itertools
import pathlib
import random
import re
import subprocess
import sys
import textwrap

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from test_support import ensure_pmars_compiled, load_worker


CORESIZE = 80
MAX_CYCLES = 400
MAX_PROCESSES = 80
MAX_LENGTH = 20
MIN_DISTANCE = 20
ROUNDS = 1

OPCODES = [
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
    "SLT",
    "SPL",
    "SNE",
    "NOP",
]

MODIFIERS = ["A", "B", "AB", "BA", "F", "X", "I"]

WRITE_TARGET_OPS = {"MOV", "ADD", "SUB", "MUL", "DIV", "MOD", "JMP", "JMZ", "JMN", "DJN", "SPL"}
NON_WRITING_OPS = {"CMP", "SEQ", "SNE", "SLT", "NOP", "DAT"}
ADDRESS_MODES_SOURCE = ["#", "$", "@", "<", ">", "*", "{", "}"]
ADDRESS_MODES_TARGET = ["$", "@", "<", ">", "*", "{", "}"]
RANDOM_CASES = 50
RANDOM_SEED = 0xC0DE


def _ensure_trailing_newline(code: str) -> str:
    return code if code.endswith("\n") else code + "\n"


def _write_warrior(path, code: str):
    path.write_text(_ensure_trailing_newline(code), encoding="utf-8")
    return path


def _make_dat_line(rng: random.Random) -> str:
    a_field = rng.randint(-5, 5)
    if a_field == 0:
        a_field = 1
    b_field = rng.randint(-5, 5)
    if b_field == 0:
        b_field = 2
    return f"DAT.F #{a_field}, #{b_field}"


def _format_instruction(opcode: str, modifier: str, a_mode: str, a_field: int, b_mode: str, b_field: int) -> str:
    return f"{opcode}.{modifier} {a_mode}{a_field}, {b_mode}{b_field}"


def _run_pmars(binary_path, w1_path, w2_path):
    cmd = [
        str(binary_path),
        "-b",
        "-f",
        "-r",
        str(ROUNDS),
        "-s",
        str(CORESIZE),
        "-c",
        str(MAX_CYCLES),
        "-p",
        str(MAX_PROCESSES),
        "-l",
        str(MAX_LENGTH),
        "-d",
        str(MIN_DISTANCE),
        str(w1_path),
        str(w2_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    output = result.stdout or ""
    if not output.strip() and result.stderr:
        output = result.stderr
    return output


def _parse_pmars_scores(output: str) -> list[int]:
    scores: list[int] = []
    for line in output.splitlines():
        if "scores" not in line:
            continue
        match = re.search(r"scores\s+(-?\d+)", line)
        if not match:
            continue
        scores.append(int(match.group(1)))
    if len(scores) != 2:
        raise AssertionError(f"Unable to parse pMARS scores from output:\n{output}")
    return scores


def _parse_internal_scores(output: str) -> list[int]:
    scores: list[int] = []
    for line in output.strip().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        scores.append(int(parts[4]))
    if len(scores) != 2:
        raise AssertionError(f"Unexpected internal engine output:\n{output}")
    return scores


def _run_internal_engine(lib, warrior: str, opponent: str, seed: int) -> str:
    return lib.run_battle(
        warrior.encode(),
        1,
        opponent.encode(),
        2,
        CORESIZE,
        MAX_CYCLES,
        MAX_PROCESSES,
        CORESIZE,
        CORESIZE,
        MIN_DISTANCE,
        MAX_LENGTH,
        ROUNDS,
        seed,
        0,
    ).decode()


def _compare_engines(lib, pmars_binary, tmp_path, warrior: str, opponent: str, seed: int):
    w1_path = _write_warrior(tmp_path / "warrior1.red", warrior)
    w2_path = _write_warrior(tmp_path / "warrior2.red", opponent)

    pmars_output = _run_pmars(pmars_binary, w1_path, w2_path)
    pmars_scores = _parse_pmars_scores(pmars_output)

    internal_output = _run_internal_engine(lib, warrior, opponent, seed)
    assert not internal_output.startswith("ERROR:"), internal_output
    internal_scores = _parse_internal_scores(internal_output)

    assert internal_scores == pmars_scores, (
        "Internal engine scores do not match pMARS reference output.\n"
        f"pMARS output:\n{pmars_output}\n"
        f"Internal output:\n{internal_output}"
    )


@pytest.fixture(scope="module")
def pmars_binary():
    return ensure_pmars_compiled()


@pytest.fixture(scope="module")
def internal_worker():
    return load_worker()


def _opcode_modifier_warrior(opcode: str, modifier: str) -> str:
    lines = [
        _format_instruction(opcode, modifier, "$", 1, "$", 2),
        "DAT.F #7, #3",
        "DAT.F #5, #1",
        "JMP.B $0, $0",
    ]
    return "\n".join(lines) + "\n"


def _random_instruction(rng: random.Random) -> str:
    opcode = rng.choice(OPCODES)
    modifier = rng.choice(MODIFIERS)

    if opcode in WRITE_TARGET_OPS:
        b_mode_choices = ADDRESS_MODES_TARGET
    elif opcode in NON_WRITING_OPS:
        b_mode_choices = ADDRESS_MODES_SOURCE
    else:
        b_mode_choices = ADDRESS_MODES_SOURCE

    a_mode = rng.choice(ADDRESS_MODES_SOURCE)
    b_mode = rng.choice(b_mode_choices)

    def _field_for_mode(mode: str) -> int:
        if mode == "#":
            value = rng.randint(-5, 5)
            return value if value != 0 else 1
        # Use offsets that target our local DAT setup (-1 or -2) or stay close
        return rng.choice([-1, -2, -3, 1, 2])

    a_field = _field_for_mode(a_mode)
    b_field = _field_for_mode(b_mode)

    if opcode in {"DIV", "MOD"}:
        # Ensure the divisor is non-zero by targeting the first DAT line
        b_mode = "$"
        b_field = -2
        if a_mode == "#":
            a_field = rng.choice([1, -1, 2, -2, 3])

    if opcode in {"JMP", "JMZ", "JMN", "DJN", "SPL"}:
        # Guarantee valid execution targets by jumping to the nearby loop line
        b_mode = "$"
        b_field = 1

    return _format_instruction(opcode, modifier, a_mode, a_field, b_mode, b_field)


def _random_warrior(rng: random.Random) -> str:
    lines = [
        _make_dat_line(rng),
        _make_dat_line(rng),
    ]

    for _ in range(3):
        lines.append(_random_instruction(rng))

    lines.append("JMP.B $0, $0")
    return "\n".join(lines) + "\n"


def _random_cases() -> list[int]:
    return list(range(RANDOM_CASES))


PMARS_PARITY_CASES = [
    pytest.param(
        textwrap.dedent(
            """
            JMP.B $4, $0
            DAT.F #0, #0
            DAT.F #0, #5
            DAT.F #10, #20
            SPL.B $3, $0
            DIV.F $-3, $-2
            JMP.B $6, $0
            SNE.B #20, $-4
            JMP.B $-1, $0
            SEQ.B #4, $-6
            JMP.B $2, $0
            MOV.B #1, $-10
            JMP.B $0, $0
            """
        ).strip(),
        "JMP.B $0, $0\n",
        123,
        id="div-completes-fields",
    ),
    pytest.param(
        textwrap.dedent(
            """
            JMP.B $5, $0
            DAT.F #0, #0
            DAT.F #0, #0
            DAT.F #1, #0
            DAT.F #1, #2
            JMN.I $3, $-2
            MOV.B #2, $-5
            JMP.B $2, $0
            MOV.B #1, $-7
            DJN.I $3, $-5
            MOV.B #2, $-8
            JMP.B $2, $0
            MOV.B #1, $-10
            DAT.F #0, #0
            """
        ).strip(),
        "JMP.B $0, $0\n",
        456,
        id="jmn-djn-or-semantics",
    ),
    pytest.param(
        "MOV.B #123, @-1\nJMP.B $-2, $0\n",
        "JMP.B $0, $0\n",
        789,
        id="mov-immediate-indirect",
    ),
]


@pytest.mark.parametrize("warrior, opponent, seed", PMARS_PARITY_CASES)
def test_internal_engine_matches_pmars(tmp_path, pmars_binary, internal_worker, warrior, opponent, seed):
    _compare_engines(internal_worker, pmars_binary, tmp_path, warrior, opponent, seed)


@pytest.mark.parametrize("opcode, modifier", list(itertools.product(OPCODES, MODIFIERS)))
def test_all_opcode_modifier_pairs(tmp_path, pmars_binary, internal_worker, opcode, modifier):
    warrior = _opcode_modifier_warrior(opcode, modifier)
    opponent = "DAT.F #0, #0\nJMP.B $0, $0\n"
    seed = (
        OPCODES.index(opcode) * len(MODIFIERS)
        + MODIFIERS.index(modifier)
        + 1
    )
    _compare_engines(internal_worker, pmars_binary, tmp_path, warrior, opponent, seed)


@pytest.mark.parametrize("case_index", _random_cases(), ids=lambda idx: f"random-{idx}")
def test_random_programs_match_pmars(tmp_path, pmars_binary, internal_worker, case_index):
    rng = random.Random(RANDOM_SEED + case_index)
    warrior = _random_warrior(rng)
    opponent = _random_warrior(rng)
    seed = rng.randint(0, 2**31 - 1)
    _compare_engines(internal_worker, pmars_binary, tmp_path, warrior, opponent, seed)
