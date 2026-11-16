"""Restartable eight-hour search for SAL Nano against cached public proxies.

Preparation reads only local caches. Battles use pMARS -P: all 71 legal
separations in both orders, with no placement seed or sampling noise.
"""

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

from tools.tournament_multiday import TELEMETRY, RECOVERY_SECONDS, disk_ok, health


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".local/sal-nano-8h-20261116"
SAL = ROOT / "references/sal/nano/2026-11-16"
KOENIG = ROOT / "references/koenigstuhl/nano/2026-11-16"
PMARS = ROOT / ".local/corewar-prep-2026-10-28/pmars-reference/src/pmars"
OPTIONS = ("-s", "80", "-p", "80", "-c", "800", "-d", "5", "-l", "5")
INSTRUCTION = re.compile(r"^(?:DAT|MOV|ADD|SUB|MUL|DIV|MOD|JMP|JMZ|JMN|DJN|SPL|CMP|SEQ|SNE|SLT|NOP|LDP|STP)(?:\.[A-Z]+)?\s", re.I)
NUMBER = re.compile(r"[-+]?\d+")
SCORES = re.compile(r"\bscores\s+(\d+)")
LANES = 6
HOURS = 8


def save_json(path: Path, value: object) -> None:
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(pending, path)


def compiled(source: str) -> tuple[int, list[str]]:
    result = subprocess.run([str(PMARS), "-A", *OPTIONS, "-"], input=source,
                            text=True, capture_output=True, timeout=10)
    if result.returncode:
        raise ValueError(result.stderr or result.stdout)
    lines = [re.sub(r"\s+", " ", re.sub(r"([#$@<>*{}])\s+(-?\d+)",
                                      r"\1\2", line.strip()))
             for line in result.stdout.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("ORG "):
        raise ValueError(f"Unexpected assembly: {result.stdout}")
    body = [line for line in lines[1:] if INSTRUCTION.match(line)]
    entry = int(lines[0].split()[1])
    if not 1 <= len(body) <= 5 or not 0 <= entry < len(body):
        raise ValueError("Invalid Nano warrior length or entry point")
    if any(re.search(r"\b(?:LDP|STP)\b", line, re.I) for line in body):
        raise ValueError("P-space source is unsuitable for deterministic -P proxy")
    return entry, body


def warrior(body: list[str], entry: int = 0) -> str:
    return ";redcode-nano\n;assert CORESIZE == 80\n" + f"ORG {entry}\n" + "\n".join(body) + "\nEND\n"


def stored_body(path: Path) -> list[str]:
    body = [line.strip() for line in path.read_text().splitlines() if INSTRUCTION.match(line.strip())]
    if not 1 <= len(body) <= 5:
        raise ValueError(f"Invalid saved warrior: {path}")
    return body


def truncated_evolved(path: Path) -> list[str]:
    body = [line.split(";", 1)[0].strip() for line in path.read_text(errors="replace").splitlines()]
    body = [line for line in body if INSTRUCTION.match(line)][:5]
    if not body:
        raise ValueError("No assembled instructions")
    entry, body = compiled(warrior(body))
    if entry:
        raise ValueError("Evolved sample has nonzero entry point")
    return body


def battle(candidate: Path, opponent: Path) -> int:
    result = subprocess.run([str(PMARS), "-b", "-P", *OPTIONS,
                             str(candidate), str(opponent)],
                            text=True, capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError(f"pMARS rejected {candidate} vs {opponent}: {result.stderr or result.stdout}")
    values = SCORES.findall(result.stdout)
    rounds = re.search(r"Results:\s*(\d+)\s+(\d+)\s+(\d+)", result.stdout)
    if len(values) != 2 or rounds is None or sum(map(int, rounds.groups())) != 142:
        raise RuntimeError(f"Unexpected exhaustive battle output: {result.stdout}")
    return int(values[0])


def score(candidate: Path, field: list[Path]) -> float:
    return sum(battle(candidate, opponent) for opponent in field) / (142 * len(field))


def prepare() -> dict:
    state_path = RUN / "state.json"
    if state_path.exists():
        return json.loads(state_path.read_text())
    for name in ("reference_train", "reference_holdout", "evolved", "seed_pool",
                 "champions", "improvements", "scratch"):
        (RUN / name).mkdir(parents=True, exist_ok=True)
    sal_manifest = json.loads((SAL / "manifest.json").read_text())
    kg_manifest = json.loads((KOENIG / "manifest.json").read_text())
    reference_manifest = []
    known_urls = set()
    for item in sal_manifest["matched_public_sources"]:
        source = SAL / item["file"]
        entry, body = compiled(source.read_text(errors="replace"))
        dest = RUN / "reference_train" / f"{item['sal_rank']:02d}_{source.name}"
        dest.write_text(warrior(body, entry))
        reference_manifest.append({"kind": "current_SAL_public_match", "sal_rank": item["sal_rank"],
                                   "name": item["name"], "source_url": item["source_url"],
                                   "file": str(dest.relative_to(RUN)), "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()})
        known_urls.add(item["source_url"])
    for item in kg_manifest["sources"]:
        if item["url"] in known_urls:
            continue
        source = KOENIG / item["file"]
        entry, body = compiled(source.read_text(errors="replace"))
        dest = RUN / "reference_holdout" / source.name
        dest.write_text(warrior(body, entry))
        reference_manifest.append({"kind": "Koenigstuhl_holdout", "koenig_rank": item["rank"],
                                   "source_url": item["url"], "file": str(dest.relative_to(RUN)),
                                   "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()})
        if len(list((RUN / "reference_holdout").glob("*.red"))) == 10:
            break
    train = sorted((RUN / "reference_train").glob("*.red"))
    holdout = sorted((RUN / "reference_holdout").glob("*.red"))
    if len(train) < 15 or len(holdout) != 10:
        raise RuntimeError(f"Insufficient fields: {len(train)} SAL matches, {len(holdout)} holdout")
    library = sorted({line for path in train for line in compiled(path.read_text())[1]})
    (RUN / "reference_instruction_library.txt").write_text("\n".join(library) + "\n")
    save_json(RUN / "reference_manifest.json", reference_manifest)

    groups = ((ROOT / "arena0", 100), (ROOT / "arena1", 25), (ROOT / "archive", 5),
              (ROOT / ".local/tournament-multiday-20261030/arena0", 25),
              (ROOT / ".local/tournament-multiday-20261030/arena2", 25),
              (ROOT / ".local/tournament-general-12h-20261109/archive", 25))
    rng = random.Random(20261116)
    evolved_manifest = []
    seen = set()
    for directory, limit in groups:
        paths = sorted(directory.glob("*.red"))
        for source in rng.sample(paths, min(limit, len(paths))):
            try:
                body = truncated_evolved(source)
            except ValueError:
                continue
            key = tuple(body)
            if key in seen:
                continue
            seen.add(key)
            index = len(evolved_manifest)
            snapshot = RUN / "evolved" / f"{index:03d}.red"
            seed = RUN / "seed_pool" / f"{index:03d}.red"
            shutil.copy2(source, snapshot)  # Keep the original length; truncate only when retrieved.
            seed.write_text(warrior(body))
            evolved_manifest.append({"source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                                     "original_lines": len(source.read_text().splitlines()),
                                     "snapshot": str(snapshot.relative_to(RUN)), "seed": str(seed.relative_to(RUN))})
    if len(evolved_manifest) < 100:
        raise RuntimeError(f"Only {len(evolved_manifest)} usable evolved samples")
    save_json(RUN / "evolved_manifest.json", evolved_manifest)

    ranked = sorted(((score(RUN / item["seed"], train), RUN / item["seed"])
                     for item in evolved_manifest), key=lambda pair: pair[0], reverse=True)
    save_json(RUN / "seed_scores.json", [{"score": value, "file": str(path.relative_to(RUN))}
                                        for value, path in ranked])
    selected = []
    for value, path in ranked:
        lines = compiled(path.read_text())[1]
        if all(sum(a != b for a, b in zip(lines, prior)) >= 2 for prior in selected):
            selected.append(lines)
            if len(selected) == LANES:
                break
    if len(selected) < LANES:
        raise RuntimeError("Insufficient distinct evolved starting points")
    lanes = []
    for index, body in enumerate(selected):
        path = RUN / "champions" / f"lane{index}.red"
        path.write_text(warrior(body))
        lanes.append({"score": score(path, train), "attempts": 0, "accepted": 0, "stalled": 0})
    best_lane = max(range(LANES), key=lambda i: lanes[i]["score"])
    shutil.copy2(RUN / "champions" / f"lane{best_lane}.red", RUN / "champions/best.red")
    state = {"prepared_at": time.time(), "started_at": None, "deadline": None,
             "attempts": 0, "accepted": 0, "resets": 0, "lanes": lanes,
             "best_train": lanes[best_lane]["score"],
             "best_holdout": score(RUN / "champions/best.red", holdout),
             "train_count": len(train), "holdout_count": len(holdout),
             "evolved_count": len(evolved_manifest)}
    save_json(state_path, state)
    (RUN / "RUNBOOK.md").write_text(
        "# SAL Nano eight-hour search\n\n"
        "Target: SAL Nano, 80 cells, 800 cycles, 80 processes, five instructions. "
        "The live hill page is cached at `../../references/sal/nano/2026-11-16/hill.html`. "
        "Only published source can be used: the training field contains public Koenigstuhl "
        "sources with names matching current SAL warriors; live SAL source may differ. "
        "Ten other Koenigstuhl warriors are holdout. "
        "The two reference pools and the copied evolved archive are separate. Original evolved "
        "samples are preserved at their full length, with first-five-instruction seeds in `seed_pool`. "
        "Each fitness match uses pMARS `-P` for 142 deterministic rounds (all 71 legal "
        "separations in both orientations), scored as mean 3/win + 1/tie per round. "
        "The live SAL server instead uses 250 rounds and includes private warriors; this "
        "proxy cannot establish a live hill rank. No submission is made.\n\n"
        "Resume with `python -m tools.nano_hill_search` from the project root. "
        "The first launch sets an eight-hour wall deadline in `state.json`; restart preserves it. "
        "Current lane leaders and the global training leader are in `champions/`; accepted "
        "versions are in `improvements/`. Source provenance and hashes are in both manifests.\n")
    return state


def mutate(lines: list[str], donor: list[str], library: list[str], rng: random.Random) -> list[str]:
    result = lines.copy()
    index = rng.randrange(len(result))
    choice = rng.randrange(6)
    if choice == 0:
        matches = list(NUMBER.finditer(result[index]))
        if matches:
            match = rng.choice(matches)
            result[index] = result[index][:match.start()] + str(int(match.group()) + rng.choice((-13, -5, -2, -1, 1, 2, 5, 13))) + result[index][match.end():]
    elif choice == 1:
        result[index] = rng.choice(library)
    elif choice == 2:
        result[index] = rng.choice(donor)
    elif choice == 3:
        length = rng.choice((2, 3))
        result[index:index + length] = donor[index:index + length]
    elif choice == 4:
        other = rng.randrange(len(result))
        result[index], result[other] = result[other], result[index]
    else:
        result.pop(index)
        result.insert(rng.randrange(len(result) + 1), rng.choice(donor))
    return result


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
        public_bodies = {tuple(stored_body(path)) for path in train + holdout}
        for lane in range(LANES):
            state["lanes"][lane]["score"] = score(RUN / "champions" / f"lane{lane}.red", train)
        if state["started_at"] is None:
            state["started_at"] = time.time()
            state["deadline"] = state["started_at"] + HOURS * 3600
            save_json(RUN / "state.json", state)
        saved_best = score(RUN / "champions/best.red", train)
        if saved_best != state["best_train"]:
            # A restart may follow the champion copy but precede the state write.
            state["best_train"] = saved_best
            state["best_holdout"] = score(RUN / "champions/best.red", holdout)
            save_json(RUN / "state.json", state)
        rng = random.Random()
        candidate = RUN / "scratch/candidate.red"
        last_health = 0.0
        last_critical = -RECOVERY_SECONDS
        last_save = time.monotonic()
        duty, reason = 0.0, "starting"
        print("started", state["started_at"], "deadline", state["deadline"],
              "baseline", state["best_train"], "holdout", state["best_holdout"], flush=True)
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
                print("progress", state["attempts"], state["accepted"], state["resets"],
                      "best", round(state["best_train"], 5), "health", reason, flush=True)
                last_save = now
            if duty == 0 or now - last_critical < RECOVERY_SECONDS:
                time.sleep(min(15, max(0, state["deadline"] - time.time())))
                continue
            lane = rng.randrange(LANES)
            lane_state = state["lanes"][lane]
            current = RUN / "champions" / f"lane{lane}.red"
            if lane_state["stalled"] >= 2000:
                replacement = rng.choice(top_seeds)
                shutil.copy2(replacement, current)
                lane_state["score"] = score(current, train)
                lane_state["stalled"] = 0
                state["resets"] += 1
            parent = stored_body(current)
            donor = stored_body(rng.choice(donors))
            proposed = mutate(parent, donor, library, rng)
            lane_state["attempts"] += 1
            lane_state["stalled"] += 1
            state["attempts"] += 1
            if tuple(proposed) == tuple(parent) or tuple(proposed) in public_bodies:
                continue
            candidate.write_text(warrior(proposed))
            started = time.monotonic()
            value = score(candidate, train)
            elapsed = time.monotonic() - started
            if value > lane_state["score"] + 1e-12:
                shutil.copy2(candidate, current)
                lane_state["score"] = value
                lane_state["accepted"] += 1
                lane_state["stalled"] = 0
                state["accepted"] += 1
                archive = RUN / "improvements" / f"{state['attempts']:09d}.red"
                shutil.copy2(candidate, archive)
                donors.append(archive)
                if value > state["best_train"] + 1e-12:
                    shutil.copy2(candidate, RUN / "champions/best.red")
                    state["best_train"] = value
                    state["best_holdout"] = score(candidate, holdout)
                    save_json(RUN / "state.json", state)
                    print("best", state["attempts"], round(value, 5),
                          "holdout", round(state["best_holdout"], 5), flush=True)
            if duty < 1:
                time.sleep(min(2, elapsed * (1 / duty - 1)))
        state["finished_at"] = time.time()
        state["final_holdout"] = [score(RUN / "champions" / f"lane{i}.red", holdout)
                                  for i in range(LANES)]
        save_json(RUN / "state.json", state)
        print("finished", state["attempts"], state["accepted"],
              "best", state["best_train"], flush=True)


if __name__ == "__main__":
    run_search()
