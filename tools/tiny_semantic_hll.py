"""Compose labeled Tiny tactics and preserve diverse battle-behavior elites."""

from __future__ import annotations

import hashlib
from pathlib import Path
import random
import re
import time

import battle_runner
from tools.nano_hill_search import save_json
from tools.tiny_hill_search import ROOT, assemble, score


PROXY = ROOT / ".local/sal-tiny-conditional-8h-20261117"
OLD = ROOT / ".local/sal-tiny-8h-20261116"
RUN = ROOT / ".local/sal-tiny-semantic-behavior-20261117"
ARCHES = ("paper", "stone", "clear", "scan_clear", "parallel_paper_stone",
          "parallel_paper_clear", "parallel_stone_clear", "stone_then_clear")


def compile_program(g: dict) -> str:
    step = g["step"]
    offset = g["offset"]
    second = g["second"]
    count = g["count"]
    if not 1 <= step < 800 or not 20 <= offset < 780 or not 20 <= second < 780 or not 4 <= count <= 80:
        raise ValueError("parameter outside Tiny range")
    paper = ["paper spl.b @0, }" + str(offset), "mov.i }paper, >paper",
             "spl.b @0, }" + str(second), "mov.i }-1, >-1", "jmp.b paper"]
    stone = ["stone spl.b #0, >-1", "mov.i bomb, @ptr", f"add.ab #{step}, ptr",
             "jmp.b stone+1", f"ptr dat.f 0, {offset}", "bomb dat.f 0, 0"]
    clear = ["clear mov.i cbomb, >cptr", "jmp.b clear", "cbomb dat.f 0, 0",
             f"cptr dat.f 0, {offset}"]
    scan_clear = [f"scan add.ab #{step}, sptr", "jmz.f scan, @sptr", "jmp.b clear",
                  f"sptr dat.f 0, {offset}", "clear mov.i cbomb, >sptr",
                  "jmp.b clear", "cbomb dat.f 0, 0"]
    finite_stone = ["stone mov.i bomb, @ptr", f"add.ab #{step}, ptr",
                    f"djn.b stone, #{count}", "jmp.b clear", f"ptr dat.f 0, {offset}",
                    "bomb dat.f 0, 0"]
    arch = g["arch"]
    if arch == "paper":
        lines = paper
    elif arch == "stone":
        lines = stone
    elif arch == "clear":
        lines = clear
    elif arch == "scan_clear":
        lines = scan_clear
    elif arch.startswith("parallel_"):
        first, last = arch.removeprefix("parallel_").split("_")
        modules = {"paper": paper, "stone": stone, "clear": clear}
        lines = [f"entry spl.b {first}", f"jmp.b {last}"] + modules[first] + modules[last]
    elif arch == "stone_then_clear":
        lines = finite_stone + clear
    else:
        raise ValueError("unknown architecture")
    if len(lines) > 20:
        raise ValueError("program exceeds Tiny length")
    lines += ["dat.f 0, 0"] * (20 - len(lines))
    source = ";redcode-tiny\n;assert CORESIZE == 800\nORG 0\n" + "\n".join(lines) + "\nEND\n"
    entry, body = assemble(source)
    if entry != 0 or len(body) != 20:
        raise ValueError("compiler produced invalid warrior")
    return source


def random_genome(rng: random.Random) -> dict:
    return {"arch": rng.choice(ARCHES), "step": rng.randrange(7, 793),
            "offset": rng.randrange(30, 770), "second": rng.randrange(30, 770),
            "count": rng.randrange(6, 65)}


def mutate(g: dict, rng: random.Random) -> dict:
    child = g.copy()
    key = rng.choice(tuple(g))
    if key == "arch":
        child[key] = rng.choice(ARCHES)
    else:
        low, high = (4, 80) if key == "count" else ((1, 799) if key == "step" else (20, 780))
        child[key] = max(low, min(high - 1, child[key] + rng.choice((-79, -37, -13, -3, 3, 13, 37, 79))))
    return child


def behavior(source: str, worker) -> tuple[int, int, int, dict]:
    body = assemble(source)[1]
    raw = worker.analyze_strategy(("\n".join(body) + "\n").encode(), 800, 8000, 800, 800, 800, 20, 0)
    result = raw.decode()
    match = re.fullmatch(r"MAX_PROCS:(\d+) NULL_DIED:([01]) OUTSIDE:([01]) NULL_GAINED:([01])", result)
    if match is None:
        raise RuntimeError(f"Unexpected C++ behavior result: {result}")
    processes, killed, outside, gained = map(int, match.groups())
    bucket = 0 if processes == 1 else 1 if processes <= 3 else 2 if processes <= 15 else 3
    return bucket, outside, killed, {"max_processes": processes, "null_died": killed,
                                     "executed_outside": outside, "null_gained": gained}


def run() -> None:
    RUN.mkdir(exist_ok=True)
    (RUN / "candidates").mkdir(exist_ok=True)
    rng = random.Random(20261117)
    known = sorted((PROXY / "known").glob("*.red"))
    hard = sorted((PROXY / "hard_train").glob("*.red"))
    holdout = sorted((PROXY / "hard_holdout").glob("*.red"))
    if (len(known), len(hard), len(holdout)) != (11, 9, 9):
        raise RuntimeError("proxy panel changed")
    scanner = [next(p for p in hard if word in p.stem) for word in ("Serval", "doubleShock")]
    paper = [next(p for p in hard if "Desync" in p.stem), next(p for p in known if "nectar" in p.stem)]
    training = known + hard + scanner * 2 + paper * 2
    battle_runner._load_cpp_worker_library()
    worker = battle_runner._get_internal_worker_library()
    scratch = RUN / "scratch.red"
    elites: dict[tuple[int, int], tuple] = {}
    seen = set()
    started = time.time()
    for attempt in range(3000):
        g = mutate(rng.choice(list(elites.values()))[1], rng) if elites and rng.random() < 0.7 else random_genome(rng)
        source = compile_program(g)
        digest = hashlib.sha256(source.encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        scratch.write_text(source)
        placement = rng.randrange(1, 2**31)
        quality = score(scratch, rng.sample(training, 6), [placement], 60)
        *key, features = behavior(source, worker)
        key = tuple(key)
        if key not in elites or quality > elites[key][0]:
            path = RUN / "candidates" / f"{digest[:16]}.red"
            path.write_text(source)
            elites[key] = (quality, g, path, features)
        if attempt % 500 == 0:
            print("progress", attempt, len(seen), len(elites), flush=True)
    confirmed = []
    for key, (_, g, path, features) in elites.items():
        value = score(path, training, [20261119, 20261120, 20261121], 150)
        confirmed.append((value, key, g, path, features))
    confirmed.sort(reverse=True, key=lambda row: row[0])
    slate = OLD / "champions/best.red"
    seeds = [1301, 1303, 1307, 1319, 1321, 1327]
    slate_known = score(slate, known, seeds, 250)
    slate_hard = score(slate, holdout, seeds, 250)
    results = []
    for value, key, g, path, features in confirmed:
        covered = score(path, known, seeds, 250)
        difficult = score(path, holdout, seeds, 250)
        projected = 120.8 + 100 * (11 / 25 * (covered - slate_known) + 14 / 25 * (difficult - slate_hard))
        results.append({"file": str(path), "cell": key, "behavior": features,
                        "genome": g, "training": value,
                        "known": covered, "hard_holdout": difficult, "estimated_live": projected})
    results.sort(key=lambda row: row["estimated_live"], reverse=True)
    save_json(RUN / "RESULTS.json", {"started_at": started, "finished_at": time.time(),
              "unique": len(seen), "occupied_cells": len(elites), "scanner_panel": [p.name for p in scanner],
              "paper_panel": [p.name for p in paper], "seeds": seeds, "slate_known": slate_known,
              "slate_hard_holdout": slate_hard, "results": results})
    print("finished", len(seen), "cells", len(elites), "best", results[0]["estimated_live"], flush=True)


if __name__ == "__main__":
    run()
