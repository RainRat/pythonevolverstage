"""Detached, bounded Optuna search for the 2026 94nop tournament profile."""

from __future__ import annotations

import argparse
import configparser
import csv
import ctypes
import json
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import optuna


ROOT = Path(__file__).resolve().parent
SOURCE_BENCHMARKS = ROOT / "bench" / "arena1"
OUTPUT = ROOT / "optuna_trials"
PROFILE_INDEX = 4  # 94nop: 8000 core, 8000 processes, 80000 cycles
POPULATION = 64
MAX_TRIALS = 100  # The active-time deadline is the usual stopping limit.
SEARCH_SECONDS = 9 * 3600
TRIAL_EVOLUTION_HOURS = 0.1  # Six minutes; evaluation is separate.
TRIAL_TIMEOUT_SECONDS = 15 * 60
VALIDATION_TIMEOUT_SECONDS = 10 * 60
BENCHMARK_SEED = 20261028
EVOLUTION_SEED = 407

PROFILE_KEYS = (
    "CORESIZE_LIST", "SANITIZE_LIST", "READLIMIT_LIST", "WRITELIMIT_LIST",
    "CYCLES_LIST", "PROCESSES_LIST", "WARDISTANCE_LIST", "SPEC_LIST",
)
SEARCH_RANGES = {
    "BATTLEROUNDS_LIST": ((2, 8), (8, 32), (16, 64)),
    "RANDOM_PAIR_BATTLE_FREQUENCY_LIST": ((40, 120), (10, 60), (1, 20)),
    "CHAMPION_BATTLE_FREQUENCY_LIST": ((5, 30), (10, 50), (5, 30)),
    "CROSSOVERRATE_LIST": ((4, 24), (4, 24), (4, 24)),
}


def benchmark_files() -> tuple[list[tuple[str, bytes]], list[tuple[str, bytes]]]:
    files = sorted(SOURCE_BENCHMARKS.glob("*.red"))
    if len(files) < 20:
        raise RuntimeError(f"Need at least 20 benchmark warriors in {SOURCE_BENCHMARKS}")
    worker_path = ROOT / "redcode_worker.so"
    if not worker_path.is_file():
        raise RuntimeError(f"Build the internal worker before launch: {worker_path}")
    worker = ctypes.CDLL(str(worker_path))
    worker.run_battle.argtypes = [ctypes.c_char_p, ctypes.c_int] * 2 + [ctypes.c_int] * 10
    worker.run_battle.restype = ctypes.c_char_p
    normalized = []
    for path in files:
        code = path.read_bytes().replace(b"\r\n", b"\n")
        result = worker.run_battle(
            code, 1, b"DAT.F #0, #0\n", 2,
            8000, 80000, 8000, 8000, 8000, 100, 100, 1, 12345, 0,
        ).decode()
        if result.startswith("ERROR:"):
            raise RuntimeError(f"Invalid benchmark {path.name}: {result.strip()}")
        normalized.append((path.name, code))
    random.Random(BENCHMARK_SEED).shuffle(normalized)
    return normalized[:12], normalized[12:20]


def snapshot_benchmarks(session: Path, train: list[tuple[str, bytes]], holdout: list[tuple[str, bytes]]) -> None:
    for group, files in (("train", train), ("holdout", holdout)):
        target = session / "benchmarks" / group / "arena0"
        target.mkdir(parents=True)
        for name, code in files:
            (target / name).write_bytes(code)
    (session / "benchmark_manifest.json").write_text(json.dumps({
        "source": str(SOURCE_BENCHMARKS),
        "train": [name for name, _ in train],
        "holdout": [name for name, _ in holdout],
        "normalization": "CRLF to LF; source files unchanged",
    }, indent=2) + "\n")


def write_settings(run_dir: Path, benchmarks: Path, *, trial: optuna.Trial | None, evaluation: bool,
                   source: Path | None = None) -> Path:
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(ROOT / "settings.ini")
    defaults = config["DEFAULT"]
    for key in PROFILE_KEYS:
        defaults[key] = defaults[key].split(",")[PROFILE_INDEX].strip()
    defaults["LAST_ARENA"] = "0"
    defaults["ARENA_WEIGHT_LIST"] = "1"
    defaults["WARLEN_LIST"] = "100" if evaluation else "50"
    defaults["NUMWARRIORS"] = str(POPULATION)
    defaults["IN_MEMORY_ARENAS"] = "False"
    defaults["ARCHIVE_PATH"] = "archive"
    defaults["NAB_LIST"] = "0,0,0"  # There is only one arena.
    defaults["LIBRARY_LIST"] = "0,0,0"  # No instruction library is supplied.
    defaults["BENCHMARK_BATTLE_FREQUENCY_LIST"] = "0,0,0"
    defaults["BENCHMARK_ROOT"] = str(benchmarks)
    defaults["FINAL_TOURNAMENT_CSV"] = "final_tournament.csv" if evaluation else ""
    defaults["RUN_FINAL_TOURNAMENT"] = str(evaluation)
    defaults["BENCHMARK_FINAL_TOURNAMENT"] = str(evaluation)
    defaults["FINAL_TOURNAMENT_ONLY"] = str(evaluation)
    defaults["CLOCK_TIME"] = str(TRIAL_EVOLUTION_HOURS)
    if source:
        previous = configparser.ConfigParser()
        previous.optionxform = str
        previous.read(source)
        for key in SEARCH_RANGES:
            defaults[key] = previous["DEFAULT"][key]
    elif trial:
        for key, ranges in SEARCH_RANGES.items():
            defaults[key] = ",".join(str(trial.suggest_int(f"{key}_ERA{era}", *bounds))
                                     for era, bounds in enumerate(ranges, 1))
    if evaluation:
        defaults["BATTLEROUNDS_LIST"] = "24,24,24"
    path = run_dir / ("evaluation.ini" if evaluation else "evolution.ini")
    with path.open("w") as handle:
        config.write(handle)
    return path


def run_evolver(config: Path, log: Path, timeout: int) -> None:
    with log.open("w") as handle:
        subprocess.run([sys.executable, str(ROOT / "evolverstage.py"), "--config", str(config),
                        "--seed", str(EVOLUTION_SEED), "--verbosity", "terse"],
                       cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, check=True, timeout=timeout)


def score(csv_path: Path) -> float:
    with csv_path.open(newline="") as handle:
        scores = sorted((float(row["score"]) for row in csv.DictReader(handle)), reverse=True)
    if len(scores) < 3:
        raise RuntimeError(f"Fewer than three warriors in {csv_path}")
    return mean(scores[:3])


def trial_result(trial: optuna.Trial, session: Path) -> float:
    trial_dir = session / f"trial_{trial.number:04d}"
    trial_dir.mkdir()  # A repeated trial number must never erase previous data.
    (trial_dir / "arena0").mkdir()
    (trial_dir / "archive").mkdir()
    train = session / "benchmarks" / "train"
    evolution = write_settings(trial_dir, train, trial=trial, evaluation=False)
    run_evolver(evolution, trial_dir / "evolution.log", TRIAL_TIMEOUT_SECONDS)
    evaluation = write_settings(trial_dir, train, trial=trial, evaluation=True, source=evolution)
    run_evolver(evaluation, trial_dir / "evaluation.log", TRIAL_TIMEOUT_SECONDS)
    value = score(trial_dir / "final_tournament.csv")
    with (trial_dir / "final_tournament.csv").open(newline="") as handle:
        winner = max(csv.DictReader(handle), key=lambda row: float(row["score"]))
    shutil.copyfile(trial_dir / "arena0" / f"{winner['warrior_id']}.red", trial_dir / "best_warrior.red")
    return value


def validate_best(session: Path, study: optuna.Study) -> list[dict[str, float | int]]:
    top = sorted((t for t in study.trials if t.value is not None),
                 key=lambda t: t.value, reverse=True)[:5]
    if not top:
        raise RuntimeError("No trials completed; inspect the trial logs before restarting")
    results = []
    for trial in top:
        original = session / f"trial_{trial.number:04d}"
        target = session / "validation" / f"trial_{trial.number:04d}"
        target.mkdir(parents=True)
        shutil.copytree(original / "arena0", target / "arena0")
        (target / "archive").mkdir()
        config = write_settings(target, session / "benchmarks" / "holdout", trial=None,
                                evaluation=True, source=original / "evolution.ini")
        try:
            run_evolver(config, target / "evaluation.log", VALIDATION_TIMEOUT_SECONDS)
            value = score(target / "final_tournament.csv")
            results.append({"trial": trial.number, "training_score": trial.value, "holdout_score": value})
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            results.append({"trial": trial.number, "training_score": trial.value, "error": str(exc)})
    return results


def run_session(session: Path) -> None:
    train, holdout = benchmark_files()
    snapshot_benchmarks(session, train, holdout)
    study = optuna.create_study(direction="maximize", study_name="94nop",
                                storage=f"sqlite:///{session / 'study.db'}")

    optimize_study(study, session)
    results = validate_best(session, study)
    (session / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"Finished {len(study.trials)} trials; results: {session / 'results.json'}", flush=True)


def optimize_study(study: optuna.Study, session: Path) -> None:
    # CLOCK_MONOTONIC excludes laptop suspend time on Linux; Optuna's timeout does not.
    started = time.monotonic()
    for _ in range(MAX_TRIALS):
        if time.monotonic() - started >= SEARCH_SECONDS:
            break
        study.optimize(lambda trial: trial_result(trial, session), n_trials=1,
                       catch=(OSError, RuntimeError, subprocess.SubprocessError))
        if len(study.trials) >= 3 and all(
            t.state == optuna.trial.TrialState.FAIL for t in study.trials[-3:]
        ):
            break


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate benchmarks without running evolution")
    parser.add_argument("--launch", action="store_true", help="Start a detached overnight session")
    parser.add_argument("--session", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check:
        train, holdout = benchmark_files()
        print(f"Validated {len(train) + len(holdout)} selected benchmarks from {SOURCE_BENCHMARKS}")
        return
    if args.session:
        run_session(args.session)
        return
    if not args.launch:
        parser.error("Use --check or --launch")
    benchmark_files()  # Fail before detaching if the inputs cannot run.
    OUTPUT.mkdir(exist_ok=True)
    session = OUTPUT / ("overnight_94nop_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    session.mkdir()  # Never reuse old Optuna output.
    with (session / "optimizer.log").open("w") as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--session", str(session)],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    (session / "pid").write_text(f"{process.pid}\n")
    print(f"Started PID {process.pid}; session: {session}")


if __name__ == "__main__":
    main()
