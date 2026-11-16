"""Restartable SAL Tiny search against cached public sources and random placements."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import time

from tools.nano_hill_search import INSTRUCTION, PMARS, mutate, save_json
from tools.tournament_multiday import TELEMETRY, RECOVERY_SECONDS, disk_ok, health


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".local/sal-tiny-8h-20261116"
SOURCES = ROOT / "references/koenigstuhl/tiny/2026-11-16"
OPTIONS = ("-s", "800", "-p", "800", "-c", "8000", "-d", "20", "-l", "20")
SCORES = re.compile(r"\bscores\s+(\d+)")
LANES = 6
HOURS = 8


def assemble(source: str) -> tuple[int, list[str]]:
    result = subprocess.run([str(PMARS), "-A", *OPTIONS, "-"], input=source,
                            text=True, capture_output=True, timeout=10)
    if result.returncode:
        raise ValueError(result.stderr or result.stdout)
    lines = [re.sub(r"\s+", " ", re.sub(r"([#$@<>*{}])\s+(-?\d+)",
                                      r"\1\2", line.strip()))
             for line in result.stdout.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("ORG "):
        raise ValueError(f"Unexpected assembly: {result.stdout[:200]}")
    body = [line for line in lines[1:] if INSTRUCTION.match(line)]
    entry = int(lines[0].split()[1])
    if not 1 <= len(body) <= 20 or not 0 <= entry < len(body):
        raise ValueError("Invalid Tiny warrior length or entry point")
    return entry, body


def warrior(body: list[str], entry: int = 0) -> str:
    return ";redcode-tiny\n;assert CORESIZE == 800\n" + f"ORG {entry}\n" + "\n".join(body) + "\nEND\n"


def body_at(path: Path) -> list[str]:
    return assemble(path.read_text(errors="replace"))[1]


def evolved_seed(path: Path) -> list[str]:
    lines = [line.split(";", 1)[0].strip() for line in path.read_text(errors="replace").splitlines()]
    body = [line for line in lines if INSTRUCTION.match(line)][:20]
    if not body:
        raise ValueError("No instructions")
    body.extend(["DAT.F $0, $0"] * (20 - len(body)))
    entry, body = assemble(warrior(body))
    if entry:
        raise ValueError("Unexpected evolved entry point")
    return body


def battle(candidate: Path, opponent: Path, seed: int, rounds: int) -> int:
    result = subprocess.run([str(PMARS), "-b", "-r", str(rounds), "-F", str(seed),
                             *OPTIONS, str(candidate), str(opponent)],
                            text=True, capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError(f"pMARS rejected {candidate} vs {opponent}: {result.stderr or result.stdout}")
    values = SCORES.findall(result.stdout)
    counts = re.search(r"Results:\s*(\d+)\s+(\d+)\s+(\d+)", result.stdout)
    if len(values) != 2 or counts is None or sum(map(int, counts.groups())) != rounds:
        raise RuntimeError(f"Unexpected battle output: {result.stdout}")
    return int(values[0])


def score(path: Path, opponents: list[Path], seeds: list[int], rounds: int) -> float:
    return sum(battle(path, opponent, seed, rounds) for opponent in opponents for seed in seeds) / (rounds * len(opponents) * len(seeds))


def prepare() -> dict:
    state_path = RUN / "state.json"
    if state_path.exists():
        return json.loads(state_path.read_text())
    for name in ("reference_train", "reference_holdout", "evolved", "seed_pool",
                 "champions", "improvements", "scratch"):
        (RUN / name).mkdir(parents=True, exist_ok=True)
    source_manifest = json.loads((SOURCES / "manifest.json").read_text())
    reference_manifest = []
    library = set()
    for item in source_manifest["sources"]:
        source = SOURCES / item["file"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError(f"Cached source hash changed: {source}")
        entry, body = assemble(source.read_text(errors="replace"))
        target = RUN / ("reference_holdout" if item["kind"] == "kg_holdout" else "reference_train") / source.name
        target.write_text(warrior(body, entry))
        reference_manifest.append({**item, "run_file": str(target.relative_to(RUN))})
        if item["kind"] != "kg_holdout":
            library.update(body)
    save_json(RUN / "reference_manifest.json", reference_manifest)
    (RUN / "reference_instruction_library.txt").write_text("\n".join(sorted(library)) + "\n")
    groups = ((ROOT / "arena0", 100), (ROOT / "arena1", 100), (ROOT / "archive", 5),
              (ROOT / ".local/tournament-multiday-20261030/arena0", 50),
              (ROOT / ".local/tournament-multiday-20261030/arena2", 50),
              (ROOT / ".local/tournament-general-12h-20261109/archive", 50))
    rng = random.Random(20261116)
    seen = set()
    evolved_manifest = []
    for directory, limit in groups:
        paths = sorted(directory.glob("*.red"))
        for source in rng.sample(paths, min(limit, len(paths))):
            try:
                body = evolved_seed(source)
            except ValueError:
                continue
            key = tuple(body)
            if key in seen:
                continue
            seen.add(key)
            number = len(evolved_manifest)
            snapshot = RUN / "evolved" / f"{number:03d}.red"
            seed_path = RUN / "seed_pool" / f"{number:03d}.red"
            shutil.copy2(source, snapshot)
            seed_path.write_text(warrior(body))
            evolved_manifest.append({"source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                                     "snapshot": str(snapshot.relative_to(RUN)), "seed": str(seed_path.relative_to(RUN))})
    if len(evolved_manifest) < 100:
        raise RuntimeError(f"Only {len(evolved_manifest)} usable evolved samples")
    save_json(RUN / "evolved_manifest.json", evolved_manifest)
    train = sorted((RUN / "reference_train").glob("*.red"))
    holdout = sorted((RUN / "reference_holdout").glob("*.red"))
    if len(train) != 25 or len(holdout) != 10:
        raise RuntimeError(f"Unexpected field sizes: {len(train)} train, {len(holdout)} holdout")
    field = rng.sample(train, 12)
    ranked = sorted(((score(RUN / item["seed"], field, [33891], 60), RUN / item["seed"])
                     for item in evolved_manifest), key=lambda pair: pair[0], reverse=True)
    save_json(RUN / "seed_scores.json", [{"score": value, "file": str(path.relative_to(RUN))} for value, path in ranked])
    selected = []
    for _, path in ranked:
        body = body_at(path)
        if all(sum(a != b for a, b in zip(body, prior)) >= 4 for prior in selected):
            selected.append(body)
            if len(selected) == LANES:
                break
    if len(selected) != LANES:
        raise RuntimeError("Insufficient distinct starting warriors")
    lanes = []
    for index, body in enumerate(selected):
        path = RUN / "champions" / f"lane{index}.red"
        path.write_text(warrior(body))
        lanes.append({"attempts": 0, "accepted": 0, "stalled": 0})
    shutil.copy2(RUN / "champions/lane0.red", RUN / "champions/best.red")
    state = {"prepared_at": time.time(), "started_at": None, "deadline": None,
             "attempts": 0, "accepted": 0, "resets": 0, "lanes": lanes,
             "best_train": None, "best_holdout": None,
             "train_count": len(train), "holdout_count": len(holdout),
             "evolved_count": len(evolved_manifest)}
    save_json(state_path, state)
    (RUN / "RUNBOOK.md").write_text(
        "# SAL Tiny eight-hour search\n\nTarget: 800 cells, 8000 cycles, 800 processes, "
        "20 instructions. The training field has 11 public-source name matches to the live "
        "25-slot SAL hill plus 14 other Koenigstuhl warriors. A name match does not prove "
        "the live source is identical. Ten other Koenigstuhl warriors are untouched holdout. "
        "Original evolved samples are kept in `evolved/`; their first 20 instructions, "
        "padded with DAT.F $0, $0, are in `seed_pool/`. References remain separate. "
        "Fitness uses pMARS `-F` random placements, never exhaustive `-P`: a rotating "
        "screen of eight opponents and a separate full-field confirmation with fresh seeds. "
        "The holdout does not decide acceptance. SAL itself uses 250 rounds and private "
        "warriors; this proxy cannot establish live rank. No submission is made.\n\n"
        "Resume with `python -m tools.tiny_hill_search` from the project root. First launch "
        "sets the eight-hour wall deadline in `state.json`. Champions and all accepted "
        "versions are retained. Cache provenance is in both manifests.\n")
    return state


def run_search() -> None:
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / "supervisor.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = prepare()
        if not disk_ok(RUN):
            raise RuntimeError("Insufficient disk space")
        train = sorted((RUN / "reference_train").glob("*.red"))
        holdout = sorted((RUN / "reference_holdout").glob("*.red"))
        library = (RUN / "reference_instruction_library.txt").read_text().splitlines()
        donors = sorted((RUN / "seed_pool").glob("*.red")) + sorted((RUN / "improvements").glob("*.red"))
        top_seeds = [RUN / item["file"] for item in json.loads((RUN / "seed_scores.json").read_text())[:50]]
        public_bodies = {tuple(body_at(path)) for path in train + holdout}
        rng = random.Random()
        if state["started_at"] is None:
            state["started_at"] = time.time()
            state["deadline"] = state["started_at"] + HOURS * 3600
            save_json(RUN / "state.json", state)
        candidate = RUN / "scratch/candidate.red"
        last_health = 0.0
        last_critical = -RECOVERY_SECONDS
        last_save = time.monotonic()
        duty, reason = 0.0, "starting"
        print("started", state["started_at"], "deadline", state["deadline"], flush=True)
        while time.time() < state["deadline"]:
            now = time.monotonic()
            if now - last_health >= 30:
                duty, reason = health(TELEMETRY)
                last_health = now
                if duty == 0:
                    last_critical = now
            if now - last_save >= 300:
                if not disk_ok(RUN):
                    raise RuntimeError("Disk limit reached")
                save_json(RUN / "state.json", state)
                print("progress", state["attempts"], state["accepted"], state["resets"], "health", reason, flush=True)
                last_save = now
            if duty == 0 or now - last_critical < RECOVERY_SECONDS:
                time.sleep(min(15, max(0, state["deadline"] - time.time())))
                continue
            lane = rng.randrange(LANES)
            lane_state = state["lanes"][lane]
            current = RUN / "champions" / f"lane{lane}.red"
            if lane_state["stalled"] >= 2000:
                shutil.copy2(rng.choice(top_seeds), current)
                lane_state["stalled"] = 0
                state["resets"] += 1
            parent = body_at(current)
            donor = body_at(rng.choice(donors))
            proposed = mutate(parent, donor, library, rng)
            lane_state["attempts"] += 1
            lane_state["stalled"] += 1
            state["attempts"] += 1
            if tuple(proposed) == tuple(parent) or tuple(proposed) in public_bodies:
                continue
            candidate.write_text(warrior(proposed))
            field = rng.sample(train, 8)
            screen_seeds = [rng.randrange(1, 2**31)]
            started = time.monotonic()
            try:
                screen_candidate = score(candidate, field, screen_seeds, 60)
            except (ValueError, RuntimeError):
                continue
            screen_parent = score(current, field, screen_seeds, 60)
            if screen_candidate > screen_parent + 0.04:
                confirm_seeds = [rng.randrange(1, 2**31) for _ in range(2)]
                confirmed = score(candidate, train, confirm_seeds, 100)
                baseline = score(current, train, confirm_seeds, 100)
                if confirmed > baseline + 0.01:
                    shutil.copy2(candidate, current)
                    lane_state["accepted"] += 1
                    lane_state["stalled"] = 0
                    state["accepted"] += 1
                    archived = RUN / "improvements" / f"{state['attempts']:09d}.red"
                    shutil.copy2(candidate, archived)
                    donors.append(archived)
                    promotion_seeds = [rng.randrange(1, 2**31) for _ in range(3)]
                    best = RUN / "champions/best.red"
                    best_score = score(best, train, promotion_seeds, 150)
                    trial_score = score(candidate, train, promotion_seeds, 150)
                    if trial_score > best_score + 0.01:
                        shutil.copy2(candidate, best)
                        state["best_train"] = trial_score
                        state["best_holdout"] = score(best, holdout, [rng.randrange(1, 2**31)], 150)
                        save_json(RUN / "state.json", state)
                        print("best", state["attempts"], round(trial_score, 4), "holdout", round(state["best_holdout"], 4), flush=True)
            elapsed = time.monotonic() - started
            if duty < 1:
                time.sleep(min(2, elapsed * (1 / duty - 1)))
        state["finished_at"] = time.time()
        state["final_holdout"] = [score(RUN / "champions" / f"lane{i}.red", holdout,
                                          [190711, 498821], 250) for i in range(LANES)]
        save_json(RUN / "state.json", state)
        print("finished", state["attempts"], state["accepted"], flush=True)


if __name__ == "__main__":
    run_search()
