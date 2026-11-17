"""Block-level structural search using evolved Tiny warriors as scaffolds."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import time

from tools.nano_hill_search import save_json
from tools.tiny_hill_search import ROOT, assemble, body_at, score, warrior


OLD = ROOT / ".local/sal-tiny-8h-20261116"
PROXY = ROOT / ".local/sal-tiny-conditional-8h-20261117"
RUN = ROOT / ".local/sal-tiny-hll-rich-20261117"
NUMBER = re.compile(r"(?<=[#$@<>*{}])(-?\d+)")
BLOCKS = {"launch": (0, 3), "engine": (3, 9), "tail": (9, 20)}


def retarget(lines: list[str], delta: int, field: str) -> list[str]:
    output = []
    for line in lines:
        parts = line.split(",", 1)
        index = 0 if field == "a" else 1
        if len(parts) > index and line.startswith(("MOV", "SPL", "DJN", "JMP")):
            parts[index] = NUMBER.sub(lambda match: str(int(match.group()) + delta), parts[index], count=1)
        output.append(",".join(parts))
    return output


def compile_genome(genome: dict, bodies: list[list[str]]) -> str:
    body = bodies[genome["base"]].copy()
    for name in ("launch", "engine", "tail"):
        start, end = BLOCKS[name]
        block = bodies[genome[name]][start:end]
        body[start:end] = retarget(block, genome[f"{name}_delta"], genome["field"])
    if genome["flow"] == "parallel_clear":
        start = genome["clear_start"]
        clear = ["MOV.I $2, >3", "JMP.B $-1, $0", "DAT.F $0, $0", f"DAT.F $0, ${start}"]
        body = ["SPL.B $2, $0", "JMP.B $15, $0"] + body[:14] + clear
    elif genome["flow"] != "inherited":
        raise ValueError("unknown flow")
    source = warrior(body)
    entry, normalized = assemble(source)
    if entry != 0 or len(normalized) != 20:
        raise ValueError("invalid compiled genome")
    return source


def random_genome(rng: random.Random, count: int) -> dict:
    g = {"base": rng.randrange(count), "field": rng.choice(("a", "b")),
         "flow": rng.choices(("inherited", "parallel_clear"), (9, 1))[0],
         "clear_start": rng.randrange(32, 768)}
    for name in BLOCKS:
        g[name] = g["base"] if rng.random() < 0.65 else rng.randrange(count)
        g[f"{name}_delta"] = rng.choice((0, 0, 0, -13, -5, -1, 1, 5, 13))
    return g


def mutate_genome(parent: dict, rng: random.Random, count: int) -> dict:
    g = parent.copy()
    key = rng.choice(("base", "launch", "engine", "tail", "launch_delta", "engine_delta",
                      "tail_delta", "field", "flow", "clear_start"))
    if key in ("base", "launch", "engine", "tail"):
        g[key] = rng.randrange(count)
    elif key.endswith("delta") or key == "clear_start":
        g[key] += rng.choice((-37, -13, -5, -1, 1, 5, 13, 37))
    elif key == "field":
        g[key] = "b" if g[key] == "a" else "a"
    else:
        g[key] = "inherited" if g[key] == "parallel_clear" else "parallel_clear"
    return g


def run() -> None:
    RUN.mkdir(exist_ok=True)
    (RUN / "candidates").mkdir(exist_ok=True)
    (RUN / "intake").mkdir(exist_ok=True)
    rng = random.Random(20261118)
    sources = [OLD / "champions/best.red"] + sorted((OLD / "champions").glob("lane*.red"))
    sources += sorted((PROXY / "champions").glob("lane*.red"))
    improvements = sorted((OLD / "improvements").glob("*.red"))
    sources += [improvements[i] for i in range(0, len(improvements), max(1, len(improvements) // 30))][:30]
    bodies = [body_at(p) for p in sources]
    if any(len(body) != 20 for body in bodies):
        raise RuntimeError("incomplete evolved scaffold")
    known = sorted((PROXY / "known").glob("*.red"))
    hard = sorted((PROXY / "hard_train").glob("*.red"))
    holdout = sorted((PROXY / "hard_holdout").glob("*.red"))
    archetypes = [next(p for p in hard if name in p.stem) for name in
                  ("Serval", "dreadnought", "Microfunk", "doubleShock")]
    training = known + hard + archetypes * 2
    scratch = RUN / "scratch.red"
    elite: dict[tuple, tuple] = {}
    seen = set()
    candidates = []
    started = time.time()
    for attempt in range(4000):
        if elite and rng.random() < 0.7:
            parent = rng.choice(list(elite.values()))[1]
            g = mutate_genome(parent, rng, len(bodies))
        else:
            g = random_genome(rng, len(bodies))
        try:
            source = compile_genome(g, bodies)
        except ValueError:
            continue
        digest = hashlib.sha256(source.encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        scratch.write_text(source)
        panel = rng.sample(training, 6)
        value = score(scratch, panel, [rng.randrange(1, 2**31)], 60)
        family = (g["flow"], g["launch"], g["engine"])
        if family not in elite or value > elite[family][0]:
            elite[family] = (value, g, source)
        candidates.append((value, g, source))
        if attempt % 500 == 0:
            print("screened", attempt, len(seen), len(elite), flush=True)
    candidates.sort(key=lambda row: row[0], reverse=True)
    chosen = candidates[:60] + sorted(elite.values(), key=lambda row: row[0], reverse=True)[:30]
    unique = {hashlib.sha256(row[2].encode()).hexdigest(): row for row in chosen}
    confirmed = []
    for digest, (_, g, source) in unique.items():
        path = RUN / "candidates" / f"{digest[:16]}.red"
        path.write_text(source)
        confirmed.append((score(path, training, [20261118, 20261119], 100), g, path))
    confirmed.sort(key=lambda row: row[0], reverse=True)
    finalists = []
    families = set()
    for row in confirmed:
        key = (row[1]["flow"], row[1]["launch"], row[1]["engine"])
        if key not in families:
            finalists.append(row)
            families.add(key)
        if len(finalists) == 16:
            break
    slate = OLD / "champions/best.red"
    seeds = [1201, 1213, 1223, 1231, 1237, 1249]
    slate_known = score(slate, known, seeds, 250)
    slate_hard = score(slate, holdout, seeds, 250)
    results = []
    for train, g, path in finalists:
        covered = score(path, known, seeds, 250)
        difficult = score(path, holdout, seeds, 250)
        projected = 120.8 + 100 * (11 / 25 * (covered - slate_known) + 14 / 25 * (difficult - slate_hard))
        results.append({"file": str(path), "genome": g, "training": train,
                        "known": covered, "hard_holdout": difficult, "estimated_live": projected})
    results.sort(key=lambda row: row["estimated_live"], reverse=True)
    seeded = []
    for row in results:
        if row["estimated_live"] >= 120.8 and row["known"] >= slate_known and row["hard_holdout"] >= slate_hard:
            src = Path(row["file"])
            dst = RUN / "intake" / src.name
            shutil.copy2(src, dst)
            seeded.append(str(dst))
    save_json(RUN / "RESULTS.json", {"started_at": started, "finished_at": time.time(),
              "source_scaffolds": [str(p) for p in sources], "screened": len(seen),
              "extra_archetypes": [p.name for p in archetypes], "seeds": seeds,
              "slate_known": slate_known, "slate_hard_holdout": slate_hard,
              "results": results, "isolated_intake": seeded})
    print("finished", len(seen), "best", results[0]["estimated_live"], "intake", len(seeded), flush=True)


if __name__ == "__main__":
    run()
