"""Utility to build a deduplicated instruction library from assembled warriors.

This script reads one or more pMARS-assembled warrior files (for example the
files under ``baseline/``) and extracts the individual Redcode instructions. It
normalises the whitespace, discards pseudo-ops like ``ORG``/``END``, and writes a
sorted list that can be used as the evolver's instruction library.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Set

# Base opcodes supported by the evolver. The assembled files may include a
# modifier suffix such as ``.I`` or ``.AB``; we only need the base opcode to
# identify whether the token is a real instruction or a label.
_VALID_BASE_OPCODES = {
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
    "SNE",
    "SLT",
    "SPL",
    "NOP",
}

# Pseudo-opcodes we explicitly ignore when building the library.
_PSEUDO_OPS = {"ORG", "END"}


def _is_opcode(token: str) -> bool:
    """Return ``True`` if *token* represents a supported opcode."""

    if not token:
        return False
    base = token.split(".", 1)[0].upper()
    if base in _PSEUDO_OPS:
        return False
    return base in _VALID_BASE_OPCODES


def _extract_instruction(raw_line: str) -> str | None:
    """Normalise a single assembled line into an instruction string."""

    # Remove trailing comments and whitespace.
    line, *_ = raw_line.split(";", 1)
    stripped = line.strip()
    if not stripped:
        return None

    parts = stripped.split()
    if not parts:
        return None

    opcode_index = 0
    if not _is_opcode(parts[opcode_index]):
        opcode_index += 1
        if opcode_index >= len(parts) or not _is_opcode(parts[opcode_index]):
            # Either a pseudo-op like ORG/END or a line that does not contain a
            # proper instruction. Skip it.
            return None

    opcode = parts[opcode_index].upper()
    operands = parts[opcode_index + 1 :]

    if operands:
        return f"{opcode} {' '.join(operands)}"
    return opcode


def _instructions_from_file(path: Path) -> Iterable[str]:
    """Yield normalised instructions from an assembled warrior file."""

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            instruction = _extract_instruction(line)
            if instruction is not None:
                yield instruction


def _build_library(paths: Iterable[Path]) -> list[str]:
    """Read *paths* and return a sorted, deduplicated instruction list."""

    instructions: Set[str] = set()
    for file_path in paths:
        for instruction in _instructions_from_file(file_path):
            instructions.add(instruction)
    return sorted(instructions)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create a deduplicated instruction library from assembled "
            "pMARS output."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help=(
            "One or more assembled warrior files to consume. These should "
            "already have labels resolved (as produced by pMARS -o)."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help=(
            "Destination file for the instruction library. If omitted, the "
            "library is written to standard output."
        ),
    )

    args = parser.parse_args()

    library = _build_library(args.inputs)

    if args.output is None:
        for instruction in library:
            print(instruction)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(library) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
