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
def ensure_pmars_compiled() -> pathlib.Path:
    """Build the bundled pMARS emulator and return the binary path."""

    binary_name = "pmars.exe" if platform.system() == "Windows" else "pmars"
    source_dir = PROJECT_ROOT / "pMars" / "src"
    binary_path = source_dir / binary_name

    subprocess.run(["make", "pmars"], cwd=source_dir, check=True)

    if not binary_path.exists():
        raise FileNotFoundError(
            "pMARS build completed but binary was not created at "
            f"{binary_path}"
        )

    return binary_path


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
        ctypes.c_int,
    ]
    lib.run_battle.restype = ctypes.c_char_p
    return lib
