"""Bounded structural Tiny warrior trial; no external source access."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import time

from tools.nano_hill_search import save_json
from tools.tiny_hill_search import ROOT, assemble, score, warrior


SOURCE = ROOT / ".local/sal-tiny-conditional-8h-20261117"
RUN = ROOT / ".local/sal-tiny-hll-trial-20261117"
CORE = 800
LIMIT = 20


def module(kind: str, step: int, offset: int, finite: bool = False) -> list[str]:
    if kind == "stone":
        if finite:
            return [f"MOV.I $4, ${offset}", f"ADD.AB #{step}, $-1",
                    "DJN.B $-2, #24", "JMP.B $2, $0", "DAT.F $0, $0"]
        return [f"MOV.I $3, ${offset}", f"ADD.AB #{step}, $-1",
                "JMP.B $-2, $0", "DAT.F $0, $0"]
    if kind == "paper":
        return [f"SPL.B @0, ${offset}", "MOV.I }-1, >-1", "JMP.B $-2, $0"]
    if kind == "clear":
        return ["MOV.I $2, >3", "JMP.B $-1, $0", "DAT.F $0, $0", f"DAT.F $0, ${offset}"]
    if kind == "imp":
        return [f"MOV.I $0, ${step}"]
    raise ValueError(kind)


def compile_spec(spec: dict) -> str:
    first = module(spec["first"], spec["step1"], spec["offset1"], spec["flow"] == "sequential")
    if spec["flow"] == "single":
        body = first
    else:
        second = module(spec["second"], spec["step2"], spec["offset2"])
        if spec["flow"] == "parallel":
            body = ["SPL.B $2, $0", f"JMP.B ${len(first) + 1}, $0"] + first + second
        elif spec["flow"] == "sequential" and spec["first"] == "stone":
            body = first + second
        else:
            raise ValueError("Unsupported structural composition")
    if len(body) > LIMIT:
        raise ValueError("Too many instructions")
    body.extend(["DAT.F $0, $0"] * (LIMIT - len(body)))
    source = warrior(body)
    entry, assembled = assemble(source)
    if entry != 0 or len(assembled) != LIMIT:
        raise ValueError("Invalid compiled warrior")
    return source


def random_spec(rng: random.Random) -> dict:
    flow = rng.choice(("single", "parallel", "sequential"))
    first = "stone" if flow == "sequential" else rng.choice(("stone", "paper", "clear", "imp"))
    second = rng.choice(("paper", "stone", "clear", "imp"))
    return {"flow": flow, "first": first, "second": second,
            "step1": rng.randrange(11, CORE - 11), "offset1": rng.randrange(25, CORE - 25),
            "step2": rng.randrange(11, CORE - 11), "offset2": rng.randrange(25, CORE - 25)}


def mutate_spec(spec: dict, rng: random.Random) -> dict:
    child = spec.copy()
    key = rng.choice(("flow", "first", "second", "step1", "offset1", "step2", "offset2"))
    if key == "flow":
        child["flow"] = rng.choice(("single", "parallel", "sequential"))
        if child["flow"] == "sequential":
            child["first"] = "stone"
    elif key in ("first", "second"):
        child[key] = rng.choice(("stone", "paper", "clear", "imp"))
        if child["flow"] == "sequential":
            child["first"] = "stone"
    else:
        child[key] = (child[key] + rng.choice((-37, -13, -5, -1, 1, 5, 13, 37))) % CORE
        if child[key] < 11:
            child[key] += 11
    return child


def run() -> None:
    RUN.mkdir(exist_ok=True)
    (RUN / "candidates").mkdir(exist_ok=True)
    known = sorted((SOURCE / "known").glob("*.red"))
    hard = sorted((SOURCE / "hard_train").glob("*.red"))
    holdout = sorted((SOURCE / "hard_holdout").glob("*.red"))
    if (len(known), len(hard), len(holdout)) != (11, 9, 9):
        raise RuntimeError("Proxy panel changed")
    # Duplicate familiar archetypes to give them extra training weight.
    archetypes = [next(p for p in hard if name in p.stem) for name in
                  ("Serval", "dreadnought", "Microfunk", "doubleShock")]
    training = known + hard + archetypes * 2
    rng = random.Random(20261117)
    scratch = RUN / "candidate.red"
    seen = set()
    screened = []
    elite = {}
    started = time.time()
    for attempt in range(1200):
        if elite and rng.random() < 0.7:
            spec = mutate_spec(rng.choice(list(elite.values()))[1], rng)
        else:
            spec = random_spec(rng)
        try:
            source = compile_spec(spec)
        except ValueError:
            continue
        digest = hashlib.sha256(source.encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        scratch.write_text(source)
        panel = rng.sample(training, 6)
        value = score(scratch, panel, [rng.randrange(1, 2**31)], 60)
        family = f"{spec['flow']}:{spec['first']}:{spec['second']}"
        prior = elite.get(family)
        if prior is None or value > prior[0]:
            elite[family] = (value, spec)
        screened.append((value, spec, source))
        if attempt % 100 == 0:
            print("screened", attempt, len(seen), len(elite), flush=True)
    screened.sort(key=lambda x: x[0], reverse=True)
    choices = screened[:40]
    choices += [next((row for row in screened if row[1] == value[1]), None) for value in elite.values()]
    choices = [row for row in choices if row is not None]
    distinct = {hashlib.sha256(row[2].encode()).hexdigest(): row for row in choices}
    train_seeds = [713, 719]
    ranked = []
    for digest, (_, spec, source) in distinct.items():
        path = RUN / "candidates" / f"{digest[:16]}.red"
        path.write_text(source)
        ranked.append((score(path, training, train_seeds, 100), spec, path))
    ranked.sort(key=lambda row: row[0], reverse=True)
    finalists = []
    families = set()
    for value, spec, path in ranked:
        family = (spec["flow"], spec["first"], spec["second"])
        if family not in families:
            finalists.append((value, spec, path))
            families.add(family)
        if len(finalists) == 12:
            break
    baseline = ROOT / ".local/sal-tiny-8h-20261116/champions/best.red"
    seeds = [1049, 1051, 1061, 1063]
    slate_known = score(baseline, known, seeds, 250)
    slate_hard = score(baseline, holdout, seeds, 250)
    results = []
    for train, spec, path in finalists:
        covered = score(path, known, seeds, 250)
        hard_score = score(path, holdout, seeds, 250)
        results.append({"file": str(path), "spec": spec, "training": train,
                        "known": covered, "hard_holdout": hard_score,
                        "estimated_live": 120.8 + 100 * (11 / 25 * (covered - slate_known) + 14 / 25 * (hard_score - slate_hard))})
    results.sort(key=lambda row: row["estimated_live"], reverse=True)
    save_json(RUN / "RESULTS.json", {"started_at": started, "finished_at": time.time(),
              "screened": len(seen), "archetype_weight": [p.name for p in archetypes],
              "slate_known": slate_known, "slate_hard_holdout": slate_hard, "seeds": seeds,
              "results": results})
    print("finished", len(seen), "best", results[0]["estimated_live"], flush=True)


if __name__ == "__main__":
    run()
