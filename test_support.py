import ctypes
import pathlib
import subprocess
from functools import lru_cache

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent


def compile_worker() -> None:
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-shared",
            "-fPIC",
            str(PROJECT_ROOT / "redcode-worker.cpp"),
            "-o",
            "redcode_worker.so",
        ],
        check=True,
        cwd=PROJECT_ROOT,
    )


@lru_cache(maxsize=1)
def load_worker():
    compile_worker()
    lib_path = PROJECT_ROOT / "redcode_worker.so"
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
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
    ]
    lib.run_battle.restype = ctypes.c_char_p
    return lib
