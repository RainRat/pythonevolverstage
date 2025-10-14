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

import evolverstage

DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "settings.ini"
_DEFAULT_CONFIG = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
evolverstage.set_active_config(_DEFAULT_CONFIG)


def test_load_configuration_parses_types(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        textwrap.dedent(
            """
            [DEFAULT]
            BATTLE_ENGINE = internal
            LAST_ARENA = 1
            CORESIZE_LIST = 8000, 8192
            SANITIZE_LIST = 80, 81
            CYCLES_LIST = 1000, 2000
            PROCESSES_LIST = 8, 16
            WARLEN_LIST = 20, 40
            WARDISTANCE_LIST = 5, 7
            NUMWARRIORS = 50
            ALREADYSEEDED = false
            CLOCK_TIME = 12.5
            BATTLE_LOG_FILE = logs.csv
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
            INSTR_SET = MOV, ADD
            INSTR_MODES = #, $
            INSTR_MODIF = A, B
            """
        ).strip()
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
    assert config.wardistance_list == [5, 7]
    assert config.numwarriors == 50
    assert config.alreadyseeded is False
    assert pytest.approx(config.clock_time, rel=1e-6) == 12.5
    assert config.base_path == str(config_path.parent)
    assert config.battle_log_file == os.path.abspath(config_path.with_name("logs.csv"))
    assert config.final_era_only is False
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
    assert config.instr_set == ["MOV", "ADD"]
    assert config.instr_modes == ["#", "$"]
    assert config.instr_modif == ["A", "B"]


def test_load_configuration_rejects_mismatched_arena_lengths(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        textwrap.dedent(
            """
            [DEFAULT]
            LAST_ARENA = 1
            CORESIZE_LIST = 8000
            SANITIZE_LIST = 80, 81
            CYCLES_LIST = 1000, 2000
            PROCESSES_LIST = 8, 8
            WARLEN_LIST = 20, 20
            WARDISTANCE_LIST = 5, 5
            NUMWARRIORS = 10
            ALREADYSEEDED = false
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
            """
        ).strip()
    )

    from evolverstage import load_configuration

    with pytest.raises(ValueError, match="CORESIZE_LIST"):
        load_configuration(str(config_path))


def test_load_configuration_rejects_negative_marble_counts(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        textwrap.dedent(
            """
            [DEFAULT]
            LAST_ARENA = 0
            CORESIZE_LIST = 8000
            SANITIZE_LIST = 80
            CYCLES_LIST = 1000
            PROCESSES_LIST = 8
            WARLEN_LIST = 20
            WARDISTANCE_LIST = 5
            NUMWARRIORS = 10
            ALREADYSEEDED = false
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
            """
        ).strip()
    )

    from evolverstage import load_configuration

    with pytest.raises(ValueError, match="NAB_LIST"):
        load_configuration(str(config_path))


def test_load_configuration_checks_seeded_directories(tmp_path):
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
            WARDISTANCE_LIST = 5, 5
            NUMWARRIORS = 10
            ALREADYSEEDED = true
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

    with pytest.raises(FileNotFoundError, match="arena1"):
        load_configuration(str(config_path))


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

    config = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
    config.base_path = str(tmp_path)
    evolverstage.set_active_config(config)

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
        wardistance=1,
        battlerounds=10,
    )

    lines = result.strip().splitlines()
    assert len(lines) == 2
    scores = {parts[0]: int(parts[4]) for parts in (line.split() for line in lines)}
    assert scores["101"] > scores["202"]
    assert scores["202"] == 0


def test_run_internal_battle_requires_worker(tmp_path, monkeypatch):
    import evolverstage

    config = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
    config.base_path = str(tmp_path)
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
            )
    finally:
        if previous_config is not None:
            evolverstage.set_active_config(previous_config)
        else:
            fallback_config = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
            evolverstage.set_active_config(fallback_config)


def test_parse_instruction_requires_modifier():
    from evolverstage import parse_redcode_instruction

    with pytest.raises(ValueError, match="missing a modifier"):
        parse_redcode_instruction("MOV $1, $2")


def test_parse_instruction_requires_addressing_modes():
    from evolverstage import parse_redcode_instruction

    with pytest.raises(ValueError, match="addressing mode"):
        parse_redcode_instruction("MOV.F 1, $2")


def test_parse_instruction_requires_addressing_modes_for_both_operands():
    from evolverstage import parse_redcode_instruction

    with pytest.raises(ValueError, match="addressing mode"):
        parse_redcode_instruction("MOV.F 1,2")


def test_parse_instruction_supports_compact_whitespace():
    from evolverstage import parse_redcode_instruction

    parsed = parse_redcode_instruction("MOV.F$1,$2")

    assert parsed is not None
    assert parsed.opcode == "MOV"
    assert parsed.modifier == "F"
    assert parsed.a_mode == "$"
    assert parsed.a_field == 1
    assert parsed.b_mode == "$"
    assert parsed.b_field == 2


def test_parse_instruction_allows_spaces_around_modifier_separator():
    from evolverstage import parse_redcode_instruction

    parsed = parse_redcode_instruction("label MOV . F $-3,$4")

    assert parsed is not None
    assert parsed.label == "label"
    assert parsed.opcode == "MOV"
    assert parsed.modifier == "F"
    assert parsed.a_mode == "$"
    assert parsed.a_field == -3
    assert parsed.b_mode == "$"
    assert parsed.b_field == 4


def test_sanitize_instruction_rejects_invalid_modes():
    from evolverstage import RedcodeInstruction, sanitize_instruction

    instr = RedcodeInstruction(
        opcode="MOV",
        modifier="F",
        a_mode="?",
        a_field=0,
        b_mode="$",
        b_field=0,
    )

    with pytest.raises(ValueError, match=r"Invalid addressing mode '\?' for A-field operand"):
        sanitize_instruction(instr, arena=0)
