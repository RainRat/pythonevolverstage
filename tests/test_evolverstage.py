import configparser
import importlib
import io
import os
import pathlib
import re
import sys
import textwrap
import types
from dataclasses import replace
from typing import Optional

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONEVOLVER_SKIP_MAIN", "1")

from test_support import compile_worker

import engine
import evolverstage

DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "settings.ini"
_DEFAULT_CONFIG = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
evolverstage.set_active_config(_DEFAULT_CONFIG)
evolverstage.set_arena_storage(evolverstage.create_arena_storage(_DEFAULT_CONFIG))


@pytest.fixture
def write_config(tmp_path):
    def _write_config(body: str, *, filename: str = "config.ini") -> pathlib.Path:
        config_path = tmp_path / filename
        if "[DEFAULT]" not in body:
            body = "[DEFAULT]\n" + body
        config_path.write_text(textwrap.dedent(body).strip())
        return config_path

    return _write_config


def test_load_configuration_parses_types(tmp_path, write_config):
    config_path = write_config(
        """
        BATTLE_ENGINE = internal
        LAST_ARENA = 1
        CORESIZE_LIST = 8000, 8192
        SANITIZE_LIST = 80, 81
        CYCLES_LIST = 1000, 2000
        PROCESSES_LIST = 8, 16
        WARLEN_LIST = 20, 40
        WARDISTANCE_LIST = 20, 40
        ARENA_WEIGHT_LIST = 1, 3
        NUMWARRIORS = 50
        CLOCK_TIME = 12.5
        BATTLE_LOG_FILE = logs.csv
        BENCHMARK_LOG_FILE = benchmark.csv
        BENCHMARK_LOG_GENERATION_INTERVAL = 5000
        FINAL_ERA_ONLY = false
        NOTHING_LIST = 1,2
        RANDOM_LIST = 4,5
        NAB_LIST = 6,7
        MINI_MUT_LIST = 8,9
        MICRO_MUT_LIST = 10,11
        LIBRARY_LIST = 12, 13
        MAGIC_NUMBER_LIST = 14, 15
        ARCHIVE_LIST = 16,17
        UNARCHIVE_LIST = 18,19
        LIBRARY_PATH = ./library
        CROSSOVERRATE_LIST = 20,21
        TRANSPOSITIONRATE_LIST = 22,23
        BATTLEROUNDS_LIST = 24, 48
        PREFER_WINNER_LIST = true, false
        CHAMPION_BATTLE_FREQUENCY_LIST = 5, 3
        RANDOM_PAIR_BATTLE_FREQUENCY_LIST = 7, 9
        INSTR_SET = MOV, ADD
        INSTR_MODES = #, $
        INSTR_MODIF = A, B
        BENCHMARK_BATTLE_FREQUENCY_LIST = 7, 11
        """
    )

    from evolverstage import load_configuration

    config = load_configuration(str(config_path))
    assert config.battle_engine == "internal"
    assert config.last_arena == 1
    assert config.coresize_list == [8000, 8192]
    assert config.sanitize_list == [80, 81]
    assert config.cycles_list == [1000, 2000]
    assert config.processes_list == [8, 16]
    assert config.warlen_list == [20, 40]
    assert config.wardistance_list == [20, 40]
    assert config.arena_weight_list == [1, 3]
    assert config.numwarriors == 50
    assert config.alreadyseeded is False
    assert pytest.approx(config.clock_time, rel=1e-6) == 12.5
    assert config.base_path == str(config_path.parent)
    assert config.archive_path == os.path.abspath(config_path.parent / "archive")
    assert config.battle_log_file == os.path.abspath(config_path.with_name("logs.csv"))
    assert config.benchmark_log_file == os.path.abspath(
        config_path.with_name("benchmark.csv")
    )
    assert config.benchmark_log_generation_interval == 5000
    assert config.final_era_only is False
    assert config.final_tournament_only is False
    assert config.nothing_list == [1, 2]
    assert config.random_list == [4, 5]
    assert config.nab_list == [6, 7]
    assert config.mini_mut_list == [8, 9]
    assert config.micro_mut_list == [10, 11]
    assert config.library_list == [12, 13]
    assert config.magic_number_list == [14, 15]
    assert config.archive_list == [16, 17]
    assert config.unarchive_list == [18, 19]
    assert config.library_path == os.path.abspath(config_path.with_name("library"))
    assert config.crossoverrate_list == [20, 21]
    assert config.transpositionrate_list == [22, 23]
    assert config.battlerounds_list == [24, 48]
    assert config.prefer_winner_list == [True, False]
    assert config.champion_battle_frequency_list == [5, 3]
    assert config.random_pair_battle_frequency_list == [7, 9]
    assert config.instr_set == ["MOV", "ADD"]
    assert config.instr_modes == ["#", "$"]
    assert config.instr_modif == ["A", "B"]
    assert config.benchmark_root is None
    assert config.benchmark_final_tournament is False
    assert config.benchmark_battle_frequency_list == [7, 11]
    assert config.benchmark_sets == {}


def test_load_configuration_accepts_custom_archive_path(tmp_path, write_config):
    shared_root = tmp_path / "shared"
    shared_root.mkdir()

    config_path = write_config(
        """
        BATTLE_ENGINE = internal
        LAST_ARENA = 0
        CORESIZE_LIST = 80
        SANITIZE_LIST = 80
        CYCLES_LIST = 800
        PROCESSES_LIST = 8
        WARLEN_LIST = 5
        WARDISTANCE_LIST = 5
        NUMWARRIORS = 2
        CLOCK_TIME = 1
        BATTLEROUNDS_LIST = 1
        NOTHING_LIST = 1
        RANDOM_LIST = 0
        NAB_LIST = 0
        MINI_MUT_LIST = 0
        MICRO_MUT_LIST = 0
        LIBRARY_LIST = 0
        MAGIC_NUMBER_LIST = 0
        ARCHIVE_LIST = 0
        UNARCHIVE_LIST = 0
        CROSSOVERRATE_LIST = 1
        TRANSPOSITIONRATE_LIST = 1
        PREFER_WINNER_LIST = false
        ARCHIVE_PATH = shared/archive
        """
    )

    config = evolverstage.load_configuration(str(config_path))
    expected_path = os.path.abspath(config_path.parent / "shared" / "archive")
    assert config.archive_path == expected_path


def test_load_configuration_defaults_archive_lists(tmp_path, write_config):
    config_path = write_config(
        """
        BATTLE_ENGINE = internal
        LAST_ARENA = 1
        CORESIZE_LIST = 8000, 8192
        SANITIZE_LIST = 80, 81
        CYCLES_LIST = 1000, 2000
        PROCESSES_LIST = 8, 16
        WARLEN_LIST = 20, 40
        WARDISTANCE_LIST = 25, 45
        ARENA_WEIGHT_LIST = 1, 1
        NUMWARRIORS = 4
        CLOCK_TIME = 1
        NOTHING_LIST = 1,2
        RANDOM_LIST = 3,4
        NAB_LIST = 5,6
        MINI_MUT_LIST = 7,8
        MICRO_MUT_LIST = 9,10
        LIBRARY_LIST = 11,12
        MAGIC_NUMBER_LIST = 13,14
        CROSSOVERRATE_LIST = 15,16
        TRANSPOSITIONRATE_LIST = 17,18
        BATTLEROUNDS_LIST = 19, 20
        PREFER_WINNER_LIST = true, false
        BENCHMARK_BATTLE_FREQUENCY = 0
        """
    )

    config = evolverstage.load_configuration(str(config_path))
    assert config.archive_list == [0, 0]
    assert config.unarchive_list == [0, 0]


def test_load_configuration_with_benchmarks(tmp_path, write_config):
    benchmark_root = tmp_path / "benchmarks" / "arena0"
    benchmark_root.mkdir(parents=True)
    (benchmark_root / "alpha.red").write_text("MOV 0, 0\n")

    config_path = write_config(
        """
        BATTLE_ENGINE = internal
        LAST_ARENA = 0
        CORESIZE_LIST = 8000
        SANITIZE_LIST = 8000
        CYCLES_LIST = 80000
        PROCESSES_LIST = 8
        WARLEN_LIST = 100
        WARDISTANCE_LIST = 100
        NUMWARRIORS = 10
        CLOCK_TIME = 1.0
        NOTHING_LIST = 1
        RANDOM_LIST = 1
        NAB_LIST = 0
        MINI_MUT_LIST = 0
        MICRO_MUT_LIST = 0
        LIBRARY_LIST = 0
        MAGIC_NUMBER_LIST = 0
        ARCHIVE_LIST = 0
        UNARCHIVE_LIST = 0
        CROSSOVERRATE_LIST = 1
        TRANSPOSITIONRATE_LIST = 1
        BATTLEROUNDS_LIST = 5
        PREFER_WINNER_LIST = true
        INSTR_SET = MOV
        INSTR_MODES = $
        INSTR_MODIF = F
        RUN_FINAL_TOURNAMENT = true
        BENCHMARK_ROOT = benchmarks
        BENCHMARK_FINAL_TOURNAMENT = true
        """
    )

    config = evolverstage.load_configuration(str(config_path))
    expected_root = str((tmp_path / "benchmarks").resolve())
    assert config.benchmark_root == expected_root
    assert config.benchmark_final_tournament is True
    assert config.benchmark_battle_frequency_list == [0]
    assert config.benchmark_log_file is None
    assert config.benchmark_log_generation_interval == 0
    assert 0 in config.benchmark_sets
    assert len(config.benchmark_sets[0]) == 1
    benchmark = config.benchmark_sets[0][0]
    assert benchmark.name == "alpha"
    assert benchmark.code.strip() == "MOV 0, 0"
    assert benchmark.path == str((benchmark_root / "alpha.red").resolve())


def test_boolean_parser_respects_explicit_values():
    parser = configparser.ConfigParser()
    parser.read_dict({"DEFAULT": {"FINAL_ERA_ONLY": "True"}})

    bool_parser = evolverstage._CONFIG_PARSERS["bool"]
    assert bool_parser("False", key="FINAL_ERA_ONLY", parser=parser) is False


def test_main_runs_final_tournament_only_mode(monkeypatch, tmp_path):
    config = replace(
        _DEFAULT_CONFIG,
        base_path=str(tmp_path),
        archive_path=str(tmp_path / "archive"),
        last_arena=0,
        numwarriors=2,
        final_tournament_only=True,
        run_final_tournament=False,
        battle_log_file=None,
        benchmark_log_file=None,
    )

    arena_dir = tmp_path / "arena0"
    archive_dir = tmp_path / "archive"
    arena_dir.mkdir()
    archive_dir.mkdir()
    warrior_path = arena_dir / "1.red"
    warrior_path.write_text("MOV 0, 0\n", encoding="utf-8")
    (arena_dir / "2.red").write_text("MOV 1, 1\n", encoding="utf-8")

    monkeypatch.setattr(evolverstage, "load_configuration", lambda _: config)
    monkeypatch.setattr(evolverstage, "set_console_verbosity", lambda verbosity: verbosity)
    monkeypatch.setattr(evolverstage, "console_log", lambda *args, **kwargs: None)

    final_tournament_calls: list[evolverstage.EvolverConfig] = []

    def record_final_tournament(active_config):
        final_tournament_calls.append(active_config)

    monkeypatch.setattr(evolverstage, "run_final_tournament", record_final_tournament)

    try:
        previous_config = evolverstage.get_active_config()
    except RuntimeError:
        previous_config = None

    try:
        previous_storage = evolverstage.get_arena_storage()
    except RuntimeError:
        previous_storage = None

    try:
        result = evolverstage._main_impl(["--config", str(tmp_path / "config.ini")])
        assert result == 0
        assert final_tournament_calls == [config]
        assert warrior_path.read_text(encoding="utf-8") == "MOV 0, 0\n"
    finally:
        if previous_config is not None:
            evolverstage.set_active_config(previous_config)
        else:
            evolverstage.set_active_config(_DEFAULT_CONFIG)
        if previous_storage is not None:
            evolverstage.set_arena_storage(previous_storage)
        else:
            evolverstage.set_arena_storage(
                evolverstage.create_arena_storage(_DEFAULT_CONFIG)
            )

def test_run_benchmark_battle_aggregates_scores(monkeypatch, tmp_path, write_config):
    benchmark_root = tmp_path / "benchmarks" / "arena0"
    benchmark_root.mkdir(parents=True)
    (benchmark_root / "alpha.red").write_text("MOV 0, 0\n", encoding="utf-8")

    config_path = write_config(
        """
        BATTLE_ENGINE = internal
        LAST_ARENA = 0
        NUMWARRIORS = 2
        CLOCK_TIME = 1
        CORESIZE_LIST = 80
        SANITIZE_LIST = 80
        CYCLES_LIST = 800
        PROCESSES_LIST = 8
        READLIMIT_LIST = 80
        WRITELIMIT_LIST = 80
        WARLEN_LIST = 5
        WARDISTANCE_LIST = 5
        BATTLEROUNDS_LIST = 1
        NOTHING_LIST = 1
        RANDOM_LIST = 0
        NAB_LIST = 0
        MINI_MUT_LIST = 0
        MICRO_MUT_LIST = 0
        LIBRARY_LIST = 0
        MAGIC_NUMBER_LIST = 0
        ARCHIVE_LIST = 0
        UNARCHIVE_LIST = 0
        CROSSOVERRATE_LIST = 1
        TRANSPOSITIONRATE_LIST = 1
        PREFER_WINNER_LIST = false
        INSTR_SET = MOV
        INSTR_MODES = $
        INSTR_MODIF = F
        BENCHMARK_ROOT = benchmarks
        BENCHMARK_BATTLE_FREQUENCY_LIST = 1
        """
    )

    config = evolverstage.load_configuration(str(config_path))
    arena_dir = pathlib.Path(config.base_path) / "arena0"
    arena_dir.mkdir(parents=True, exist_ok=True)

    try:
        previous_config = evolverstage.get_active_config()
    except RuntimeError:
        previous_config = None
    try:
        previous_storage = evolverstage.get_arena_storage()
    except RuntimeError:
        previous_storage = None

    storage = evolverstage.create_arena_storage(config)
    evolverstage.set_active_config(config)
    evolverstage.set_arena_storage(storage)
    storage.load_existing()
    storage.set_warrior_lines(0, 1, ["MOV 0, 0\n"])
    storage.set_warrior_lines(0, 2, ["DAT 0, 0\n"])

    def fake_execute_battle_with_sources(
        arena,
        cont1,
        cont1_code,
        cont2,
        cont2_code,
        era,
        verbose=False,
        battlerounds_override=None,
        seed=None,
    ):
        warrior_score = 10 if cont1 == 1 else 4
        return [cont1, cont2], [warrior_score, 0]

    monkeypatch.setattr(
        evolverstage, "execute_battle_with_sources", fake_execute_battle_with_sources
    )

    try:
        result = evolverstage._run_benchmark_battle(0, 1, 2, 0, config)
        assert result is not None
        assert result.warriors == [1, 2]
        assert result.scores == [10, 4]
        assert result.benchmarks_played == 1
    finally:
        if previous_config is not None:
            evolverstage.set_active_config(previous_config)
        if previous_storage is not None:
            evolverstage.set_arena_storage(previous_storage)


def test_final_tournament_with_benchmarks(monkeypatch, tmp_path, write_config):
    base_dir = tmp_path
    arena_dir = base_dir / "arena0"
    archive_dir = base_dir / "archive"
    arena_dir.mkdir()
    archive_dir.mkdir()
    (arena_dir / "1.red").write_text("MOV 0, 1\n")
    (arena_dir / "2.red").write_text("MOV 0, 1\n")

    benchmark_dir = base_dir / "benchmarks" / "arena0"
    benchmark_dir.mkdir(parents=True)
    (benchmark_dir / "bench.red").write_text("MOV 0, 0\n")

    config_path = write_config(
        """
        BATTLE_ENGINE = internal
        LAST_ARENA = 0
        CORESIZE_LIST = 8000
        SANITIZE_LIST = 8000
        CYCLES_LIST = 80000
        PROCESSES_LIST = 8
        WARLEN_LIST = 100
        WARDISTANCE_LIST = 100
        NUMWARRIORS = 2
        IN_MEMORY_ARENAS = false
        ARENA_CHECKPOINT_INTERVAL = 1000
        CLOCK_TIME = 1.0
        NOTHING_LIST = 1
        RANDOM_LIST = 1
        NAB_LIST = 0
        MINI_MUT_LIST = 0
        MICRO_MUT_LIST = 0
        LIBRARY_LIST = 0
        MAGIC_NUMBER_LIST = 0
        ARCHIVE_LIST = 0
        UNARCHIVE_LIST = 0
        CROSSOVERRATE_LIST = 1
        TRANSPOSITIONRATE_LIST = 1
        BATTLEROUNDS_LIST = 3
        PREFER_WINNER_LIST = true
        INSTR_SET = MOV
        INSTR_MODES = $
        INSTR_MODIF = F
        RUN_FINAL_TOURNAMENT = true
        BENCHMARK_ROOT = benchmarks
        BENCHMARK_FINAL_TOURNAMENT = true
        """
    )

    config = evolverstage.load_configuration(str(config_path))
    evolverstage.set_active_config(config)
    storage = evolverstage.create_arena_storage(config)
    evolverstage.set_arena_storage(storage)

    call_records: list[tuple[int, int, int, str, str, Optional[int]]] = []

    def fake_execute_battle_with_sources(
        arena,
        cont1,
        cont1_code,
        cont2,
        cont2_code,
        era,
        verbose=False,
        battlerounds_override=None,
        seed=None,
    ):
        call_records.append(
            (arena, cont1, cont2, cont1_code.strip(), cont2_code.strip(), seed)
        )
        if cont1 == 1:
            return [cont1, cont2], [15, -15]
        return [cont1, cont2], [5, -5]

    def unexpected_execute_battle(*_args, **_kwargs):
        raise AssertionError("execute_battle should not be used when benchmarks are available")

    captured: dict[str, object] = {}

    def fake_report(arena_summaries, warrior_scores):
        captured["arena_summaries"] = list(arena_summaries)
        captured["warrior_scores"] = {
            key: list(value) for key, value in warrior_scores.items()
        }

    monkeypatch.setattr(evolverstage, "execute_battle_with_sources", fake_execute_battle_with_sources)
    monkeypatch.setattr(evolverstage, "execute_battle", unexpected_execute_battle)
    monkeypatch.setattr(evolverstage, "console_update_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(evolverstage, "console_clear_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(evolverstage, "console_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(evolverstage, "_report_final_tournament_statistics", fake_report)
    monkeypatch.setattr(evolverstage, "_export_final_tournament_results", lambda *args, **kwargs: None)

    evolverstage.run_final_tournament(config)

    assert len(call_records) == 2
    for record in call_records:
        assert record[5] is not None

    bench_id = max(
        1,
        evolverstage._BENCHMARK_WARRIOR_ID_BASE - (0 * 1000 + 0),
    )
    expected_seed_w1 = evolverstage._stable_internal_battle_seed(0, 1, bench_id, 0)
    expected_seed_w2 = evolverstage._stable_internal_battle_seed(0, 2, bench_id, 0)
    assert {rec[5] for rec in call_records} == {expected_seed_w1, expected_seed_w2}
    assert {rec[2] for rec in call_records} == {bench_id}

    arena_summaries = captured.get("arena_summaries")
    assert arena_summaries is not None
    summary = arena_summaries[0]
    rankings = summary["rankings"]
    assert rankings[0][0] == 1
    assert rankings[0][1] == 15
    assert rankings[1][0] == 2
    benchmark_info = summary["benchmark"]
    assert benchmark_info[0]["name"] == "bench"
    assert pytest.approx(benchmark_info[0]["average"], rel=1e-6) == -10.0
    assert benchmark_info[0]["matches"] == 2

    warrior_scores = captured.get("warrior_scores")
    assert warrior_scores == {1: [15], 2: [5]}


def test_set_console_verbosity_falls_back_on_curses_error(monkeypatch):
    fake_curses = types.ModuleType("curses")

    class FakeCursesError(Exception):
        pass

    fake_curses.error = FakeCursesError

    def failing_initscr():
        raise FakeCursesError("boom")

    fake_curses.initscr = failing_initscr
    fake_curses.noecho = lambda: None
    fake_curses.cbreak = lambda: None
    fake_curses.nocbreak = lambda: None
    fake_curses.echo = lambda: None
    fake_curses.endwin = lambda: None

    monkeypatch.setitem(sys.modules, "curses", fake_curses)

    with pytest.warns(RuntimeWarning):
        level = evolverstage.set_console_verbosity(
            evolverstage.VerbosityLevel.PSEUDO_GRAPHICAL
        )

    try:
        assert level == evolverstage.VerbosityLevel.DEFAULT
        assert isinstance(evolverstage.get_console(), evolverstage.SimpleConsole)
    finally:
        evolverstage.set_console_verbosity(evolverstage.VerbosityLevel.DEFAULT)


def test_pseudo_graphical_console_close_restores_terminal_on_refresh_error(monkeypatch):
    fake_curses = types.ModuleType("curses")
    state = {"noecho": 0, "cbreak": 0, "nocbreak": 0, "echo": 0, "endwin": 0}

    def record_call(key):
        def _record():
            state[key] += 1

        return _record

    fake_curses.noecho = record_call("noecho")
    fake_curses.cbreak = record_call("cbreak")
    fake_curses.nocbreak = record_call("nocbreak")
    fake_curses.echo = record_call("echo")
    fake_curses.endwin = record_call("endwin")

    class FakeScreen:
        def __init__(self) -> None:
            self.keypad_calls: list[bool] = []

        def getmaxyx(self):
            return (24, 80)

        def erase(self):
            return None

        def addnstr(self, *_args, **_kwargs):
            return None

        def refresh(self):
            return None

        def keypad(self, flag: bool):
            self.keypad_calls.append(flag)

    fake_curses_screen = FakeScreen()

    def initscr():
        return fake_curses_screen

    fake_curses.initscr = initscr
    fake_curses.error = Exception

    monkeypatch.setitem(sys.modules, "curses", fake_curses)

    console = evolverstage.PseudoGraphicalConsole()
    assert fake_curses_screen.keypad_calls == [True]

    def fail_refresh():
        raise RuntimeError("refresh failed")

    console._refresh = fail_refresh

    with pytest.raises(RuntimeError):
        console.close()

    assert state["nocbreak"] == 1
    assert state["echo"] == 1
    assert state["endwin"] == 1
    assert fake_curses_screen.keypad_calls[-1] is False


def test_status_display_skips_duplicate_updates(monkeypatch):
    status = evolverstage.StatusDisplay()
    output = io.StringIO()

    monkeypatch.setattr(status, "_stream", lambda: output)
    monkeypatch.setattr(evolverstage.time, "monotonic", lambda: 0.0)

    status.update("progress", "detail")
    first_output = output.getvalue()

    status.update("progress", "detail")

    assert output.getvalue() == first_output


def test_get_progress_status_clamps_percent_complete(monkeypatch):
    start_time = 1000.0
    monkeypatch.setattr(evolverstage.time, "time", lambda: start_time + 7200.0)

    progress_line, detail_line = evolverstage._get_progress_status(
        start_time, total_duration_hr=1.0, current_era=0
    )

    assert "100.00% complete" in progress_line
    assert detail_line == "Era 1"


def test_load_configuration_reads_in_memory_settings(tmp_path, write_config):
    config_path = write_config(
        """
        BATTLE_ENGINE = internal
        LAST_ARENA = 0
        CORESIZE_LIST = 80
        SANITIZE_LIST = 80
        CYCLES_LIST = 800
        PROCESSES_LIST = 8
        READLIMIT_LIST = 80
        WRITELIMIT_LIST = 80
        WARLEN_LIST = 5
        WARDISTANCE_LIST = 5
        NUMWARRIORS = 2
        CLOCK_TIME = 1
        BATTLEROUNDS_LIST = 1
        NOTHING_LIST = 1
        RANDOM_LIST = 0
        NAB_LIST = 0
        MINI_MUT_LIST = 0
        MICRO_MUT_LIST = 0
        LIBRARY_LIST = 0
        MAGIC_NUMBER_LIST = 0
        ARCHIVE_LIST = 0
        UNARCHIVE_LIST = 0
        CROSSOVERRATE_LIST = 1
        TRANSPOSITIONRATE_LIST = 1
        PREFER_WINNER_LIST = false
        IN_MEMORY_ARENAS = true
        ARENA_CHECKPOINT_INTERVAL = 20000
        """
    )

    (tmp_path / "arena0").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "arena0" / "1.red").write_text("DAT.F #0, #0\n", encoding="utf-8")
    (tmp_path / "arena0" / "2.red").write_text("DAT.F #0, #0\n", encoding="utf-8")

    config = evolverstage.load_configuration(str(config_path))
    assert config.use_in_memory_arenas is True
    assert config.arena_checkpoint_interval == 20000


@pytest.mark.parametrize(
    "seed_existing, expected_seeded, expected_message",
    [
        (
            False,
            False,
            "Arenas will be freshly seeded because required warriors are missing.",
        ),
        (True, True, None),
    ],
)
def test_load_configuration_handles_missing_directories(
    tmp_path,
    capsys,
    write_config,
    seed_existing,
    expected_seeded,
    expected_message,
):
    config_path = write_config(
        """
        BATTLE_ENGINE = internal
        LAST_ARENA = 0
        CORESIZE_LIST = 80
        SANITIZE_LIST = 80
        CYCLES_LIST = 800
        PROCESSES_LIST = 8
        WARLEN_LIST = 5
        WARDISTANCE_LIST = 5
        NUMWARRIORS = 10
        CLOCK_TIME = 1
        BATTLEROUNDS_LIST = 1
        NOTHING_LIST = 1
        RANDOM_LIST = 1
        NAB_LIST = 0
        MINI_MUT_LIST = 0
        MICRO_MUT_LIST = 0
        LIBRARY_LIST = 0
        MAGIC_NUMBER_LIST = 0
        ARCHIVE_LIST = 0
        UNARCHIVE_LIST = 0
        CROSSOVERRATE_LIST = 1
        TRANSPOSITIONRATE_LIST = 1
        PREFER_WINNER_LIST = false
        """
    )

    if seed_existing:
        arena_dir = tmp_path / "arena0"
        arena_dir.mkdir()
        for warrior_id in range(1, 11):
            (arena_dir / f"{warrior_id}.red").write_text("DAT.F #0, #0\n", encoding="utf-8")
        (tmp_path / "archive").mkdir()

    config = evolverstage.load_configuration(str(config_path))
    captured = capsys.readouterr()

    assert config.alreadyseeded is expected_seeded
    if expected_message:
        assert expected_message in captured.out
    else:
        assert "Arenas will be freshly seeded" not in captured.out


def test_validate_config_accepts_pmars_engine():
    config = replace(_DEFAULT_CONFIG, battle_engine="pmars")
    evolverstage.validate_config(config)


def test_candidate_pmars_paths_respect_env_override(monkeypatch):
    monkeypatch.setenv("PMARS_CMD", "/custom/pmars")

    candidates = evolverstage._candidate_pmars_paths()

    assert candidates[0] == os.path.expanduser("/custom/pmars")


def test_candidate_nmars_paths_respect_env_override(monkeypatch):
    monkeypatch.setenv("NMARS_CMD", "/custom/nmars")

    candidates = evolverstage._candidate_nmars_paths()

    assert candidates[0] == os.path.expanduser("/custom/nmars")


def test_validate_config_rejects_unknown_engine():
    config = replace(_DEFAULT_CONFIG, battle_engine="unknown")
    with pytest.raises(ValueError, match="BATTLE_ENGINE"):
        evolverstage.validate_config(config)


def test_validate_config_rejects_excessive_wardistance():
    invalid_wardistance = list(_DEFAULT_CONFIG.wardistance_list)
    invalid_wardistance[0] = _DEFAULT_CONFIG.coresize_list[0] // 2 + 1
    config = replace(_DEFAULT_CONFIG, wardistance_list=invalid_wardistance)

    with pytest.raises(ValueError, match="WARDISTANCE_LIST"):
        evolverstage.validate_config(config)


def test_validate_config_rejects_short_wardistance():
    shorter_distance = list(_DEFAULT_CONFIG.wardistance_list)
    shorter_distance[0] = _DEFAULT_CONFIG.warlen_list[0] - 1
    config = replace(_DEFAULT_CONFIG, wardistance_list=shorter_distance)

    with pytest.raises(
        ValueError,
        match="WARDISTANCE_LIST values must be greater than or equal to their corresponding WARLEN_LIST values",
    ):
        evolverstage.validate_config(config)


def test_validate_config_rejects_nonpositive_checkpoint_interval():
    config = replace(_DEFAULT_CONFIG, arena_checkpoint_interval=0)
    with pytest.raises(ValueError, match="ARENA_CHECKPOINT_INTERVAL"):
        evolverstage.validate_config(config)


def test_validate_config_rejects_negative_arena_weights():
    invalid_weights = list(_DEFAULT_CONFIG.arena_weight_list)
    invalid_weights[0] = -1
    config = replace(_DEFAULT_CONFIG, arena_weight_list=invalid_weights)

    with pytest.raises(ValueError, match="ARENA_WEIGHT_LIST"):
        evolverstage.validate_config(config)


def test_validate_config_rejects_all_zero_arena_weights():
    arena_count = _DEFAULT_CONFIG.last_arena + 1
    zero_weights = [0] * arena_count
    config = replace(_DEFAULT_CONFIG, arena_weight_list=zero_weights)

    with pytest.raises(ValueError, match="ARENA_WEIGHT_LIST"):
        evolverstage.validate_config(config)


def test_rebuild_instruction_tables_requires_non_dat_opcodes():
    config = replace(_DEFAULT_CONFIG, instr_set=["DAT"])
    try:
        with pytest.raises(ValueError, match="INSTR_SET") as excinfo:
            evolverstage.rebuild_instruction_tables(config)
        assert "opcode other than DAT" in str(excinfo.value)
    finally:
        evolverstage.rebuild_instruction_tables(_DEFAULT_CONFIG)


def test_validate_config_rejects_invalid_instr_modes():
    config = replace(_DEFAULT_CONFIG, instr_modes=["$", "X"])
    with pytest.raises(ValueError, match="INSTR_MODES") as excinfo:
        evolverstage.validate_config(config)
    assert "X" in str(excinfo.value)


@pytest.mark.parametrize(
    "body, error_pattern",
    [
        (
            """
            LAST_ARENA = 1
            CORESIZE_LIST = 8000
            SANITIZE_LIST = 80, 81
            CYCLES_LIST = 1000, 2000
            PROCESSES_LIST = 8, 8
            WARLEN_LIST = 20, 20
            WARDISTANCE_LIST = 20, 20
            NUMWARRIORS = 10
            CLOCK_TIME = 1
            BATTLEROUNDS_LIST = 1, 1
            NOTHING_LIST = 1, 1
            RANDOM_LIST = 1, 1
            NAB_LIST = 0, 0
            MINI_MUT_LIST = 0, 0
            MICRO_MUT_LIST = 0, 0
            LIBRARY_LIST = 0, 0
            MAGIC_NUMBER_LIST = 0, 0
            ARCHIVE_LIST = 0, 0
            UNARCHIVE_LIST = 0, 0
            CROSSOVERRATE_LIST = 1, 1
            TRANSPOSITIONRATE_LIST = 1, 1
            PREFER_WINNER_LIST = false, false
            """,
            "CORESIZE_LIST",
        ),
        (
            """
            LAST_ARENA = 0
            CORESIZE_LIST = 8000
            SANITIZE_LIST = 80
            CYCLES_LIST = 1000
            PROCESSES_LIST = 8
            WARLEN_LIST = 20
            WARDISTANCE_LIST = 20
            NUMWARRIORS = 10
            CLOCK_TIME = 1
            BATTLEROUNDS_LIST = 5
            NOTHING_LIST = 1
            RANDOM_LIST = 0
            NAB_LIST = -1
            MINI_MUT_LIST = 0
            MICRO_MUT_LIST = 0
            LIBRARY_LIST = 0
            MAGIC_NUMBER_LIST = 0
            ARCHIVE_LIST = 0
            UNARCHIVE_LIST = 0
            CROSSOVERRATE_LIST = 1
            TRANSPOSITIONRATE_LIST = 1
            PREFER_WINNER_LIST = false
            """,
            "NAB_LIST",
        ),
    ],
)
def test_load_configuration_rejects_invalid_configs(write_config, body, error_pattern):
    from evolverstage import load_configuration

    config_path = write_config(body)

    with pytest.raises(ValueError, match=error_pattern):
        load_configuration(str(config_path))


def test_validate_config_warns_when_lists_longer_than_last_arena():
    config = replace(
        _DEFAULT_CONFIG,
        last_arena=0,
        coresize_list=list(_DEFAULT_CONFIG.coresize_list[:2]),
        sanitize_list=list(_DEFAULT_CONFIG.sanitize_list[:2]),
        cycles_list=list(_DEFAULT_CONFIG.cycles_list[:2]),
        processes_list=list(_DEFAULT_CONFIG.processes_list[:2]),
        readlimit_list=list(_DEFAULT_CONFIG.readlimit_list[:2]),
        writelimit_list=list(_DEFAULT_CONFIG.writelimit_list[:2]),
        warlen_list=list(_DEFAULT_CONFIG.warlen_list[:2]),
        wardistance_list=list(_DEFAULT_CONFIG.wardistance_list[:2]),
        arena_weight_list=list(_DEFAULT_CONFIG.arena_weight_list[:2]),
    )

    with pytest.warns(UserWarning, match="LAST_ARENA limits"):
        evolverstage.validate_config(config)


def test_select_arena_index_honours_weights():
    config = replace(
        _DEFAULT_CONFIG,
        last_arena=1,
        coresize_list=list(_DEFAULT_CONFIG.coresize_list[:2]),
        sanitize_list=list(_DEFAULT_CONFIG.sanitize_list[:2]),
        cycles_list=list(_DEFAULT_CONFIG.cycles_list[:2]),
        processes_list=list(_DEFAULT_CONFIG.processes_list[:2]),
        readlimit_list=list(_DEFAULT_CONFIG.readlimit_list[:2]),
        writelimit_list=list(_DEFAULT_CONFIG.writelimit_list[:2]),
        warlen_list=list(_DEFAULT_CONFIG.warlen_list[:2]),
        wardistance_list=list(_DEFAULT_CONFIG.wardistance_list[:2]),
        arena_weight_list=[0, 5],
    )

    evolverstage.set_rng_sequence([1])
    try:
        assert evolverstage._select_arena_index(config) == 1
    finally:
        evolverstage.set_rng_sequence([])

    config_no_weights = replace(config, arena_weight_list=[])
    evolverstage.set_rng_sequence([0])
    try:
        assert evolverstage._select_arena_index(config_no_weights) == 0
    finally:
        evolverstage.set_rng_sequence([])


def test_in_memory_storage_defers_disk_writes_until_required(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        textwrap.dedent(
            """
            [DEFAULT]
            BATTLE_ENGINE = internal
            LAST_ARENA = 0
            CORESIZE_LIST = 80
            SANITIZE_LIST = 80
            CYCLES_LIST = 800
            PROCESSES_LIST = 8
            READLIMIT_LIST = 80
            WRITELIMIT_LIST = 80
            WARLEN_LIST = 5
            WARDISTANCE_LIST = 5
            NUMWARRIORS = 2
            CLOCK_TIME = 1
            BATTLEROUNDS_LIST = 1
            NOTHING_LIST = 1
            RANDOM_LIST = 0
            NAB_LIST = 0
            MINI_MUT_LIST = 0
            MICRO_MUT_LIST = 0
            LIBRARY_LIST = 0
            MAGIC_NUMBER_LIST = 0
            ARCHIVE_LIST = 0
            UNARCHIVE_LIST = 0
            CROSSOVERRATE_LIST = 1
            TRANSPOSITIONRATE_LIST = 1
            PREFER_WINNER_LIST = false
            IN_MEMORY_ARENAS = true
            ARENA_CHECKPOINT_INTERVAL = 100
            INSTR_SET = MOV
            """
        ).strip()
    )

    arena_dir = tmp_path / "arena0"
    arena_dir.mkdir()
    (tmp_path / "archive").mkdir()
    warrior_path = arena_dir / "1.red"
    warrior_path.write_text("DAT.F #0, #0\n", encoding="utf-8")
    (arena_dir / "2.red").write_text("DAT.F #0, #0\n", encoding="utf-8")

    config = evolverstage.load_configuration(str(config_path))
    evolverstage.set_active_config(config)
    storage = evolverstage.create_arena_storage(config)
    evolverstage.set_arena_storage(storage)
    storage.load_existing()

    write_events: list[tuple[int, int]] = []
    original_write = storage._write_warrior  # type: ignore[attr-defined]

    def _tracking_write(arena: int, warrior_id: int) -> None:
        write_events.append((arena, warrior_id))
        original_write(arena, warrior_id)

    storage._write_warrior = _tracking_write  # type: ignore[attr-defined]

    storage.set_warrior_lines(0, 1, ["MOV.I #1, #2\n"])
    assert write_events == []
    assert warrior_path.read_text(encoding="utf-8") == "DAT.F #0, #0\n"

    storage.ensure_warriors_on_disk(0, [2])
    assert write_events == []
    assert warrior_path.read_text(encoding="utf-8") == "DAT.F #0, #0\n"

    storage.ensure_warriors_on_disk(0, [1])
    assert write_events == [(0, 1)]
    assert warrior_path.read_text(encoding="utf-8") == "MOV.I #1, #2\n"

    write_events.clear()
    storage.set_warrior_lines(0, 2, ["ADD.I #3, #4\n"])
    assert storage.flush_all() is True
    assert write_events == [(0, 2)]

    write_events.clear()
    assert storage.flush_all() is False

    storage._write_warrior = original_write  # type: ignore[attr-defined]
    evolverstage.set_active_config(_DEFAULT_CONFIG)


def test_build_marble_bag_combines_strategy_counts():
    config = replace(
        _DEFAULT_CONFIG,
        nothing_list=[1],
        random_list=[2],
        nab_list=[3],
        mini_mut_list=[4],
        micro_mut_list=[5],
        library_list=[6],
        magic_number_list=[7],
    )

    bag = evolverstage._build_marble_bag(0, config)

    assert sum(
        isinstance(strategy, evolverstage.DoNothingMutation) for strategy in bag
    ) == 1
    assert sum(
        isinstance(strategy, evolverstage.MajorMutation) for strategy in bag
    ) == 2
    assert sum(
        isinstance(strategy, evolverstage.NabInstruction) for strategy in bag
    ) == 3
    assert sum(
        isinstance(strategy, evolverstage.MinorMutation) for strategy in bag
    ) == 4
    assert sum(
        isinstance(strategy, evolverstage.MicroMutation) for strategy in bag
    ) == 5
    assert sum(
        isinstance(strategy, evolverstage.InstructionLibraryMutation)
        for strategy in bag
    ) == 6
    assert sum(
        isinstance(strategy, evolverstage.MagicNumberMutation) for strategy in bag
    ) == 7
    assert len(bag) == sum(range(1, 8))


def test_count_archive_warriors_counts_only_red_files(tmp_path):
    base_path = tmp_path
    archive_dir = base_path / "archive"
    archive_dir.mkdir()
    (archive_dir / "alpha.red").write_text("", encoding="utf-8")
    (archive_dir / "beta.RED").write_text("", encoding="utf-8")
    (archive_dir / "ignored.txt").write_text("", encoding="utf-8")
    (archive_dir / "subdir").mkdir()
    (archive_dir / "subdir" / "nested.red").write_text("", encoding="utf-8")

    archive_storage = engine.DiskArchiveStorage(archive_path=str(archive_dir))

    assert archive_storage.count() == 2


def test_count_instruction_library_entries_ignores_comments(tmp_path):
    library_path = tmp_path / "library.txt"
    library_path.write_text(
        """; comment

MOV 0, 0
; another comment
ADD 0, 1
    ; indented comment
""",
        encoding="utf-8",
    )

    assert evolverstage._count_instruction_library_entries(str(library_path)) == 2
    assert evolverstage._count_instruction_library_entries(None) == 0
    evolverstage.set_arena_storage(evolverstage.create_arena_storage(_DEFAULT_CONFIG))


def test_execute_battle_parses_pmars_output(monkeypatch):
    temp_config = replace(_DEFAULT_CONFIG, battle_engine="pmars")
    sample_output = (
        "Alpha by Example scores 10\n"
        "Beta by Example scores 20\n"
        "Results: 1 3 1\n"
    )

    monkeypatch.setattr(
        evolverstage, "_run_external_command", lambda *args, **kwargs: sample_output
    )
    monkeypatch.setattr(
        evolverstage, "_candidate_pmars_paths", lambda: ["fake-pmars"]
    )
    monkeypatch.setattr(
        evolverstage,
        "_resolve_external_command",
        lambda engine_name, candidates: candidates[0],
    )

    evolverstage.set_active_config(temp_config)
    evolverstage.set_arena_storage(evolverstage.create_arena_storage(temp_config))
    try:
        warriors, scores = evolverstage.execute_battle(0, 101, 202, 0, verbose=False)
    finally:
        evolverstage.set_active_config(_DEFAULT_CONFIG)
        evolverstage.set_arena_storage(
            evolverstage.create_arena_storage(_DEFAULT_CONFIG)
        )

    assert warriors == [101, 202]
    assert scores == [10, 20]


def test_run_external_battle_pmars_forwards_seed_and_wardistance(monkeypatch):
    temp_config = replace(_DEFAULT_CONFIG, battle_engine="pmars")
    captured: dict[str, dict[str, object]] = {}

    def fake_run(executable, warrior_files, flag_args):
        captured["flag_args"] = dict(flag_args)
        return "Alpha by Example scores 10\nBeta by Example scores 20\n"

    monkeypatch.setattr(evolverstage, "_run_external_command", fake_run)
    monkeypatch.setattr(
        evolverstage, "_candidate_pmars_paths", lambda: ["fake-pmars"]
    )
    monkeypatch.setattr(
        evolverstage,
        "_resolve_external_command",
        lambda engine_name, candidates: candidates[0],
    )

    previous_config = evolverstage.get_active_config()
    try:
        evolverstage.set_active_config(temp_config)
        engine._run_external_battle(
            "pmars",
            arena_index=0,
            era_index=0,
            battlerounds=1,
            seed=123456,
            warrior1_path="warrior1.red",
            warrior2_path="warrior2.red",
        )
    finally:
        evolverstage.set_active_config(previous_config)

    assert "flag_args" in captured
    assert captured["flag_args"].get("-F") == 123456
    assert captured["flag_args"].get("-d") == temp_config.wardistance_list[0]
    assert "-f" not in captured["flag_args"]
    assert "-S" not in captured["flag_args"]


def test_run_external_battle_pmars_normalizes_seed(monkeypatch):
    temp_config = replace(_DEFAULT_CONFIG, battle_engine="pmars")
    captured: dict[str, dict[str, object]] = {}

    def fake_run(executable, warrior_files, flag_args):
        captured["flag_args"] = dict(flag_args)
        return "Alpha by Example scores 10\nBeta by Example scores 20\n"

    monkeypatch.setattr(evolverstage, "_run_external_command", fake_run)
    monkeypatch.setattr(
        evolverstage, "_candidate_pmars_paths", lambda: ["fake-pmars"]
    )
    monkeypatch.setattr(
        evolverstage,
        "_resolve_external_command",
        lambda engine_name, candidates: candidates[0],
    )

    previous_config = evolverstage.get_active_config()
    try:
        evolverstage.set_active_config(temp_config)
        engine._run_external_battle(
            "pmars",
            arena_index=0,
            era_index=0,
            battlerounds=1,
            seed=2_147_483_647,
            warrior1_path="warrior1.red",
            warrior2_path="warrior2.red",
        )
    finally:
        evolverstage.set_active_config(previous_config)

    assert "flag_args" in captured
    assert captured["flag_args"].get("-F") == 1_073_741_822


def test_run_external_battle_nmars_uses_expected_flags(monkeypatch):
    temp_config = replace(_DEFAULT_CONFIG, battle_engine="nmars")
    captured: dict[str, dict[str, object]] = {}

    def fake_run(executable, warrior_files, flag_args):
        captured["flag_args"] = dict(flag_args)
        return "Alpha by Example scores 10\nBeta by Example scores 20\n"

    monkeypatch.setattr(evolverstage, "_run_external_command", fake_run)
    monkeypatch.setattr(
        evolverstage, "_candidate_nmars_paths", lambda: ["fake-nmars"]
    )
    monkeypatch.setattr(
        evolverstage,
        "_resolve_external_command",
        lambda engine_name, candidates: candidates[0],
    )

    previous_config = evolverstage.get_active_config()
    try:
        evolverstage.set_active_config(temp_config)
        engine._run_external_battle(
            "nmars",
            arena_index=0,
            era_index=0,
            battlerounds=1,
            seed=None,
            warrior1_path="warrior1.red",
            warrior2_path="warrior2.red",
        )
    finally:
        evolverstage.set_active_config(previous_config)

    assert "flag_args" in captured
    flags = captured["flag_args"]
    assert flags.get("-r") == 1
    assert flags.get("-p") == temp_config.processes_list[0]
    assert flags.get("-c") == temp_config.cycles_list[0]
    assert flags.get("-s") == temp_config.coresize_list[0]
    assert flags.get("-l") == temp_config.warlen_list[0]
    assert flags.get("-d") == temp_config.wardistance_list[0]
    assert "-w" not in flags
    assert "-F" not in flags


def test_execute_battle_parses_nmars_output(monkeypatch):
    temp_config = replace(_DEFAULT_CONFIG, battle_engine="nmars")
    sample_output = (
        "303 0 0 0 7 scores\n"
        "404 0 0 0 12 scores\n"
        "Results: 1 0 1\n"
    )

    monkeypatch.setattr(
        evolverstage, "_run_external_command", lambda *args, **kwargs: sample_output
    )
    monkeypatch.setattr(
        evolverstage, "_candidate_nmars_paths", lambda: ["fake-nmars"]
    )
    monkeypatch.setattr(
        evolverstage,
        "_resolve_external_command",
        lambda engine_name, candidates: candidates[0],
    )

    evolverstage.set_active_config(temp_config)
    evolverstage.set_arena_storage(evolverstage.create_arena_storage(temp_config))
    try:
        warriors, scores = evolverstage.execute_battle(0, 303, 404, 0, verbose=False)
    finally:
        evolverstage.set_active_config(_DEFAULT_CONFIG)
        evolverstage.set_arena_storage(
            evolverstage.create_arena_storage(_DEFAULT_CONFIG)
        )

    warrior_scores = dict(zip(warriors, scores))
    assert warrior_scores == {303: 7, 404: 12}


def test_execute_battle_raises_when_nmars_scores_missing(monkeypatch):
    temp_config = replace(_DEFAULT_CONFIG, battle_engine="nmars")
    sample_output = "Header line without keyword\n"

    monkeypatch.setattr(
        evolverstage, "_run_external_command", lambda *args, **kwargs: sample_output
    )
    monkeypatch.setattr(
        evolverstage, "_candidate_nmars_paths", lambda: ["fake-nmars"]
    )
    monkeypatch.setattr(
        evolverstage,
        "_resolve_external_command",
        lambda engine_name, candidates: candidates[0],
    )

    evolverstage.set_active_config(temp_config)
    evolverstage.set_arena_storage(evolverstage.create_arena_storage(temp_config))
    try:
        with pytest.raises(RuntimeError, match="did not include any lines containing 'scores'"):
            evolverstage.execute_battle(0, 1, 2, 0, verbose=False)
    finally:
        evolverstage.set_active_config(_DEFAULT_CONFIG)
        evolverstage.set_arena_storage(
            evolverstage.create_arena_storage(_DEFAULT_CONFIG)
        )


def test_resolve_external_command_lists_tried_candidates(monkeypatch):
    monkeypatch.setattr(evolverstage.shutil, "which", lambda candidate: None)

    with pytest.raises(RuntimeError) as excinfo:
        evolverstage._resolve_external_command(
            "SampleEngine", ["/missing/bin/sample", "sample"]
        )

    message = str(excinfo.value)
    assert "SampleEngine" in message
    assert "/missing/bin/sample" in message
    assert "sample" in message


def test_determine_winner_and_loser_reports_draw(monkeypatch):
    def fake_random(min_val, max_val):
        assert (min_val, max_val) == (1, 2)
        return 1

    monkeypatch.setattr(evolverstage, "get_random_int", fake_random)

    winner, loser, was_draw = evolverstage.determine_winner_and_loser(
        [11, 22], [55, 55]
    )

    assert was_draw is True
    assert winner == 22
    assert loser == 11


def test_load_configuration_checks_seeded_directories(tmp_path, capsys):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        textwrap.dedent(
            """
            [DEFAULT]
            LAST_ARENA = 1
            CORESIZE_LIST = 8000, 8000
            SANITIZE_LIST = 80, 80
            CYCLES_LIST = 1000, 1000
            PROCESSES_LIST = 8, 8
            WARLEN_LIST = 20, 20
            WARDISTANCE_LIST = 20, 20
            NUMWARRIORS = 10
            CLOCK_TIME = 1
            BATTLEROUNDS_LIST = 5, 5
            NOTHING_LIST = 1,1
            RANDOM_LIST = 1,1
            NAB_LIST = 0,0
            MINI_MUT_LIST = 0,0
            MICRO_MUT_LIST = 0,0
            LIBRARY_LIST = 0,0
            MAGIC_NUMBER_LIST = 0,0
            ARCHIVE_LIST = 0,0
            UNARCHIVE_LIST = 0,0
            CROSSOVERRATE_LIST = 1,1
            TRANSPOSITIONRATE_LIST = 1,1
            PREFER_WINNER_LIST = false,false
            """
        ).strip()
    )

    (tmp_path / "arena0").mkdir()
    # Intentionally leave arena1 missing
    (tmp_path / "archive").mkdir()

    from evolverstage import load_configuration

    config = load_configuration(str(config_path))
    captured = capsys.readouterr()

    assert config.alreadyseeded is False
    assert (
        "Arenas will be freshly seeded because required warriors are missing."
        in captured.out
    )


def test_data_logger_writes_header_once(tmp_path):
    from evolverstage import DataLogger

    log_path = tmp_path / "battle_log.csv"
    logger = DataLogger(str(log_path))
    logger.log_data(era=1, arena=2, winner=3, loser=4, score1=5, score2=6, bred_with=7)
    logger.log_data(era=2, arena=3, winner=4, loser=5, score1=6, score2=7, bred_with=8)

    content = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert content[0] == "era,arena,winner,loser,score1,score2,bred_with"
    assert len(content) == 3


def test_benchmark_logger_writes_header_once(tmp_path):
    from evolverstage import BenchmarkLogger

    log_path = tmp_path / "benchmark_log.csv"
    logger = BenchmarkLogger(str(log_path))
    logger.log_score(
        era=1,
        generation=5000,
        arena=2,
        champion=3,
        benchmark="alpha",
        score=42,
        benchmark_path="alpha.red",
    )
    logger.log_score(
        era=2,
        generation=10000,
        arena=2,
        champion=3,
        benchmark="beta",
        score=-10,
        benchmark_path=None,
    )
    logger.close()

    content = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert content[0] == (
        "era,generation,arena,champion,benchmark,score,benchmark_path"
    )
    assert len(content) == 3


def test_log_benchmark_scores_for_champions_records_scores(
    monkeypatch, tmp_path
):
    from evolverstage import (
        BenchmarkLogger,
        BenchmarkWarrior,
        _log_benchmark_scores_for_champions,
        create_arena_storage,
        set_active_config,
        set_arena_storage,
    )

    benchmark = BenchmarkWarrior(
        name="alpha",
        code="MOV 0, 0\n",
        path=str(tmp_path / "alpha.red"),
    )
    config = replace(
        _DEFAULT_CONFIG,
        base_path=str(tmp_path),
        archive_path=str(tmp_path / "archive"),
        last_arena=0,
        numwarriors=1,
        benchmark_sets={0: [benchmark]},
    )

    (tmp_path / "archive").mkdir(exist_ok=True)

    try:
        previous_config = evolverstage.get_active_config()
    except RuntimeError:
        previous_config = None
    try:
        previous_storage = evolverstage.get_arena_storage()
    except RuntimeError:
        previous_storage = None

    storage = create_arena_storage(config)
    set_active_config(config)
    set_arena_storage(storage)
    storage.load_existing()
    storage.set_warrior_lines(0, 1, ["MOV 0, 0\n"])

    def fake_execute_battle_with_sources(
        arena_index,
        warrior_id,
        warrior_code,
        bench_identifier,
        bench_code,
        era,
        verbose=False,
        seed=None,
    ):
        return [warrior_id, bench_identifier], [123, -123]

    monkeypatch.setattr(
        evolverstage,
        "execute_battle_with_sources",
        fake_execute_battle_with_sources,
    )

    log_path = tmp_path / "benchmark_log.csv"
    logger = BenchmarkLogger(str(log_path))
    _log_benchmark_scores_for_champions(
        era=0,
        generation=5,
        champions={0: 1},
        active_config=config,
        benchmark_logger=logger,
    )
    logger.close()

    lines = [
        line
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines[0] == (
        "era,generation,arena,champion,benchmark,score,benchmark_path"
    )
    assert lines[1].startswith("0,5,0,1,alpha,123")

    if previous_config is not None:
        set_active_config(previous_config)
        if previous_storage is not None:
            set_arena_storage(previous_storage)
        else:
            set_arena_storage(create_arena_storage(previous_config))
    else:
        fallback_config = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
        set_active_config(fallback_config)
        set_arena_storage(create_arena_storage(fallback_config))


def test_run_internal_battle_integration(tmp_path, monkeypatch):
    compile_worker()
    import evolverstage

    importlib.reload(evolverstage)

    config = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
    config.base_path = str(tmp_path)
    config.archive_path = os.path.join(config.base_path, "archive")
    evolverstage.set_active_config(config)
    evolverstage.set_arena_storage(evolverstage.create_arena_storage(config))

    arena_dir = tmp_path / "arena1"
    arena_dir.mkdir()
    (arena_dir / "101.red").write_text("JMP.F $0, $0\n", encoding="utf-8")
    (arena_dir / "202.red").write_text("DAT.F #0, #0\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    result = evolverstage.run_internal_battle(
        arena=1,
        cont1=101,
        cont2=202,
        coresize=8000,
        cycles=200,
        processes=8000,
        readlimit=8000,
        writelimit=8000,
        warlen=20,
        wardistance=20,
        battlerounds=10,
        seed=42,
    )

    lines = result.strip().splitlines()
    assert len(lines) == 2
    scores = {parts[0]: int(parts[4]) for parts in (line.split() for line in lines)}
    assert scores["101"] > scores["202"]
    assert scores["202"] == 0


def test_execute_battle_uses_reproducible_seed(tmp_path, monkeypatch):
    compile_worker()
    import evolverstage

    importlib.reload(evolverstage)

    config = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
    config.base_path = str(tmp_path)
    config.archive_path = os.path.join(config.base_path, "archive")
    evolverstage.set_active_config(config)
    evolverstage.set_arena_storage(evolverstage.create_arena_storage(config))

    arena_dir = tmp_path / "arena0"
    arena_dir.mkdir()
    (arena_dir / "1.red").write_text("JMP.F $0, $0\n", encoding="utf-8")
    (arena_dir / "2.red").write_text("DAT.F #0, #0\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    def run_once():
        evolverstage.random.seed(1234)
        battle_seed = evolverstage._generate_internal_battle_seed()
        return evolverstage.execute_battle(
            arena=0,
            cont1=1,
            cont2=2,
            era=0,
            verbose=False,
            battlerounds_override=5,
            seed=battle_seed,
        )

    first_warriors, first_scores = run_once()
    second_warriors, second_scores = run_once()

    assert first_warriors == second_warriors
    assert first_scores == second_scores


def test_end_to_end_evolution_run(tmp_path, capsys):
    compile_worker()
    capsys.readouterr()

    global _DEFAULT_CONFIG

    importlib.reload(evolverstage)
    _DEFAULT_CONFIG = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
    evolverstage.set_active_config(_DEFAULT_CONFIG)
    evolverstage.set_arena_storage(evolverstage.create_arena_storage(_DEFAULT_CONFIG))

    initial_warrior = (
        textwrap.dedent(
            """
            MOV.I #0, #0
            ADD.AB #1, #1
            JMP.B $0, $0
            DAT.F #0, #0
            NOP.F $0, $0
            """
        ).strip()
        + "\n"
    )

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()

    for arena_index in range(2):
        arena_dir = tmp_path / f"arena{arena_index}"
        arena_dir.mkdir()
        for warrior_id in range(1, 4):
            (arena_dir / f"{warrior_id}.red").write_text(
                initial_warrior, encoding="utf-8"
            )

    config_path = tmp_path / "config.ini"
    config_path.write_text(
        textwrap.dedent(
            """
            [DEFAULT]
            BATTLE_ENGINE = internal
            LAST_ARENA = 1
            NUMWARRIORS = 3
            CLOCK_TIME = 0.001
            BATTLE_LOG_FILE = battle_log.csv
            RUN_FINAL_TOURNAMENT = true
            CORESIZE_LIST = 80, 80
            SANITIZE_LIST = 80, 80
            CYCLES_LIST = 200, 200
            PROCESSES_LIST = 8, 8
            READLIMIT_LIST = 80, 80
            WRITELIMIT_LIST = 80, 80
            WARLEN_LIST = 5, 5
            WARDISTANCE_LIST = 10, 10
            BATTLEROUNDS_LIST = 1, 1
            NOTHING_LIST = 1, 1
            RANDOM_LIST = 1, 1
            NAB_LIST = 1, 1
            MINI_MUT_LIST = 1, 1
            MICRO_MUT_LIST = 1, 1
            LIBRARY_LIST = 1, 1
            MAGIC_NUMBER_LIST = 1, 1
            ARCHIVE_LIST = 0, 0
            UNARCHIVE_LIST = 0, 0
            CROSSOVERRATE_LIST = 1, 1
            TRANSPOSITIONRATE_LIST = 1, 1
            PREFER_WINNER_LIST = false, false
            ARENA_CHECKPOINT_INTERVAL = 0
            INSTR_SET = MOV, ADD, DAT
            INSTR_MODES = $, #
            INSTR_MODIF = A, B, F
            """
        ).strip(),
        encoding="utf-8",
    )

    try:
        previous_config = evolverstage.get_active_config()
    except RuntimeError:
        previous_config = None
    try:
        previous_storage = evolverstage.get_arena_storage()
    except RuntimeError:
        previous_storage = None

    try:
        exit_code = evolverstage.main([
            "--config",
            str(config_path),
            "--seed",
            "1234",
        ])
    finally:
        if previous_config is not None:
            evolverstage.set_active_config(previous_config)
            if previous_storage is not None:
                evolverstage.set_arena_storage(previous_storage)
            else:
                evolverstage.set_arena_storage(
                    evolverstage.create_arena_storage(previous_config)
                )
        else:
            fallback_config = evolverstage.load_configuration(
                str(DEFAULT_SETTINGS_PATH)
            )
            evolverstage.set_active_config(fallback_config)
            evolverstage.set_arena_storage(
                evolverstage.create_arena_storage(fallback_config)
            )

    assert exit_code == 0

    captured = capsys.readouterr()
    assert "================ Final Tournament ================" in captured.out
    assert "Arena 0 final standings:" in captured.out
    assert "Final tournament completed" in captured.out

    battle_log_path = tmp_path / "battle_log.csv"
    assert battle_log_path.exists()
    battle_log_lines = [
        line
        for line in battle_log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(battle_log_lines) > 1

    mutated_warriors = []
    for arena_index in range(2):
        arena_dir = tmp_path / f"arena{arena_index}"
        warrior_files = sorted(arena_dir.glob("*.red"))
        assert len(warrior_files) == 3
        for path in warrior_files:
            final_text = path.read_text(encoding="utf-8")
            if final_text != initial_warrior:
                mutated_warriors.append(path)

    assert mutated_warriors, "Expected evolved warriors to differ from initial seeds"


def test_run_internal_battle_requires_worker(tmp_path, monkeypatch):
    import evolverstage

    config = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
    config.base_path = str(tmp_path)
    config.archive_path = os.path.join(config.base_path, "archive")
    try:
        previous_config = evolverstage.get_active_config()
    except RuntimeError:
        previous_config = None
    evolverstage.set_active_config(config)

    arena_dir = tmp_path / "arena0"
    arena_dir.mkdir()
    (arena_dir / "1.red").write_text("DAT.F #0, #0\n", encoding="utf-8")
    (arena_dir / "2.red").write_text("DAT.F #0, #0\n", encoding="utf-8")

    monkeypatch.setattr(evolverstage, "CPP_WORKER_LIB", None)

    try:
        with pytest.raises(RuntimeError, match="Internal battle engine is required"):
            evolverstage.run_internal_battle(
                arena=0,
                cont1=1,
                cont2=2,
                coresize=8000,
                cycles=200,
                processes=8000,
                readlimit=8000,
                writelimit=8000,
                warlen=20,
                wardistance=1,
                battlerounds=10,
                seed=7,
            )
    finally:
        if previous_config is not None:
            evolverstage.set_active_config(previous_config)
            evolverstage.set_arena_storage(
                evolverstage.create_arena_storage(previous_config)
            )
        else:
            fallback_config = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
            evolverstage.set_active_config(fallback_config)
            evolverstage.set_arena_storage(
                evolverstage.create_arena_storage(fallback_config)
            )


def test_final_tournament_uses_single_round(monkeypatch, tmp_path, capsys):
    config = replace(
        _DEFAULT_CONFIG,
        base_path=str(tmp_path),
        last_arena=0,
        numwarriors=3,
        alreadyseeded=True,
    )
    config.archive_path = os.path.join(config.base_path, "archive")
    config.battlerounds_list = [5]

    arena_dir = tmp_path / "arena0"
    arena_dir.mkdir()
    for warrior_id in range(1, 4):
        (arena_dir / f"{warrior_id}.red").write_text(
            "DAT.F #0, #0\n",
            encoding="utf-8",
        )

    try:
        previous_config = evolverstage.get_active_config()
    except RuntimeError:
        previous_config = None

    evolverstage.set_active_config(config)

    battle_rounds: list[int] = []

    def fake_execute_battle(
        arena,
        cont1,
        cont2,
        era,
        verbose=True,
        battlerounds_override=None,
        seed=None,
    ):
        battle_rounds.append(battlerounds_override)
        return [cont1, cont2], [10, 5]

    monkeypatch.setattr(evolverstage, "execute_battle", fake_execute_battle)

    evolverstage.run_final_tournament(config)

    captured = capsys.readouterr()

    assert battle_rounds
    assert all(rounds == 1 for rounds in battle_rounds)
    assert "Final Tournament Progress" in captured.out

    if previous_config is not None:
        evolverstage.set_active_config(previous_config)
        evolverstage.set_arena_storage(
            evolverstage.create_arena_storage(previous_config)
        )
    else:
        evolverstage.set_active_config(_DEFAULT_CONFIG)
        evolverstage.set_arena_storage(
            evolverstage.create_arena_storage(_DEFAULT_CONFIG)
        )


def test_final_tournament_uses_in_memory_storage(monkeypatch, tmp_path, capsys):
    config = replace(
        _DEFAULT_CONFIG,
        base_path=str(tmp_path),
        battle_engine="internal",
        use_in_memory_arenas=True,
        last_arena=0,
        numwarriors=3,
        battlerounds_list=[_DEFAULT_CONFIG.battlerounds_list[0]],
    )
    config.archive_path = os.path.join(config.base_path, "archive")

    previous_config = evolverstage.get_active_config()
    evolverstage.set_active_config(config)

    storage = evolverstage.create_arena_storage(config)
    evolverstage.set_arena_storage(storage)
    storage.load_existing()
    for warrior_id in range(1, 4):
        storage.set_warrior_lines(0, warrior_id, ["DAT.F #0, #0\n"])

    battle_rounds: list[int] = []

    def fake_execute_battle(
        arena,
        cont1,
        cont2,
        era,
        verbose=True,
        battlerounds_override=None,
        seed=None,
    ):
        battle_rounds.append(battlerounds_override)
        return [cont1, cont2], [10, 5]

    monkeypatch.setattr(evolverstage, "execute_battle", fake_execute_battle)

    evolverstage.run_final_tournament(config)

    captured = capsys.readouterr()

    assert battle_rounds
    assert all(rounds == 1 for rounds in battle_rounds)
    assert "Final Tournament Progress" in captured.out
    assert not (tmp_path / "arena0").exists()

    evolverstage.set_active_config(previous_config)
    evolverstage.set_arena_storage(evolverstage.create_arena_storage(previous_config))


def test_run_internal_battle_passes_configuration_to_worker(
    monkeypatch, tmp_path, capsys
):
    import evolverstage

    config = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
    capsys.readouterr()
    config.base_path = str(tmp_path)
    config.archive_path = os.path.join(config.base_path, "archive")
    evolverstage.set_active_config(config)

    arena_dir = tmp_path / "arena0"
    arena_dir.mkdir()
    (arena_dir / "1.red").write_text("DAT.F #0, #0\n", encoding="utf-8")
    (arena_dir / "2.red").write_text("DAT.F #0, #0\n", encoding="utf-8")

    class FakeWorker:
        def __init__(self):
            self.args = None

        def run_battle(self, *args):
            self.args = args
            return b"1 0 0 0 0\n2 0 0 0 0\n"

    fake_worker = FakeWorker()
    monkeypatch.setattr(evolverstage, "CPP_WORKER_LIB", fake_worker)
    result = evolverstage.run_internal_battle(
        arena=0,
        cont1=1,
        cont2=2,
        coresize=8000,
        cycles=200,
        processes=8000,
        readlimit=8000,
        writelimit=8000,
        warlen=20,
        wardistance=5000,
        battlerounds=10,
        seed=123,
    )

    captured = capsys.readouterr()
    assert fake_worker.args is not None
    assert fake_worker.args[9] == 5000
    assert fake_worker.args[10] == 20
    assert fake_worker.args[11] == 10
    assert fake_worker.args[12] == 123
    assert result == "1 0 0 0 0\n2 0 0 0 0\n"

    assert "Clamping" not in captured.out


def test_execute_battle_in_memory_internal_avoids_disk_writes(monkeypatch, tmp_path):
    config = replace(
        _DEFAULT_CONFIG,
        base_path=str(tmp_path),
        battle_engine="internal",
        use_in_memory_arenas=True,
        last_arena=0,
        numwarriors=2,
        coresize_list=[_DEFAULT_CONFIG.coresize_list[0]],
        sanitize_list=[_DEFAULT_CONFIG.sanitize_list[0]],
        cycles_list=[_DEFAULT_CONFIG.cycles_list[0]],
        processes_list=[_DEFAULT_CONFIG.processes_list[0]],
        readlimit_list=[_DEFAULT_CONFIG.readlimit_list[0]],
        writelimit_list=[_DEFAULT_CONFIG.writelimit_list[0]],
        warlen_list=[_DEFAULT_CONFIG.warlen_list[0]],
        wardistance_list=[_DEFAULT_CONFIG.wardistance_list[0]],
        battlerounds_list=[_DEFAULT_CONFIG.battlerounds_list[0]],
    )
    config.archive_path = os.path.join(config.base_path, "archive")

    previous_config = evolverstage.get_active_config()
    evolverstage.set_active_config(config)

    storage = evolverstage.create_arena_storage(config)
    evolverstage.set_arena_storage(storage)
    storage.load_existing()
    storage.set_warrior_lines(0, 1, ["DAT.F #0, #0\n"])
    storage.set_warrior_lines(0, 2, ["DAT.F #0, #0\n"])

    def unexpected_persist(arena, warrior_ids):
        raise AssertionError(
            f"Unexpected persistence for arena {arena}: {warrior_ids}"
        )

    monkeypatch.setattr(storage, "ensure_warriors_on_disk", unexpected_persist)

    calls: list[tuple] = []

    def fake_run_internal_battle(*args, **kwargs):
        calls.append(args)
        return "1 Example Warrior scores 0\n2 Example Warrior scores 0\n"

    monkeypatch.setattr(evolverstage, "run_internal_battle", fake_run_internal_battle)

    try:
        warriors, scores = evolverstage.execute_battle(0, 1, 2, 0, verbose=False)
    finally:
        evolverstage.set_active_config(previous_config)
        evolverstage.set_arena_storage(
            evolverstage.create_arena_storage(previous_config)
        )

    assert warriors == [1, 2]
    assert scores == [0, 0]
    assert calls, "Internal worker was not invoked"
    assert not any(tmp_path.glob("arena0/*.red"))


def test_main_flushes_in_memory_internal_on_exit(monkeypatch, tmp_path):
    config = replace(
        _DEFAULT_CONFIG,
        base_path=str(tmp_path),
        battle_engine="internal",
        use_in_memory_arenas=True,
        last_arena=0,
        numwarriors=1,
        coresize_list=[_DEFAULT_CONFIG.coresize_list[0]],
        sanitize_list=[_DEFAULT_CONFIG.sanitize_list[0]],
        cycles_list=[_DEFAULT_CONFIG.cycles_list[0]],
        processes_list=[_DEFAULT_CONFIG.processes_list[0]],
        readlimit_list=[_DEFAULT_CONFIG.readlimit_list[0]],
        writelimit_list=[_DEFAULT_CONFIG.writelimit_list[0]],
        warlen_list=[_DEFAULT_CONFIG.warlen_list[0]],
        wardistance_list=[_DEFAULT_CONFIG.wardistance_list[0]],
        battlerounds_list=[_DEFAULT_CONFIG.battlerounds_list[0]],
    )

    previous_config = evolverstage.get_active_config()
    previous_storage = evolverstage.get_arena_storage()

    storage = evolverstage.create_arena_storage(config)
    evolverstage.set_active_config(config)
    evolverstage.set_arena_storage(storage)
    storage.load_existing()
    storage.set_warrior_lines(0, 1, ["MOV.I #1, #2\n"])

    def boom(_argv=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(evolverstage, "_main_impl", boom)
    monkeypatch.setattr(evolverstage, "close_console", lambda: None)

    try:
        with pytest.raises(RuntimeError):
            evolverstage.main([])
    finally:
        evolverstage.set_active_config(previous_config)
        evolverstage.set_arena_storage(previous_storage)

    warrior_path = tmp_path / "arena0" / "1.red"
    assert warrior_path.read_text(encoding="utf-8") == "MOV.I #1, #2\n"


def test_micro_mutation_handler():
    instruction = evolverstage.RedcodeInstruction(
        opcode="MOV",
        modifier="F",
        a_mode="$",
        a_field=5,
        b_mode="$",
        b_field=10,
    )
    evolverstage.set_rng_sequence([1, 1, 1, 2, 2, 1, 2, 2])
    micro_mutation = evolverstage.MicroMutation()
    try:
        instruction = micro_mutation.apply(instruction, 0, _DEFAULT_CONFIG, 0)
        assert instruction.a_field == 6

        instruction = micro_mutation.apply(instruction, 0, _DEFAULT_CONFIG, 0)
        assert instruction.a_field == 5

        instruction = micro_mutation.apply(instruction, 0, _DEFAULT_CONFIG, 0)
        assert instruction.b_field == 11

        instruction = micro_mutation.apply(instruction, 0, _DEFAULT_CONFIG, 0)
        assert instruction.b_field == 10
    finally:
        evolverstage.set_rng_sequence([])


def test_minor_mutation_handler(monkeypatch):
    base_instruction = evolverstage.RedcodeInstruction(
        opcode="MOV",
        modifier="F",
        a_mode="$",
        a_field=1,
        b_mode="$",
        b_field=2,
    )

    monkeypatch.setattr(evolverstage, "GENERATION_OPCODE_POOL", ["MOV", "ADD"])
    monkeypatch.setattr(evolverstage.config, "instr_modif", ["A", "B"])
    monkeypatch.setattr(evolverstage.config, "instr_modes", ["#", "$"])
    monkeypatch.setattr(evolverstage.config, "coresize_list", [10])
    monkeypatch.setattr(evolverstage.config, "warlen_list", [5])

    evolverstage.set_rng_sequence([1, 1, 2, 1, 3, 0, 4, 2, 3, 5, 0, 6, 1, -7])
    minor_mutation = evolverstage.MinorMutation()
    try:
        mutated = minor_mutation.apply(
            base_instruction.copy(),
            arena=0,
            config=evolverstage.config,
            magic_number=0,
        )
        assert mutated.opcode == "ADD"

        mutated = minor_mutation.apply(
            base_instruction.copy(),
            arena=0,
            config=evolverstage.config,
            magic_number=0,
        )
        assert mutated.modifier == "B"

        mutated = minor_mutation.apply(
            base_instruction.copy(),
            arena=0,
            config=evolverstage.config,
            magic_number=0,
        )
        assert mutated.a_mode == "#"

        mutated = minor_mutation.apply(
            base_instruction.copy(),
            arena=0,
            config=evolverstage.config,
            magic_number=0,
        )
        assert mutated.a_field == 3

        mutated = minor_mutation.apply(
            base_instruction.copy(),
            arena=0,
            config=evolverstage.config,
            magic_number=0,
        )
        assert mutated.b_mode == "#"

        mutated = minor_mutation.apply(
            base_instruction.copy(),
            arena=0,
            config=evolverstage.config,
            magic_number=0,
        )
        assert mutated.b_field == -7
    finally:
        evolverstage.set_rng_sequence([])


def test_generate_warrior_lines_until_non_dat_with_dat_only_pool(monkeypatch):
    monkeypatch.setattr(evolverstage, "GENERATION_OPCODE_POOL", ["DAT"])

    with pytest.raises(RuntimeError, match="cannot generate non-DAT opcodes"):
        evolverstage.generate_warrior_lines_until_non_dat(
            lambda: ["DAT.F $0, $0\n"],
            context="Test context",
            arena=0,
        )


def test_generate_warrior_lines_until_non_dat_retries_until_success(monkeypatch):
    monkeypatch.setattr(evolverstage, "GENERATION_OPCODE_POOL", ["DAT", "MOV"])

    attempts = 0

    def generator():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return ["DAT.F $0, $0\n"]
        return ["MOV.I $0, $0\n"]

    lines = evolverstage.generate_warrior_lines_until_non_dat(
        generator,
        context="Test context",
        arena=0,
    )

    assert lines == ["MOV.I $0, $0\n"]
    assert attempts == 3


@pytest.mark.parametrize(
    "source, error_pattern",
    [
        ("MOV $1, $2", "missing a modifier"),
        ("MOV.F 1, $2", "addressing mode"),
        ("MOV.F 1,2", "addressing mode"),
    ],
)
def test_parse_instruction_rejects_invalid_inputs(source, error_pattern):
    from evolverstage import parse_redcode_instruction

    with pytest.raises(ValueError, match=error_pattern):
        parse_redcode_instruction(source)


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "MOV.F$1,$2",
            {
                "label": None,
                "opcode": "MOV",
                "modifier": "F",
                "a_mode": "$",
                "a_field": 1,
                "b_mode": "$",
                "b_field": 2,
            },
        ),
        (
            "label MOV . F $-3,$4",
            {
                "label": "label",
                "opcode": "MOV",
                "modifier": "F",
                "a_mode": "$",
                "a_field": -3,
                "b_mode": "$",
                "b_field": 4,
            },
        ),
    ],
)
def test_parse_instruction_parses_whitespace_variations(source, expected):
    from evolverstage import parse_redcode_instruction

    parsed = parse_redcode_instruction(source)

    assert parsed is not None
    for key, value in expected.items():
        assert getattr(parsed, key) == value


@pytest.mark.parametrize(
    "a_mode, b_mode, expected_message",
    [
        ("?", "$", "Invalid addressing mode '?' for A-field operand"),
        ("$", "?", "Invalid addressing mode '?' for B-field operand"),
    ],
)
def test_sanitize_instruction_rejects_invalid_modes(a_mode, b_mode, expected_message):
    from evolverstage import RedcodeInstruction, sanitize_instruction

    instr = RedcodeInstruction(
        opcode="MOV",
        modifier="F",
        a_mode=a_mode,
        a_field=0,
        b_mode=b_mode,
        b_field=0,
    )

    with pytest.raises(ValueError, match=re.escape(expected_message)):
        sanitize_instruction(instr, arena=0)


def test_sanitize_instruction_replaces_1994_features_in_1988_arena():
    previous_config = evolverstage.get_active_config()
    try:
        spec_list = list(previous_config.arena_spec_list)
        spec_list[0] = evolverstage.SPEC_1988
        updated_config = replace(previous_config, arena_spec_list=spec_list)
        evolverstage.set_active_config(updated_config)

        mul_instruction = evolverstage.RedcodeInstruction(
            opcode="MUL",
            modifier="F",
            a_mode="$",
            a_field=0,
            b_mode="$",
            b_field=0,
        )
        sanitized_mul = evolverstage.sanitize_instruction(mul_instruction, arena=0)
        assert sanitized_mul.opcode == "DAT"

        mode_instruction = evolverstage.RedcodeInstruction(
            opcode="MOV",
            modifier="F",
            a_mode="{",
            a_field=1,
            b_mode="$",
            b_field=2,
        )
        sanitized_mode = evolverstage.sanitize_instruction(mode_instruction, arena=0)
        assert sanitized_mode.opcode == "DAT"
    finally:
        evolverstage.set_active_config(previous_config)


def test_choose_random_mode_filters_to_1988_defaults():
    previous_config = evolverstage.get_active_config()
    try:
        spec_list = list(previous_config.arena_spec_list)
        spec_list[0] = evolverstage.SPEC_1988
        updated_config = replace(
            previous_config,
            arena_spec_list=spec_list,
            instr_modes=["{", "}", "#"],
        )
        evolverstage.set_active_config(updated_config)
        evolverstage.set_rng_sequence([0])
        mode = evolverstage.choose_random_mode(0)
        assert mode in {"#", "$", "@", "<", ">"}
        assert mode != "{"
    finally:
        evolverstage.set_rng_sequence([])
        evolverstage.set_active_config(previous_config)
