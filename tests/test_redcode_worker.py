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
