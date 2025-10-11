import ctypes
import pathlib
import platform
import subprocess
from functools import lru_cache

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent


def _shared_library_extension() -> str:
    system = platform.system()
    if system == "Windows":
        return ".dll"
    if system == "Darwin":
        return ".dylib"
    return ".so"


def compile_worker() -> None:
    output_name = f"redcode_worker{_shared_library_extension()}"
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-shared",
            "-fPIC",
            str(PROJECT_ROOT / "redcode-worker.cpp"),
            "-o",
            output_name,
        ],
        check=True,
        cwd=PROJECT_ROOT,
    )


@lru_cache(maxsize=1)
def load_worker():
    compile_worker()
    lib_path = PROJECT_ROOT / f"redcode_worker{_shared_library_extension()}"
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
