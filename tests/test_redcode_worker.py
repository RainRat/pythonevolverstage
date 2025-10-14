import os
import pathlib
import sys
import textwrap

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from test_support import load_worker


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
    with open(code_path, "r", encoding="utf-8") as f:
        code = f.read()
    rounds = 5
    result = lib.run_battle(
        code.encode(), 1,
        code.encode(), 2,
        8000, 10000, 8000, 8000, 8000, 100, 100, rounds, -1
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
        8000, 1000, 8000, 8000, 8000, 100, 100, 1, -1
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
        8000, 10, 8000, 8000, 8000, 1, 100, 1, -1
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
        8000, 10, 8000, 8000, 8000, 1, 100, 1, -1
    ).decode()
    assert result.startswith("ERROR:"), f"Expected ORG to be rejected, got: {result}"
    assert "Unsupported pseudo-opcode 'ORG'" in result


def test_battle_stops_once_outcome_decided():
    lib = load_worker()
    dominant_warrior = "JMP.B $0, $0\n"
    fragile_warrior = "DAT.F #0, #0\n"
    rounds = 100
    result = lib.run_battle(
        dominant_warrior.encode(), 1,
        fragile_warrior.encode(), 2,
        8000, 50, 8000, 8000, 8000, 1, 100, rounds, -1
    ).decode()
    w1_score, w2_score = get_scores(result)
    assert w2_score == 0, f"Expected fragile warrior to lose every round, got scores {w1_score}, {w2_score}"
    expected_rounds_played = (rounds // 2) + 1
    expected_score = expected_rounds_played * 3
    assert w1_score == expected_score, (
        "Battle should stop once the outcome is locked; "
        f"expected leader score {expected_score} for {expected_rounds_played} rounds, got {w1_score}"
    )


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
        8000, 200, 8000, 8000, 8000, 1, 100, 1, -1
    ).decode()
    trace_text = trace_file.read_text(encoding="utf-8")
    assert not result.startswith("ERROR:"), result
    assert "DIV.F" in trace_text
    assert "MOV.B #1, $-10" in trace_text


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
        8000, 200, 8000, 8000, 8000, 1, 100, 1, -1
    ).decode()
    trace_text = trace_file.read_text(encoding="utf-8")
    assert not result.startswith("ERROR:"), result
    assert "JMN.I" in trace_text
    assert "DJN.I" in trace_text
    assert trace_text.count("MOV.B #1") >= 2
    assert "MOV.B #2" not in trace_text


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
        80, 200, 80, 6, 6, 1, 10, 1, -1
    ).decode()
    assert not result.startswith("ERROR:"), result
    trace_text = trace_file.read_text(encoding="utf-8")
    assert "DAT.F #123, #456" in trace_text


def test_mov_b_immediate_operand(monkeypatch, tmp_path):
    lib = load_worker()
    warrior = "MOV.B #123, @-1\nDAT.F #0, #0\n"
    opponent = "DAT.F #0, #0\n"
    trace_file = tmp_path / "mov_immediate_trace.txt"
    monkeypatch.setenv("REDCODE_TRACE_FILE", str(trace_file))
    result = lib.run_battle(
        warrior.encode(), 1,
        opponent.encode(), 2,
        80, 200, 80, 6, 6, 1, 10, 1, 23
    ).decode()
    assert not result.startswith("ERROR:"), result
    trace_text = trace_file.read_text(encoding="utf-8")
    assert "DAT.F #0, #-2" in trace_text


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
        80, 200, 80, 6, 6, 1, 12, 1, 29
    ).decode()
    assert not result.startswith("ERROR:"), result
    trace_text = trace_file.read_text(encoding="utf-8")
    assert trace_text.count("DAT.F #111, #222") >= 2
    assert "DAT.F #777, #888" not in trace_text


def test_warrior_exceeding_dynamic_length_is_rejected():
    lib = load_worker()
    warrior = ("JMP.B $0, $0\n" * 5).encode()
    result = lib.run_battle(
        warrior, 1,
        warrior, 2,
        80, 200, 80, 80, 80, 1, 3, 1, -1
    ).decode()
    assert result.startswith("ERROR:"), result
    assert "exceeds the configured maximum" in result
