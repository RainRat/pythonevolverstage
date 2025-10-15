import pathlib
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


def _ensure_trailing_newline(code: str) -> str:
    return code if code.endswith("\n") else code + "\n"


def _write_warrior(path, code: str):
    path.write_text(_ensure_trailing_newline(code), encoding="utf-8")
    return path


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
def test_internal_engine_matches_pmars(tmp_path, warrior, opponent, seed):
    pmars_binary = ensure_pmars_compiled()
    lib = load_worker()

    w1_path = _write_warrior(tmp_path / "warrior1.red", warrior)
    w2_path = _write_warrior(tmp_path / "warrior2.red", opponent)

    pmars_output = _run_pmars(pmars_binary, w1_path, w2_path)
    pmars_scores = _parse_pmars_scores(pmars_output)

    internal_result = lib.run_battle(
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
    ).decode()

    assert not internal_result.startswith("ERROR:"), internal_result

    internal_scores = _parse_internal_scores(internal_result)
    assert internal_scores == pmars_scores, (
        "Internal engine scores do not match pMARS reference output.\n"
        f"pMARS output:\n{pmars_output}\n"
        f"Internal output:\n{internal_result}"
    )
