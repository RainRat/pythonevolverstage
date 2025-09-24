import importlib
import os
import pathlib
import sys
import textwrap

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONEVOLVER_SKIP_MAIN", "1")

from test_support import compile_worker


def test_load_configuration_parses_types(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        textwrap.dedent(
            """
            [DEFAULT]
            BATTLE_ENGINE = internal
            LAST_ARENA = 2
            CORESIZE_LIST = 8000, 8192
            SANITIZE_LIST = 0,1
            CYCLES_LIST = 1000, 2000
            PROCESSES_LIST = 8, 16
            WARLEN_LIST = 20, 40
            WARDISTANCE_LIST = 5, 7
            NUMWARRIORS = 50
            ALREADYSEEDED = true
            CLOCK_TIME = 12.5
            BATTLE_LOG_FILE = logs.csv
            FINAL_ERA_ONLY = false
            NOTHING_LIST = 1,2,3
            RANDOM_LIST = 4,5
            NAB_LIST = 6
            MINI_MUT_LIST = 7
            MICRO_MUT_LIST = 8
            LIBRARY_LIST = 9, 10
            MAGIC_NUMBER_LIST = 11
            ARCHIVE_LIST = 12
            UNARCHIVE_LIST = 13
            LIBRARY_PATH = ./library
            CROSSOVERRATE_LIST = 14
            TRANSPOSITIONRATE_LIST = 15
            BATTLEROUNDS_LIST = 16, 32
            PREFER_WINNER_LIST = true, false
            INSTR_SET = MOV, ADD
            INSTR_MODES = #, $
            INSTR_MODIF = A, B
            """
        ).strip()
    )

    from evolverstage import load_configuration

    config = load_configuration(str(config_path))
    assert config.battle_engine == "internal"
    assert config.last_arena == 2
    assert config.coresize_list == [8000, 8192]
    assert config.sanitize_list == [0, 1]
    assert config.cycles_list == [1000, 2000]
    assert config.processes_list == [8, 16]
    assert config.warlen_list == [20, 40]
    assert config.wardistance_list == [5, 7]
    assert config.numwarriors == 50
    assert config.alreadyseeded is True
    assert pytest.approx(config.clock_time, rel=1e-6) == 12.5
    assert config.battle_log_file == "logs.csv"
    assert config.final_era_only is False
    assert config.nothing_list == [1, 2, 3]
    assert config.random_list == [4, 5]
    assert config.nab_list == [6]
    assert config.mini_mut_list == [7]
    assert config.micro_mut_list == [8]
    assert config.library_list == [9, 10]
    assert config.magic_number_list == [11]
    assert config.archive_list == [12]
    assert config.unarchive_list == [13]
    assert config.library_path == "./library"
    assert config.crossoverrate_list == [14]
    assert config.transpositionrate_list == [15]
    assert config.battlerounds_list == [16, 32]
    assert config.prefer_winner_list == [True, False]
    assert config.instr_set == ["MOV", "ADD"]
    assert config.instr_modes == ["#", "$"]
    assert config.instr_modif == ["A", "B"]


def test_data_logger_writes_header_once(tmp_path):
    from evolverstage import DataLogger

    log_path = tmp_path / "battle_log.csv"
    logger = DataLogger(str(log_path))
    logger.log_data(era=1, arena=2, winner=3, loser=4, score1=5, score2=6, bred_with=7)
    logger.log_data(era=2, arena=3, winner=4, loser=5, score1=6, score2=7, bred_with=8)

    content = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert content[0] == "era,arena,winner,loser,score1,score2,bred_with"
    assert len(content) == 3


def test_run_internal_battle_integration(tmp_path, monkeypatch):
    compile_worker()
    import evolverstage

    importlib.reload(evolverstage)

    arena_dir = tmp_path / "arena1"
    arena_dir.mkdir()
    (arena_dir / "101.red").write_text("JMP 0, 0\n", encoding="utf-8")
    (arena_dir / "202.red").write_text("DAT.F #0, #0\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    result = evolverstage.run_internal_battle(
        arena=1,
        cont1=101,
        cont2=202,
        coresize=8000,
        cycles=200,
        processes=8000,
        warlen=20,
        wardistance=1,
        battlerounds=10,
    )

    lines = result.strip().splitlines()
    assert len(lines) == 2
    scores = {parts[0]: int(parts[4]) for parts in (line.split() for line in lines)}
    assert scores["101"] > scores["202"]
    assert scores["202"] == 0
