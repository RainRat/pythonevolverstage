import random
import re

import pytest

import engine
import evolverstage


@pytest.fixture(autouse=True)
def restore_engine_rng():
    yield
    engine.configure_rng(random.randint, random.choice)


def test_safe_int_trims_whitespace():
    assert engine._safe_int(" 42 ") == 42


def test_safe_int_rejects_invalid_literal():
    with pytest.raises(ValueError, match="Invalid integer literal"):
        engine._safe_int("abc")


@pytest.mark.parametrize(
    "operand, operand_name, pattern",
    [
        ("", "A", "Missing A-field operand"),
        ("1", "B", re.escape("Missing addressing mode for B-field operand '1'")),
        ("$ ", "A", "Missing value for A-field operand"),
        (
            "$abc",
            "B",
            re.escape("Invalid B-field operand '$abc': Invalid integer literal: 'abc'"),
        ),
    ],
)
def test_parse_operand_rejects_invalid_inputs(operand, operand_name, pattern):
    with pytest.raises(ValueError, match=pattern):
        engine._parse_operand(operand, operand_name)


def test_parse_operand_parses_valid_operand():
    mode, value = engine._parse_operand("#-10", "A")
    assert mode == "#"
    assert value == -10


def test_weighted_random_number_prefers_length_range():
    calls: list[tuple[int, int]] = []

    def fake_randint(a: int, b: int) -> int:
        calls.append((a, b))
        if len(calls) == 1:
            return 2
        return b

    engine.configure_rng(fake_randint, lambda seq: seq[0])

    result = engine.weighted_random_number(size=10, length=3)

    assert result == 3
    assert calls == [(1, 4), (-3, 3)]


def test_weighted_random_number_uses_size_range_when_selected():
    calls: list[tuple[int, int]] = []

    def fake_randint(a: int, b: int) -> int:
        calls.append((a, b))
        if len(calls) == 1:
            return 1
        return a

    engine.configure_rng(fake_randint, lambda seq: seq[0])

    result = engine.weighted_random_number(size=10, length=3)

    assert result == -10
    assert calls == [(1, 4), (-10, 10)]


def test_coremod_rejects_zero_modulus():
    with pytest.raises(ValueError, match="Modulus cannot be zero"):
        engine.coremod(5, 0)


def test_corenorm_wraps_values_greater_than_half_modulus():
    assert engine.corenorm(6, 10) == -4
    assert engine.corenorm(-6, 10) == 4
    assert engine.corenorm(5, 10) == 5


def test_determine_winner_and_loser_handles_draw(monkeypatch):
    monkeypatch.setattr(evolverstage, "get_random_int", lambda _a, _b: 1)

    winner, loser, was_draw = engine.determine_winner_and_loser([1, 2], [5, 5])

    assert was_draw is True
    assert winner == 2
    assert loser == 1


def test_determine_winner_and_loser_prefers_higher_score():
    winner, loser, was_draw = engine.determine_winner_and_loser([1, 2], [3, 7])

    assert was_draw is False
    assert winner == 2
    assert loser == 1


def test_select_opponents_prefers_champion_when_rng_allows():
    champion = 2
    calls: list[tuple[int, int]] = []

    sequence = [0, champion, champion + 1]

    def fake_randint(a: int, b: int) -> int:
        calls.append((a, b))
        return sequence.pop(0)

    engine.configure_rng(fake_randint, lambda seq: seq[0])

    result = engine.select_opponents(num_warriors=5, champion=champion)

    assert result == (champion, champion + 1)
    assert calls == [(0, 1), (1, 5), (1, 5)]


def test_select_opponents_without_champion_draws_distinct_contestants():
    champion = 2
    calls: list[tuple[int, int]] = []
    sequence = [1, 3, 3, 1]

    def fake_randint(a: int, b: int) -> int:
        calls.append((a, b))
        return sequence.pop(0)

    engine.configure_rng(fake_randint, lambda seq: seq[0])

    result = engine.select_opponents(num_warriors=4, champion=champion)

    assert result == (3, 1)
    assert champion not in result
    assert calls == [(0, 1), (1, 4), (1, 4), (1, 4)]


def test_determine_winner_and_loser_requires_two_scores():
    with pytest.raises(ValueError, match="Expected scores for two warriors"):
        engine.determine_winner_and_loser([1], [10])
