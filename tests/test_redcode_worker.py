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
    ]
    lib.run_battle.restype = ctypes.c_char_p
    return lib


def get_process_counts(result_str):
    lines = result_str.strip().splitlines()
    counts = []
    for line in lines:
        parts = line.split()
        counts.append(int(parts[4]))
    return counts


def test_validate_self_tie():
    lib = load_worker()
    base_path = pathlib.Path(__file__).resolve().parents[1]
    code_path = base_path / "Validate1_1R_assembled.txt"
    with open(code_path, "r") as f:
        code = f.read()
    result = lib.run_battle(
        code.encode(), 1,
        code.encode(), 2,
        8000, 10000, 8000, 100
    ).decode()
    w1_procs, w2_procs = get_process_counts(result)
    assert w1_procs > 0 and w2_procs > 0, (
        "Validate1.1R should self-tie with processes remaining, got: " + result
    )
