import os
import pathlib
import sys
import textwrap
from dataclasses import dataclass
from typing import Optional

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASELINE_DIR = PROJECT_ROOT / "baseline"

from engine import corenorm
from test_support import load_worker


def get_scores(result_str):
    lines = result_str.strip().splitlines()
    scores = []
    for line in lines:
        parts = line.split()
        scores.append(int(parts[4]))
    return scores


@dataclass
class BaselineEntry:
    label: Optional[str]
    opcode: str
    a_mode: str
    a_value: int
    b_mode: str
    b_value: int


def load_baseline_warrior(filename: str) -> str:
    path = BASELINE_DIR / filename
    text = path.read_text(encoding="utf-8")
    entries: list[BaselineEntry] = []
    start_label: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.split(";", 1)[0].rstrip()
        if not line:
            continue
        stripped_upper = line.strip().upper()
        if stripped_upper.startswith("ORG"):
            parts = line.split()
            if len(parts) > 1:
                start_label = parts[1].rstrip(":")
            continue
        if stripped_upper.startswith("END"):
            continue

        label: Optional[str] = None
        tokens = line.split()
        while tokens and "." not in tokens[0] and tokens[0][0] not in "#$@<>*{}":
            potential_label = tokens.pop(0)
            label = potential_label.rstrip(":")
        if not tokens:
            continue

        opcode = tokens[0]
        if len(tokens) < 5:
            raise ValueError(f"Unexpected operand layout in {filename!r}: {raw_line!r}")
        a_mode = tokens[1]
        b_mode = tokens[3]
        try:
            a_value = int(tokens[2].rstrip(","))
            b_value = int(tokens[4].rstrip(","))
        except ValueError as exc:
            raise ValueError(f"Failed to parse numeric operands in {filename!r}: {raw_line!r}") from exc
        entries.append(BaselineEntry(label, opcode, a_mode, a_value, b_mode, b_value))

    if start_label is not None:
        rotated: list[int] = list(range(len(entries)))
        start_index: Optional[int] = None
        for idx, entry in enumerate(entries):
            if entry.label and entry.label.upper() == start_label.upper():
                start_index = idx
                break
        if start_index is not None and start_index != 0:
            rotated = rotated[start_index:] + rotated[:start_index]
        else:
            rotated = list(range(len(entries)))
        start_index = start_index or 0
    else:
        rotated = list(range(len(entries)))
        start_index = 0

    total = len(entries)
    assembled_lines: list[str] = []
    for new_pos, original_index in enumerate(rotated):
        entry = entries[original_index]

        def adjust_operand(mode: str, value: int) -> int:
            if mode == "#" or total == 0:
                return value
            target_original = (original_index + value) % total
            target_rotated = (target_original - start_index) % total
            return target_rotated - new_pos

        adjusted_a = adjust_operand(entry.a_mode, entry.a_value)
        adjusted_b = adjust_operand(entry.b_mode, entry.b_value)
        assembled_lines.append(
            f"{entry.opcode} {entry.a_mode}{adjusted_a}, {entry.b_mode}{adjusted_b}"
        )

    return "\n".join(assembled_lines) + "\n"


def parse_folding_offsets() -> list[int]:
    path = BASELINE_DIR / "folding.txt"
    offsets: list[int] = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped.startswith(";After"):
                break
            if stripped.startswith(";"):
                continue
            if stripped.upper().startswith("ORG") or stripped.upper().startswith("END"):
                continue
            if "DAT" not in stripped.upper():
                continue
            first_operand = stripped.split(",", 1)[0]
            if "#" not in first_operand:
                continue
            numeric_str = first_operand.split("#", 1)[1].strip()
            offsets.append(int(numeric_str))
    return offsets


def test_validate_self_tie():
    lib = load_worker()
    base_path = pathlib.Path(__file__).resolve().parents[1]
    code_path = base_path / "Validate1_1R_assembled.txt"
    with open(code_path, "r", encoding="utf-8") as f:
        code = f.read()
    rounds = 5
    result = lib.run_battle(
        code.encode(), 1,
        code.encode(), 2,
        8000, 10000, 8000, 8000, 8000, 100, 100, rounds, -1,
        0,
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
        8000, 1000, 8000, 8000, 8000, 100, 100, 1, -1,
        0,
    ).decode()
    assert result.startswith("ERROR:"), f"Expected error response, got: {result}"
    assert "Invalid numeric operand" in result


def test_large_configuration_limits_are_supported():
    lib = load_worker()
    warrior = "DAT.F #0, #0\n"
    core_size = 200_000
    max_cycles = 1_000_000
    max_processes = 120_000
    min_distance = core_size // 2
    max_warrior_length = min_distance
    result = lib.run_battle(
        warrior.encode(), 1,
        warrior.encode(), 2,
        core_size, max_cycles, max_processes,
        core_size, core_size,
        min_distance, max_warrior_length, 10, -1,
        0,
    ).decode()
    assert not result.startswith("ERROR:"), result


def test_min_distance_shorter_than_max_warrior_length_is_rejected():
    lib = load_worker()
    warrior = "JMP.B $0, $0\n"
    result = lib.run_battle(
        warrior.encode(), 1,
        warrior.encode(), 2,
        80, 200, 80, 80, 80, 5, 6, 1, -1,
        0,
    ).decode()
    assert result.startswith("ERROR:"), result
    assert "Min distance must be greater than or equal to max warrior length" in result


def test_mov_immediate_copies_instruction(tmp_path, monkeypatch):
    lib = load_worker()
    trace_file = tmp_path / "trace.log"
    monkeypatch.setenv("REDCODE_TRACE_FILE", str(trace_file))

    warrior1 = "\n".join(
        [
            "MOV.I #7, $1",
            "JMP.F $1, $0",
        ]
    ) + "\n"
    warrior2 = "\n".join(
        [
            "NOP.F $0, $0",
            "NOP.F $0, $0",
        ]
    ) + "\n"

    result = lib.run_battle(
        warrior1.encode(), 1,
        warrior2.encode(), 2,
        80, 50, 10,
        80, 80,
        5, 5, 1, -1,
        0,
    ).decode()

    assert not result.startswith("ERROR:"), result

    trace_contents = trace_file.read_text(encoding="utf-8")
    assert "WRITE @1 {MOV.I #7, $1}" in trace_contents


def test_1988_mode_rejects_1994_opcode():
    lib = load_worker()
    warrior = "MUL.F $0, $0\n"
    result = lib.run_battle(
        warrior.encode(), 1,
        warrior.encode(), 2,
        8000, 1000, 8000, 8000, 8000, 100, 100, 1, -1,
        1,
    ).decode()
    assert result.startswith("ERROR:"), result
    assert "1988" in result


def test_mixed_case_warrior_with_inline_comments():
    lib = load_worker()
    warrior = (
        "mov.i $0, $0 ; copy current cell\n"
        "add.aB #1,$2 ; adjust pointer\n"
    )
    result = lib.run_battle(
        warrior.encode(), 1,
        warrior.encode(), 2,
        8000, 10, 8000, 8000, 8000, 100, 100, 1, -1,
        0,
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
        8000, 10, 8000, 8000, 8000, 100, 100, 1, -1,
        0,
    ).decode()
    assert result.startswith("ERROR:"), f"Expected ORG to be rejected, got: {result}"
    assert "Unknown opcode 'ORG'" in result


def test_battle_stops_once_outcome_decided():
    lib = load_worker()
    dominant_warrior = "JMP.B $0, $0\n"
    fragile_warrior = "DAT.F #0, #0\n"
    rounds = 100
    result = lib.run_battle(
        dominant_warrior.encode(), 1,
        fragile_warrior.encode(), 2,
        8000, 50, 8000, 8000, 8000, 100, 100, rounds, -1,
        0,
    ).decode()
    w1_score, w2_score = get_scores(result)
    assert w2_score == 0, f"Expected fragile warrior to lose every round, got scores {w1_score}, {w2_score}"
    expected_rounds_played = (rounds // 2) + 1
    expected_score = expected_rounds_played * 3
    assert w1_score == expected_score, (
        "Battle should stop once the outcome is locked; "
        f"expected leader score {expected_score} for {expected_rounds_played} rounds, got {w1_score}"
    )


def test_round_limit_is_enforced():
    lib = load_worker()
    warrior = "DAT.F #0, #0\n"
    excessive_rounds = 200_000
    result = lib.run_battle(
        warrior.encode(), 1,
        warrior.encode(), 2,
        8000, 1000, 8000, 8000, 8000, 100, 100, excessive_rounds, -1,
        0,
    ).decode()
    assert result.startswith("ERROR:"), f"Expected error response, got: {result}"
    assert "Number of rounds must be between" in result


def test_div_instruction_completes_remaining_fields(monkeypatch, tmp_path):
    lib = load_worker()
    warrior = textwrap.dedent(
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
    ).strip() + "\n"
    opponent = "JMP.B $0, $0\n"
    trace_file = tmp_path / "div_trace.txt"
    monkeypatch.setenv("REDCODE_TRACE_FILE", str(trace_file))
    result = lib.run_battle(
        warrior.encode(), 1,
        opponent.encode(), 2,
        8000, 200, 8000, 8000, 8000, 100, 100, 1, -1,
        0,
    ).decode()
    trace_text = trace_file.read_text(encoding="utf-8")
    assert not result.startswith("ERROR:"), result
    assert "DIV.F" in trace_text
    assert "SNE.B #20, $-4" in trace_text


def test_jmn_djn_use_or_logic(monkeypatch, tmp_path):
    lib = load_worker()
    warrior = textwrap.dedent(
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
    ).strip() + "\n"
    opponent = "JMP.B $0, $0\n"
    trace_file = tmp_path / "jmn_djn_trace.txt"
    monkeypatch.setenv("REDCODE_TRACE_FILE", str(trace_file))
    result = lib.run_battle(
        warrior.encode(), 1,
        opponent.encode(), 2,
        8000, 200, 8000, 8000, 8000, 100, 100, 1, -1,
        0,
    ).decode()
    trace_text = trace_file.read_text(encoding="utf-8")
    assert not result.startswith("ERROR:"), result
    assert "JMN.I" in trace_text
    assert "DJN.I" in trace_text
    assert trace_text.count("MOV.B #1") >= 2
    assert "MOV.B #2" not in trace_text


def test_baseline_jmn_djn_flags_report_or_logic(monkeypatch, tmp_path):
    lib = load_worker()
    warrior = load_baseline_warrior("jmn_djn_assembled.txt")
    opponent = "JMP.B $0, $0\n"
    trace_file = tmp_path / "baseline_jmn_djn_trace.txt"
    monkeypatch.setenv("REDCODE_TRACE_FILE", str(trace_file))
    result = lib.run_battle(
        warrior.encode(), 1,
        opponent.encode(), 2,
        8000, 200, 8000, 8000, 8000, 100, 100, 1, -1,
        0,
    ).decode()
    trace_text = trace_file.read_text(encoding="utf-8")
    assert not result.startswith("ERROR:"), result
    assert trace_text.count("MOV.B #1, $6") >= 2
    assert "MOV.B #2" not in trace_text


def test_baseline_div_preserves_valid_field(monkeypatch, tmp_path):
    lib = load_worker()
    warrior = load_baseline_warrior("div_assembled.txt")
    opponent = "JMP.B $0, $0\n"
    trace_file = tmp_path / "baseline_div_trace.txt"
    monkeypatch.setenv("REDCODE_TRACE_FILE", str(trace_file))
    result = lib.run_battle(
        warrior.encode(), 1,
        opponent.encode(), 2,
        8000, 200, 8000, 8000, 8000, 100, 100, 1, -1,
        0,
    ).decode()
    trace_text = trace_file.read_text(encoding="utf-8")
    assert not result.startswith("ERROR:"), result
    assert "DIV.F" in trace_text
    assert "-> WRITE @11" not in trace_text


def test_immediate_source_populates_b_field():
    lib = load_worker()
    warrior = textwrap.dedent(
        """
        DIV.B #1, $5
        MOV.B $5, $6
        JMZ.B $2, $6
        DAT.F #0, #0
        JMP.B $-3, $0
        DAT.F #0, #3
        DAT.F #0, #0
        """
    ).strip() + "\n"
    opponent = "JMP.B $0, $0\n"
    result = lib.run_battle(
        warrior.encode(), 1,
        opponent.encode(), 2,
        8000, 50, 8000, 8000, 8000, 100, 100, 1, -1,
        0,
    ).decode()
    w1_score, w2_score = get_scores(result)
    assert w1_score == w2_score == 1, (
        "Immediate source operands should populate both fields; "
        f"expected a draw, got scores {w1_score}, {w2_score}"
    )


def test_division_uses_signed_operands():
    lib = load_worker()
    warrior = textwrap.dedent(
        """
        DIV.B #-1, $4
        JMZ.B $2, $3
        JMP.B $0, $0
        DAT.F #0, #0
        DAT.F #0, #5
        """
    ).strip() + "\n"
    opponent = "DAT.F #0, #0\n"
    result = lib.run_battle(
        warrior.encode(), 1,
        opponent.encode(), 2,
        8000, 100, 8000, 8000, 8000, 100, 100, 3, -1,
        0,
    ).decode()
    w1_score, w2_score = get_scores(result)
    assert w2_score == 0, (
        "Division by a negative operand should treat the divisor as signed; "
        f"expected the opponent to score 0, got {w2_score}"
    )
    assert w1_score > 0, (
        "Division by a negative operand should keep the executing warrior alive; "
        f"expected a positive score, got {w1_score}"
    )


def test_baseline_folding_matches_reference():
    offsets = parse_folding_offsets()
    expected_fold = [-1, 0, 1, 3999, 4000, -3999, -1, 0, 1, 3999, 4000, -3999, -1, 0, 1]
    assert offsets == [
        -8001,
        -8000,
        -7999,
        -4001,
        -4000,
        -3999,
        -1,
        0,
        1,
        3999,
        4000,
        4001,
        7999,
        8000,
        8001,
    ]
    core_size = 8000
    for original, expected in zip(offsets, expected_fold):
        folded = corenorm(original, core_size)
        assert folded == expected, f"Fold mismatch for {original}: got {folded}, expected {expected}"


def test_custom_read_limit_folds_offsets(monkeypatch, tmp_path):
    lib = load_worker()
    warrior = textwrap.dedent(
        """
        MOV.I $3, $-1
        MOV.I $4, $0
        JMP.B $-2, $0
        DAT.F #123, #456
        """
    ).strip() + "\n"
    opponent = "JMP.B $0, $0\n"
    trace_file = tmp_path / "fold_trace.txt"
    monkeypatch.setenv("REDCODE_TRACE_FILE", str(trace_file))
    result = lib.run_battle(
        warrior.encode(), 1,
        opponent.encode(), 2,
        80, 200, 80, 6, 6, 10, 10, 1, -1,
        0,
    ).decode()
    assert not result.startswith("ERROR:"), result
    trace_text = trace_file.read_text(encoding="utf-8")
    assert "DAT.F #123, #456" in trace_text


def test_mov_b_immediate_operand(monkeypatch, tmp_path):
    lib = load_worker()
    warrior = "MOV.B #123, @-1\nJMP.B $-2, $0\n"
    opponent = "JMP.B $0, $0\n"
    trace_file = tmp_path / "mov_immediate_trace.txt"
    monkeypatch.setenv("REDCODE_TRACE_FILE", str(trace_file))
    result = lib.run_battle(
        warrior.encode(), 1,
        opponent.encode(), 2,
        80, 200, 80, 6, 6, 10, 10, 1, 23,
        0,
    ).decode()
    assert not result.startswith("ERROR:"), result
    trace_text = trace_file.read_text(encoding="utf-8")
    assert "MOV.B #123, @-1" in trace_text
    assert "DAT.F $0, $-1" in trace_text


def test_cmp_immediate_b_operand_uses_literal():
    lib = load_worker()
    warrior = "CMP.I #5,#5\nDAT.F #0,#0\nJMP.B $0,$0\n"
    opponent = "DAT.F #0,#0\n"
    result = lib.run_battle(
        warrior.encode(), 1,
        opponent.encode(), 2,
        80, 200, 80, 6, 6, 10, 10, 1, 37,
        0,
    ).decode()
    scores = get_scores(result)
    assert scores[0] > scores[1], result


def test_fold_negative_boundary(monkeypatch, tmp_path):
    lib = load_worker()
    warrior = textwrap.dedent(
        """
        JMP.B $3, $0
        DAT.F #111, #222
        DAT.F #333, #444
        MOV.I $4, $0
        MOV.I $-3, $0
        SPL.B $-2, $0
        JMP.B $-2, $0
        DAT.F #777, #888
        DAT.F #999, #111
        DAT.F #555, #666
        """
    ).strip() + "\n"
    opponent = "JMP.B $0, $0\n"
    trace_file = tmp_path / "fold_boundary_trace.txt"
    monkeypatch.setenv("REDCODE_TRACE_FILE", str(trace_file))
    result = lib.run_battle(
        warrior.encode(), 1,
        opponent.encode(), 2,
        80, 200, 80, 6, 6, 12, 12, 1, 29,
        0,
    ).decode()
    assert not result.startswith("ERROR:"), result
    trace_text = trace_file.read_text(encoding="utf-8")
    assert "WRITE @3 {DAT.F #111, #222}" in trace_text
    assert "WRITE @4 {DAT.F #777, #888}" in trace_text


def test_warrior_exceeding_dynamic_length_is_rejected():
    lib = load_worker()
    warrior = ("JMP.B $0, $0\n" * 5).encode()
    result = lib.run_battle(
        warrior, 1,
        warrior, 2,
        80, 200, 80, 80, 80, 3, 3, 1, -1,
        0,
    ).decode()
    assert result.startswith("ERROR:"), result
    assert "exceeds the configured maximum" in result
