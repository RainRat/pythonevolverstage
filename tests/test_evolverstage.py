import importlib
import os
import pathlib
import sys
import textwrap
from dataclasses import replace

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
evolverstage.set_arena_storage(evolverstage.create_arena_storage(_DEFAULT_CONFIG))


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


def test_load_configuration_reads_in_memory_settings(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        textwrap.dedent(
            """
            [DEFAULT]
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
            ALREADYSEEDED = true
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
        ).strip()
    )

    (tmp_path / "arena0").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "arena0" / "1.red").write_text("DAT.F #0, #0\n", encoding="utf-8")
    (tmp_path / "arena0" / "2.red").write_text("DAT.F #0, #0\n", encoding="utf-8")

    config = evolverstage.load_configuration(str(config_path))
    assert config.use_in_memory_arenas is True
    assert config.arena_checkpoint_interval == 20000


def test_load_configuration_overrides_alreadyseeded_when_directories_missing(tmp_path, capsys):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        textwrap.dedent(
            """
            [DEFAULT]
            LAST_ARENA = 0
            CORESIZE_LIST = 80
            SANITIZE_LIST = 80
            CYCLES_LIST = 800
            PROCESSES_LIST = 8
            WARLEN_LIST = 5
            WARDISTANCE_LIST = 5
            NUMWARRIORS = 10
            ALREADYSEEDED = true
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
        ).strip()
    )

    config = evolverstage.load_configuration(str(config_path))
    captured = capsys.readouterr()

    assert config.alreadyseeded is False
    assert "ALREADYSEEDED was True" in captured.out


def test_load_configuration_retains_alreadyseeded_when_only_archive_missing(tmp_path, capsys):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        textwrap.dedent(
            """
            [DEFAULT]
            LAST_ARENA = 0
            CORESIZE_LIST = 80
            SANITIZE_LIST = 80
            CYCLES_LIST = 800
            PROCESSES_LIST = 8
            WARLEN_LIST = 5
            WARDISTANCE_LIST = 5
            NUMWARRIORS = 10
            ALREADYSEEDED = true
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
        ).strip()
    )

    (tmp_path / "arena0").mkdir()

    config = evolverstage.load_configuration(str(config_path))
    captured = capsys.readouterr()

    assert config.alreadyseeded is True
    assert "ALREADYSEEDED was True" not in captured.out
    assert (tmp_path / "archive").is_dir()


def test_validate_config_accepts_pmars_engine():
    config = replace(_DEFAULT_CONFIG, battle_engine="pmars")
    evolverstage.validate_config(config)


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


def test_validate_config_rejects_nonpositive_checkpoint_interval():
    config = replace(_DEFAULT_CONFIG, arena_checkpoint_interval=0)
    with pytest.raises(ValueError, match="ARENA_CHECKPOINT_INTERVAL"):
        evolverstage.validate_config(config)


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
    )

    with pytest.warns(UserWarning, match="LAST_ARENA limits"):
        evolverstage.validate_config(config)


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


def test_in_memory_storage_defers_disk_writes_until_required(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        textwrap.dedent(
            """
            [DEFAULT]
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
            ALREADYSEEDED = true
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

    storage.set_warrior_lines(0, 1, ["MOV.I #1, #2\n"])
    assert warrior_path.read_text(encoding="utf-8") == "DAT.F #0, #0\n"

    storage.ensure_warriors_on_disk(0, [2])
    assert warrior_path.read_text(encoding="utf-8") == "DAT.F #0, #0\n"

    storage.ensure_warriors_on_disk(0, [1])
    assert warrior_path.read_text(encoding="utf-8") == "MOV.I #1, #2\n"


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

    config = load_configuration(str(config_path))
    captured = capsys.readouterr()

    assert config.alreadyseeded is False
    assert "ALREADYSEEDED was True" in captured.out


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
        wardistance=1,
        battlerounds=10,
        seed=42,
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
        arena, cont1, cont2, era, verbose=True, battlerounds_override=None
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

    previous_config = evolverstage.get_active_config()
    evolverstage.set_active_config(config)

    storage = evolverstage.create_arena_storage(config)
    evolverstage.set_arena_storage(storage)
    storage.load_existing()
    for warrior_id in range(1, 4):
        storage.set_warrior_lines(0, warrior_id, ["DAT.F #0, #0\n"])

    battle_rounds: list[int] = []

    def fake_execute_battle(
        arena, cont1, cont2, era, verbose=True, battlerounds_override=None
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


def test_run_internal_battle_clamps_wardistance(monkeypatch, tmp_path, capsys):
    import evolverstage

    config = evolverstage.load_configuration(str(DEFAULT_SETTINGS_PATH))
    capsys.readouterr()
    config.base_path = str(tmp_path)
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
    monkeypatch.setattr(evolverstage, "_WARDISTANCE_CLAMP_LOGGED", set())

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
    assert fake_worker.args[9] == 4000
    assert "Clamping" in captured.out
    assert "(0-4000)" in captured.out
    assert result.strip() != ""


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
    try:
        instruction = evolverstage._apply_micro_mutation(instruction, 0, _DEFAULT_CONFIG, 0)
        assert instruction.a_field == 6

        instruction = evolverstage._apply_micro_mutation(instruction, 0, _DEFAULT_CONFIG, 0)
        assert instruction.a_field == 5

        instruction = evolverstage._apply_micro_mutation(instruction, 0, _DEFAULT_CONFIG, 0)
        assert instruction.b_field == 11

        instruction = evolverstage._apply_micro_mutation(instruction, 0, _DEFAULT_CONFIG, 0)
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
    try:
        mutated = evolverstage._apply_minor_mutation(
            base_instruction.copy(),
            arena=0,
            config=evolverstage.config,
            _magic_number=0,
        )
        assert mutated.opcode == "ADD"

        mutated = evolverstage._apply_minor_mutation(
            base_instruction.copy(),
            arena=0,
            config=evolverstage.config,
            _magic_number=0,
        )
        assert mutated.modifier == "B"

        mutated = evolverstage._apply_minor_mutation(
            base_instruction.copy(),
            arena=0,
            config=evolverstage.config,
            _magic_number=0,
        )
        assert mutated.a_mode == "#"

        mutated = evolverstage._apply_minor_mutation(
            base_instruction.copy(),
            arena=0,
            config=evolverstage.config,
            _magic_number=0,
        )
        assert mutated.a_field == 3

        mutated = evolverstage._apply_minor_mutation(
            base_instruction.copy(),
            arena=0,
            config=evolverstage.config,
            _magic_number=0,
        )
        assert mutated.b_mode == "#"

        mutated = evolverstage._apply_minor_mutation(
            base_instruction.copy(),
            arena=0,
            config=evolverstage.config,
            _magic_number=0,
        )
        assert mutated.b_field == -7
    finally:
        evolverstage.set_rng_sequence([])


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
