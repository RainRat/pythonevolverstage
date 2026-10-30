"""Safety checks for the prepared long-running tournament harness."""

import configparser
import datetime as dt
import json
from types import SimpleNamespace

import engine
from tools import tournament_multiday as multiday


def test_preparation_is_inert_and_telemetry_fails_closed(tmp_path, monkeypatch):
    run = tmp_path / "run"
    source = tmp_path / "source-instructions.txt"
    source.write_text("MOV.I $0, $1\n")
    monkeypatch.setattr(multiday, "LIBRARY_SOURCE", source)
    multiday.prepare(run)
    config = configparser.ConfigParser()
    config.read(run / "settings.ini")
    assert config["DEFAULT"]["CLOCK_TIME"] == "72"
    assert "WALL_START_EPOCH" not in config["DEFAULT"]
    assert config["DEFAULT"]["LIBRARY_LIST"] == "2,1,0"
    assert (run / "instructions.txt").read_text() == source.read_text()
    assert not list(run.glob("arena*"))

    telemetry = tmp_path / "telemetry.json"
    record = {
        "timestampUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "temperatureAvailable": True,
        "temperatureC": 60,
        "resources": {"cpuLoadPercent": 10, "memoryAvailableMB": 10000,
                      "memoryUsedPercent": 40},
        "power": {"acOnline": True, "batteryPercent": 100},
    }
    telemetry.write_text(json.dumps(record))
    assert multiday.health(telemetry)[0] == 1
    record["temperatureC"] = 82
    telemetry.write_text(json.dumps(record))
    assert multiday.health(telemetry)[0] == 0
    record["temperatureC"] = 60
    record["timestampUtc"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=4)).isoformat()
    telemetry.write_text(json.dumps(record))
    assert multiday.health(telemetry)[0] == 0


def test_library_mutation_uses_88_compatible_subset(tmp_path, monkeypatch):
    library = tmp_path / "instructions.txt"
    library.write_text("SNE.I $1, $2\nMOV.I $0, $1\n")
    monkeypatch.setattr(engine, "_LIBRARY_CACHE", None)
    monkeypatch.setattr(engine, "_LIBRARY_CACHE_88", [])
    monkeypatch.setattr(engine, "_LIBRARY_CACHE_PATH", None)
    monkeypatch.setattr(engine, "_rng_choice", lambda choices: choices[0])
    monkeypatch.setattr(engine, "get_arena_spec", lambda arena: "1988")
    mutation = engine.InstructionLibraryMutation()
    config = SimpleNamespace(library_path=str(library))
    assert mutation.apply(engine.default_instruction(), 0, config, 0).opcode == "MOV"
    monkeypatch.setattr(engine, "get_arena_spec", lambda arena: "1994")
    assert mutation.apply(engine.default_instruction(), 0, config, 0).opcode == "SNE"
