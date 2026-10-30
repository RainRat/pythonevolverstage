"""Safety checks for the prepared long-running tournament harness."""

import configparser
import datetime as dt
import json

from tools.tournament_multiday import health, prepare


def test_preparation_is_inert_and_telemetry_fails_closed(tmp_path):
    run = tmp_path / "run"
    prepare(run)
    config = configparser.ConfigParser()
    config.read(run / "settings.ini")
    assert config["DEFAULT"]["CLOCK_TIME"] == "72"
    assert "WALL_START_EPOCH" not in config["DEFAULT"]
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
    assert health(telemetry)[0] == 1
    record["temperatureC"] = 82
    telemetry.write_text(json.dumps(record))
    assert health(telemetry)[0] == 0
    record["temperatureC"] = 60
    record["timestampUtc"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=4)).isoformat()
    telemetry.write_text(json.dumps(record))
    assert health(telemetry)[0] == 0
