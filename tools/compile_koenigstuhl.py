"""Compile the cached Koenigstuhl top-50 sources for the internal worker."""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PMARS = Path(os.environ.get("PMARS_BIN", ROOT / ".local/corewar-prep-2026-10-28/pmars-reference/src/pmars"))
REFERENCE = ROOT / "references/koenigstuhl"


def compile_one(source: Path, spec: str) -> str:
    command = [str(PMARS), "-A", "-s", "8000", "-p", "8000", "-c", "80000", "-l", "100"]
    if spec == "88":
        command.append("-8")
    result = subprocess.run(command + [str(source)], text=True, capture_output=True, check=True)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    entry_match = re.fullmatch(r"ORG\s+(\d+)", lines[0])
    if entry_match is None:
        raise ValueError(f"pMARS did not report an entry point for {source}")
    entry = int(entry_match.group(1))
    instructions = []
    for line in lines[1:]:
        if line.startswith("END"):
            continue
        line = re.sub(r"([#$@<>*{}])\s+(-?\d+)", r"\1\2", line)
        instructions.append(re.sub(r"\s+", " ", line))
    if not 0 <= entry < len(instructions) <= 100:
        raise ValueError(f"Invalid entry point or length for {source}: {entry}, {len(instructions)}")
    if spec == "88":
        return "\n".join(instructions + [f"END {entry}"]) + "\n"
    instructions[entry] = "START " + instructions[entry]
    return "ORG START\n" + "\n".join(instructions) + "\n"


def main() -> None:
    worker = ctypes.CDLL(str(ROOT / "redcode_worker.so"))
    worker.run_battle.argtypes = [ctypes.c_char_p, ctypes.c_int] * 2 + [ctypes.c_int] * 10
    worker.run_battle.restype = ctypes.c_char_p
    for spec in ("88", "94"):
        destination = ROOT / "bench" / f"koenigstuhl_{'94nop' if spec == '94' else '88'}" / "arena0"
        destination.mkdir(parents=True, exist_ok=True)
        sources = sorted((REFERENCE / f"{spec}_raw").glob("*.red"))
        if len(sources) != 59:
            raise RuntimeError(f"Expected 59 cached {spec} sources, found {len(sources)}")
        library = set()
        for source in sources:
            compiled = compile_one(source, spec)
            opponent = b"DAT #0, #0\n" if spec == "88" else b"DAT.F #0, #0\n"
            result = worker.run_battle(compiled.encode(), 1, opponent, 2,
                                       8000, 80000, 8000, 8000, 8000, 100, 100, 1, 12345,
                                       int(spec == "88")).decode()
            if result.startswith("ERROR:"):
                raise RuntimeError(f"Worker rejected {source.name}: {result.strip()}")
            output = destination / source.name
            if output.exists() and output.read_text() != compiled:
                raise RuntimeError(f"Refusing to replace changed benchmark: {output}")
            output.write_text(compiled)
            if spec == "94":
                for line in compiled.splitlines():
                    instruction = line.removeprefix("START ")
                    if instruction not in {"ORG START", "DAT.F $0, $0"}:
                        library.add(instruction)
        if spec == "94":
            path = destination.parent / "instructions.txt"
            content = "\n".join(sorted(library)) + "\n"
            if path.exists() and path.read_text() != content:
                raise RuntimeError(f"Refusing to replace changed library: {path}")
            path.write_text(content)
        print(f"Compiled and worker-validated {len(sources)} {spec} warriors in {destination}")


if __name__ == "__main__":
    main()
