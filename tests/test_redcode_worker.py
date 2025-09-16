import os
import subprocess
import ctypes
import pathlib

def compile_worker():
    subprocess.run([
        "g++",
        "-std=c++17",
        "-shared",
        "-fPIC",
        str(pathlib.Path(__file__).resolve().parents[1] / "redcode-worker.cpp"),
        "-o",
        "redcode_worker.so",
    ], check=True, cwd=pathlib.Path(__file__).resolve().parents[1])


def load_worker():
    compile_worker()
    lib_path = pathlib.Path(__file__).resolve().parents[1] / "redcode_worker.so"
    lib = ctypes.CDLL(str(lib_path))
    lib.run_battle.argtypes = [
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
    ]
    lib.run_battle.restype = ctypes.c_char_p
    return lib


def get_scores(result_str):
    lines = result_str.strip().splitlines()
    scores = []
    for line in lines:
        parts = line.split()
        scores.append(int(parts[4]))
    return scores


def test_validate_self_tie():
    lib = load_worker()
    base_path = pathlib.Path(__file__).resolve().parents[1]
    code_path = base_path / "Validate1_1R_assembled.txt"
    with open(code_path, "r") as f:
        code = f.read()
    rounds = 5
    result = lib.run_battle(
        code.encode(), 1,
        code.encode(), 2,
        8000, 10000, 8000, 100, rounds
    ).decode()
    w1_score, w2_score = get_scores(result)
    assert w1_score == w2_score == rounds, (
        "Validate1.1R should score " + str(rounds) + " each, got: " + result
    )


def test_invalid_operand_returns_error():
    lib = load_worker()
    invalid_code = "MOV.I #abc, $0\n"
    result = lib.run_battle(
        invalid_code.encode(), 1,
        invalid_code.encode(), 2,
        8000, 1000, 8000, 100, 1
    ).decode()
    assert result.startswith("ERROR:"), f"Expected error response, got: {result}"
    assert "Invalid numeric operand" in result


def test_mixed_case_warrior_with_inline_comments():
    lib = load_worker()
    warrior = (
        "mov.i $0, $0 ; copy current cell\n"
        "add.aB #1,$2 ; adjust pointer\n"
    )
    result = lib.run_battle(
        warrior.encode(), 1,
        warrior.encode(), 2,
        8000, 10, 8000, 1, 1
    ).decode()
    assert not result.startswith("ERROR:"), f"Expected warrior to load, got: {result}"
    scores = get_scores(result)
    assert len(scores) == 2


def test_org_pseudo_opcode_rejected():
    lib = load_worker()
    warrior = "ORG 1\nDAT.F #0, #0\n"
    result = lib.run_battle(
        warrior.encode(), 1,
        warrior.encode(), 2,
        8000, 10, 8000, 1, 1
    ).decode()
    assert result.startswith("ERROR:"), f"Expected ORG to be rejected, got: {result}"
    assert "Unsupported pseudo-opcode 'ORG'" in result


def test_battle_stops_once_outcome_decided():
    lib = load_worker()
    dominant_warrior = "JMP 0\n"
    fragile_warrior = "DAT.F #0, #0\n"
    rounds = 100
    result = lib.run_battle(
        dominant_warrior.encode(), 1,
        fragile_warrior.encode(), 2,
        8000, 50, 8000, 1, rounds
    ).decode()
    w1_score, w2_score = get_scores(result)
    assert w2_score == 0, f"Expected fragile warrior to lose every round, got scores {w1_score}, {w2_score}"
    expected_rounds_played = (rounds // 2) + 1
    expected_score = expected_rounds_played * 3
    assert w1_score == expected_score, (
        "Battle should stop once the outcome is locked; "
        f"expected leader score {expected_score} for {expected_rounds_played} rounds, got {w1_score}"
    )
