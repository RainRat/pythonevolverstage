"""Prepare or run a restartable four-event evolution under host telemetry.

Preparation never starts evolution. Run explicitly with --run; repeat the same
command after a reboot to continue from the saved wall-clock origin and arenas.
"""

from __future__ import annotations

import argparse
import configparser
import ctypes
import datetime as dt
import fcntl
import gzip
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import time


ROOT = Path(__file__).resolve().parents[1]
TELEMETRY = Path("/mnt/c/Temp/fuzz-host-telemetry.json")
SAMPLE_SECONDS = 30
SEGMENT_SECONDS = 3600
RUN_HOURS = 72


def prepare(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    target = run / "settings.ini"
    config = configparser.ConfigParser()
    config.read(ROOT / "settings.ini")
    values = config["DEFAULT"]
    values.update({
        "LAST_ARENA": "3",
        "CORESIZE_LIST": "8000,55440,8000,8000",
        "SANITIZE_LIST": "8000,55440,8000,8000",
        "READLIMIT_LIST": "8000,55440,8000,8000",
        "WRITELIMIT_LIST": "8000,55440,8000,8000",
        "CYCLES_LIST": "80000,500000,80000,80000",
        "PROCESSES_LIST": "8,10000,8000,8000",
        "WARLEN_LIST": "50,50,50,50",
        "WARDISTANCE_LIST": "200,200,100,100",
        "SPEC_LIST": "1994,1994,1988,1994",
        "ARENA_WEIGHT_LIST": "1,1,1,1",
        "NUMWARRIORS": "500",
        "CLOCK_TIME": str(RUN_HOURS),
        "IN_MEMORY_ARENAS": "True",
        "ARENA_CHECKPOINT_INTERVAL": "1000",
        "BATTLE_LOG_FILE": "",
        "BENCHMARK_LOG_FILE": "",
        "RUN_FINAL_TOURNAMENT": "False",
        "BENCHMARK_FINAL_TOURNAMENT": "False",
        "BATTLEROUNDS_LIST": "3,8,24",
        "CHAMPION_BATTLE_FREQUENCY_LIST": "20,60,35",
        "RANDOM_PAIR_BATTLE_FREQUENCY_LIST": "80,40,65",
        "CROSSOVERRATE_LIST": "24,4,19",
        "NAB_LIST": "1,1,1",
        "LIBRARY_LIST": "0,0,0",
        "LIBRARY_PATH": "",
    })
    from io import StringIO
    buffer = StringIO()
    config.write(buffer)
    content = buffer.getvalue()
    if target.exists() and target.read_text() != content:
        raise RuntimeError(f"Refusing to replace existing run config: {target}")
    target.write_text(content)
    print(f"Prepared {target}; no evolution process started")


def health(path: Path) -> tuple[float, str]:
    """Return duty cycle using the existing fuzz supervisor's calibrated limits."""
    try:
        data = json.loads(path.read_text())
        stamp = dt.datetime.fromisoformat(data["timestampUtc"].replace("Z", "+00:00"))
        age = (dt.datetime.now(dt.timezone.utc) - stamp).total_seconds()
        temp = float(data["temperatureC"])
        memory = data["resources"]
        available = float(memory["memoryAvailableMB"])
        used = memory.get("memoryUsedPercent")
        load = memory.get("cpuLoadPercent")
        power = data.get("power") or {}
        if age < -10 or age > 180 or not data.get("temperatureAvailable"):
            return 0, "telemetry stale or temperature unavailable"
        used = float(used) if used is not None else 0
        load = float(load) if load is not None else None
        if not all(math.isfinite(value) for value in (temp, available, used)) or (load is not None and not math.isfinite(load)):
            return 0, "invalid host telemetry"
        if temp >= 82 or available <= 1800 or used >= 92 or (load is not None and load >= 97):
            return 0, "critical host pressure"
        battery = power.get("batteryPercent")
        if power.get("acOnline") is False and battery is not None and float(battery) < 40:
            return 0, "battery below 40%"
        if temp >= 76 or available <= 3000 or used >= 88 or (load is not None and load >= 90):
            return 0.5, "high host pressure"
        if temp >= 70 or available <= 4000 or used >= 85 or (load is not None and load >= 75):
            return 0.75, "moderate host pressure"
        if power.get("acOnline") is False or load is None:
            return 0.5, "battery power or CPU load unavailable"
        return 1.0, "healthy"
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return 0, f"telemetry unavailable: {error}"


def disk_ok(run: Path) -> bool:
    if shutil.disk_usage(run).free < 20 * 1024**3:
        return False
    if Path("/mnt/c").exists() and shutil.disk_usage("/mnt/c").free < 20 * 1024**3:
        return False
    total = sum(path.stat().st_size for path in run.rglob("*") if path.is_file())
    return total < 2 * 1024**3


def rotate_logs(run: Path) -> None:
    logs = run / "logs"
    for path in logs.glob("segment-*.log"):
        compressed = path.with_suffix(".log.gz")
        with path.open("rb") as source, gzip.open(compressed, "wb") as output:
            shutil.copyfileobj(source, output)
        path.unlink()
    for path in sorted(logs.glob("segment-*.log.gz"))[:-12]:
        path.unlink()


def snapshot(run: Path, day: int) -> None:
    target = run / "snapshots" / f"day-{day}.tar.gz"
    if target.exists():
        return
    target.parent.mkdir(exist_ok=True)
    pending = target.with_suffix(".pending")
    with tarfile.open(pending, "w:gz") as archive:
        for path in sorted(run.glob("arena[0-3]")):
            archive.add(path, arcname=path.name)
        state = run / "evolution_state.json"
        if state.exists():
            archive.add(state, arcname=state.name)
    os.replace(pending, target)


def _exit_with_parent() -> None:
    # Linux stops the worker if the supervisor disappears unexpectedly.
    ctypes.CDLL(None).prctl(1, signal.SIGTERM)


def run_evolution(run: Path, telemetry: Path) -> None:
    settings = run / "settings.ini"
    if not settings.is_file():
        raise FileNotFoundError(f"Prepare first: {settings}")
    lock = (run / "supervisor.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    config = configparser.ConfigParser()
    config.read(settings)
    values = config["DEFAULT"]
    hours = float(values["CLOCK_TIME"])
    resuming = "WALL_START_EPOCH" in values
    if "WALL_START_EPOCH" not in values:
        duty, reason = health(telemetry)
        if duty == 0:
            raise RuntimeError(f"Cannot start: {reason}")
        values["WALL_START_EPOCH"] = str(time.time())
        pending = settings.with_suffix(".pending")
        with pending.open("w") as handle:
            config.write(handle)
        os.replace(pending, settings)
    start = float(values["WALL_START_EPOCH"])
    deadline = start + hours * 3600
    if time.time() >= deadline:
        print("Wall-clock deadline has passed; run is complete")
        return
    (run / "logs").mkdir(exist_ok=True)
    rotate_logs(run)
    # A restarted supervisor waits through the existing ten-minute safety hold.
    last_critical = time.time() if resuming else 0.0
    segment = 0
    while time.time() < deadline:
        if not disk_ok(run):
            raise RuntimeError("Disk budget exceeded; arenas preserved")
        duty, reason = health(telemetry)
        if duty == 0:
            last_critical = time.time()
            print(f"Waiting: {reason}", flush=True)
            time.sleep(SAMPLE_SECONDS)
            continue
        if time.time() - last_critical < 600:
            print("Waiting for ten minutes of safe telemetry", flush=True)
            time.sleep(SAMPLE_SECONDS)
            continue
        segment += 1
        log = run / "logs" / f"segment-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{segment}.log"
        segment_end = min(time.time() + SEGMENT_SECONDS, deadline)
        with log.open("w") as output:
            child = subprocess.Popen(
                [sys.executable, str(ROOT / "evolverstage.py"), "--config", str(settings),
                 "--seed", str(int(start) + segment), "--verbosity", "terse"],
                cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                preexec_fn=_exit_with_parent,
            )
            stopped = False
            try:
                while child.poll() is None and time.time() < segment_end:
                    duty, reason = health(telemetry)
                    if duty == 0:
                        last_critical = time.time()
                    if duty == 0 or time.time() - last_critical < 600:
                        if not stopped:
                            child.send_signal(signal.SIGSTOP)
                            stopped = True
                        time.sleep(SAMPLE_SECONDS)
                        continue
                    if stopped:
                        child.send_signal(signal.SIGCONT)
                        stopped = False
                    time.sleep(min(SAMPLE_SECONDS * duty, max(0, segment_end - time.time())))
                    if duty < 1 and child.poll() is None:
                        child.send_signal(signal.SIGSTOP)
                        stopped = True
                        time.sleep(min(SAMPLE_SECONDS * (1 - duty), max(0, segment_end - time.time())))
                planned_stop = child.poll() is None
            finally:
                if child.poll() is None:
                    if stopped:
                        child.send_signal(signal.SIGCONT)
                    child.send_signal(signal.SIGINT)
                    try:
                        child.wait(timeout=60)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
            if child.returncode != 0:
                raise RuntimeError(f"Evolution exited {child.returncode}; inspect {log}")
            if not planned_stop and time.time() < deadline:
                raise RuntimeError(f"Evolution exited before deadline; inspect {log}")
        rotate_logs(run)
        elapsed_days = int((time.time() - start) // 86400)
        if elapsed_days > 0:
            snapshot(run, elapsed_days)
        print(f"Checkpointed segment {segment}; {max(0, deadline - time.time()) / 3600:.1f} wall hours remain", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--run", action="store_true")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--telemetry", type=Path, default=TELEMETRY)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    if args.prepare:
        prepare(run)
    else:
        run_evolution(run, args.telemetry)


if __name__ == "__main__":
    main()
