import pathlib
import random
import re
import sys

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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

    sequence = [25, champion, champion + 1]

    def fake_randint(a: int, b: int) -> int:
        calls.append((a, b))
        return sequence.pop(0)

    engine.configure_rng(fake_randint, lambda seq: seq[0])

    result = engine.select_opponents(
        num_warriors=5, champion=champion, champion_battle_chance=50
    )

    assert result == (champion, champion + 1)
    assert calls == [(1, 100), (1, 5), (1, 5)]


def test_select_opponents_without_champion_draws_distinct_contestants():
    champion = 2
    calls: list[tuple[int, int]] = []
    sequence = [90, 3, 3, 1]

    def fake_randint(a: int, b: int) -> int:
        calls.append((a, b))
        return sequence.pop(0)

    engine.configure_rng(fake_randint, lambda seq: seq[0])

    result = engine.select_opponents(
        num_warriors=4, champion=champion, champion_battle_chance=50
    )

    assert result == (3, 1)
    assert champion not in result
    assert calls == [(1, 100), (1, 4), (1, 4), (1, 4)]


def test_select_opponents_respects_zero_percent_champion_chance():
    champion = 3
    calls: list[tuple[int, int]] = []
    sequence = [1, 2]

    def fake_randint(a: int, b: int) -> int:
        calls.append((a, b))
        return sequence.pop(0)

    engine.configure_rng(fake_randint, lambda seq: seq[0])

    result = engine.select_opponents(
        num_warriors=5, champion=champion, champion_battle_chance=0
    )

    assert result == (1, 2)
    assert calls == [(1, 5), (1, 5)]
    assert champion not in result


def test_select_opponents_uses_champion_when_chance_is_certain():
    champion = 4
    calls: list[tuple[int, int]] = []
    sequence = [42, champion, champion + 2]

    def fake_randint(a: int, b: int) -> int:
        calls.append((a, b))
        return sequence.pop(0)

    engine.configure_rng(fake_randint, lambda seq: seq[0])

    result = engine.select_opponents(
        num_warriors=6, champion=champion, champion_battle_chance=100
    )

    assert result == (champion, champion + 2)
    assert calls == [(1, 100), (1, 6), (1, 6)]



def test_determine_winner_and_loser_requires_two_scores():
    with pytest.raises(ValueError, match="Expected scores for two warriors"):
        engine.determine_winner_and_loser([1], [10])


def test_handle_archiving_uses_disk_storage(tmp_path):
    config = evolverstage.EvolverConfig(
        battle_engine="internal",
        last_arena=0,
        base_path=str(tmp_path),
        archive_path=str(tmp_path / "archive"),
        coresize_list=[8000],
        sanitize_list=[0],
        cycles_list=[80000],
        processes_list=[8000],
        readlimit_list=[8000],
        writelimit_list=[8000],
        warlen_list=[3],
        wardistance_list=[0],
        arena_spec_list=[engine.SPEC_1994],
        arena_weight_list=[1],
        numwarriors=2,
        alreadyseeded=False,
        use_in_memory_arenas=True,
        arena_checkpoint_interval=10000,
        clock_time=0.0,
        battle_log_file=None,
        final_era_only=False,
        nothing_list=[0],
        random_list=[0],
        nab_list=[0],
        mini_mut_list=[0],
        micro_mut_list=[0],
        library_list=[0],
        magic_number_list=[0],
        archive_list=[1],
        unarchive_list=[0],
        library_path=None,
        crossoverrate_list=[1],
        transpositionrate_list=[1],
        battlerounds_list=[1],
        prefer_winner_list=[False],
        champion_battle_chance_list=[50],
        instr_set=["MOV"],
        instr_modes=[],
        instr_modif=[],
        run_final_tournament=False,
        final_tournament_csv=None,
        benchmark_root=None,
        benchmark_final_tournament=False,
        benchmark_battle_frequency_list=[0],
    )

    previous_config = getattr(engine, "_active_config")
    previous_arena_storage = engine._ARENA_STORAGE
    previous_archive_storage = engine._ARCHIVE_STORAGE

    try:
        engine.set_engine_config(config)
        arena_storage = engine.InMemoryArenaStorage()
        engine.set_arena_storage(arena_storage)
        arena_storage.set_warrior_lines(0, 1, ["MOV 0, 0\n"])

        archive_storage = engine.DiskArchiveStorage(config.archive_path)
        archive_storage.initialize()
        engine.set_archive_storage(archive_storage)

        engine.configure_rng(lambda a, _b: a, lambda seq: seq[0])

        result = engine.handle_archiving(
            winner=1,
            loser=2,
            arena=0,
            era=0,
            config=config,
        )

        assert result.events and result.events[0].archive_filename is not None
        archived_file = tmp_path / "archive" / result.events[0].archive_filename
        assert archived_file.exists()
    finally:
        if previous_config is None:
            engine._active_config = None
        else:
            engine.set_engine_config(previous_config)
        engine._ARENA_STORAGE = previous_arena_storage
        engine._ARCHIVE_STORAGE = previous_archive_storage
