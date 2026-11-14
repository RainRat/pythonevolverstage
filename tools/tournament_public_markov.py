"""Generate tournament seeds from cached public Redcode, then screen locally.

This experiment never reads our evolved warriors as training data and never
contacts a source site. Its output is an isolated donor pool, not an entry.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import csv
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import tarfile
import time
import zipfile

from tools.tournament_benchmark import PMARS, PROFILES
from tools.tournament_diverse_search import crossover_lines, safe_battle
from tools.tournament_hillclimb import save_json


ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "references"
RUN = ROOT / ".local/tournament-public-markov-20261113"
OP = re.compile(r"^(?:DAT|MOV|ADD|SUB|MUL|DIV|MOD|JMP|JMZ|JMN|DJN|CMP|SEQ|SNE|SLT|SPL|NOP)\b", re.I)
PSPACE = re.compile(r"\b(?:LDP|STP)\b", re.I)


def sources(arena: int):
    paths = [REF / "koenigstuhl" / name for name in
             ("lp.tar.gz", "x.tar.gz", "88top50.tar.gz", "94top50.tar.gz")]
    if arena == 1:
        paths = paths[1:2]  # Most historical warriors assert CORESIZE == 8000.
    elif arena == 2:
        paths = paths[2:3]
    for archive in paths:
        with tarfile.open(archive) as members:
            for item in members:
                if item.isfile() and item.name.lower().endswith(".red"):
                    yield f"{archive.name}:{item.name}", members.extractfile(item).read()
    if arena != 1:
        with tarfile.open(REF / "historical/warrior10.tar.gz") as members:
            for item in members:
                if item.isfile() and item.name.startswith("88/"):
                    yield f"warrior10.tar.gz:{item.name}", members.extractfile(item).read()
        if arena != 2:
            with zipfile.ZipFile(REF / "historical/Wilkies.zip") as members:
                for name in members.namelist():
                    if name.lower().endswith(".red"):
                        yield f"Wilkies.zip:{name}", members.read(name)


def assemble(code: bytes, arena: int) -> tuple[int, list[str]] | None:
    _, _, size, processes, cycles, distance, strict88 = PROFILES[arena]
    command = [str(PMARS), "-A", "-s", str(size), "-p", str(processes),
               "-c", str(cycles), "-d", str(distance), "-l", "100"]
    if strict88:
        command.append("-8")
    result = subprocess.run(command + ["-"], input=code, capture_output=True, timeout=10)
    if result.returncode:
        return None
    lines = [re.sub(r"\s+", " ", re.sub(r"([#$@<>*{}])\s+(-?\d+)",
                                               r"\1\2", x.strip()))
             for x in result.stdout.decode(errors="replace").splitlines() if x.strip()]
    if not lines or not lines[0].startswith("ORG "):
        return None
    entry = int(lines[0].split()[1])
    body = [line for line in lines[1:] if OP.match(line)]
    if not 0 <= entry < len(body) <= 100 or any(PSPACE.search(line) for line in body):
        return None
    return entry, body


def source_corpus(arena: int):
    seen = set()
    corpus = []
    for origin, code in sources(arena):
        digest = hashlib.sha256(code).hexdigest()
        if digest in seen or PSPACE.search(code.decode(errors="ignore")):
            continue
        seen.add(digest)
        compiled = assemble(code, arena)
        if compiled:
            corpus.append((origin, *compiled))
    return corpus


def generate(arena: int, count: int, seed: int) -> dict:
    rng = random.Random(seed + arena)
    corpus = source_corpus(arena)
    if len(corpus) < 40:
        raise RuntimeError(f"Only {len(corpus)} public source warriors for arena {arena}")
    transitions = defaultdict(list)
    by_opcode = defaultdict(list)
    for _, entry, lines in corpus:
        for i, line in enumerate(lines):
            opcode = line.split(".")[0]
            by_opcode[opcode].append(line)
            if i >= 2:
                transitions[lines[i-2].split(".")[0], lines[i-1].split(".")[0]].append(
                    lines[i:i+4])
    folder = RUN / "generated" / f"a{arena}"
    folder.mkdir(parents=True, exist_ok=True)
    existing = {hashlib.sha256("\n".join(lines).encode()).hexdigest()
                for _, _, lines in corpus}
    made = []
    attempts = 0
    while len(made) < count and attempts < count * 30:
        attempts += 1
        origin, entry, source = rng.choice(corpus)
        prefix = source[entry:min(len(source), entry + rng.randint(2, 5))]
        if len(prefix) < 2:
            continue
        length = rng.randint(max(8, len(prefix) + 1), 50)
        lines = prefix.copy()
        while len(lines) < length:
            key = lines[-2].split(".")[0], lines[-1].split(".")[0]
            choices = transitions.get(key)
            if not choices or rng.random() < .12:
                lines.append(rng.choice(by_opcode[rng.choice(tuple(by_opcode))]))
            else:
                block = rng.choice(choices)
                lines.extend(block[:rng.randint(1, min(4, len(block)))])
            lines = lines[:length]
        digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
        if digest in existing:
            continue
        existing.add(digest)
        text = ("\n".join(lines) + "\nEND 0\n" if arena == 2 else
                "ORG START\nSTART " + lines[0] + "\n" + "\n".join(lines[1:]) + "\n")
        if not assemble(text.encode(), arena):
            continue
        target = folder / f"m{len(made):04d}.red"
        target.write_text(text)
        made.append({"path": str(target.relative_to(RUN)), "anchor": origin,
                     "sha256": hashlib.sha256(text.encode()).hexdigest()})
    if len(made) < count:
        raise RuntimeError(f"Generated only {len(made)} legal warriors after {attempts} attempts")
    return {"arena": arena, "public_sources": len(corpus), "candidates": made,
            "attempts": attempts}


def screen() -> None:
    state = json.loads((RUN / "generated.json").read_text())
    csv_path = RUN / "screen.csv"
    done = {}
    if csv_path.exists():
        with csv_path.open(newline="") as file:
            done = {(int(row["arena"]), row["candidate"], row["opponent"]):
                    float(row["score"]) for row in csv.DictReader(file)}
    with csv_path.open("a", newline="") as file:
        writer = csv.writer(file)
        if not done:
            writer.writerow(("arena", "candidate", "opponent", "rounds", "score"))
        for arena, group in enumerate(state["groups"]):
            field = ROOT / ".local/tournament-overnight-pair-8h-20261113"
            field_state = json.loads((field / "state.json").read_text())
            opponents = [field / p for p in field_state["fields"][str(arena)]["A"][:2]]
            for item in group["candidates"]:
                candidate = RUN / item["path"]
                for opponent in opponents:
                    key = arena, candidate.name, opponent.name
                    if key in done:
                        continue
                    try:
                        score = safe_battle(candidate, opponent, PROFILES[arena], 6, seed=18211)[0]
                    except (RuntimeError, subprocess.TimeoutExpired):
                        score = 0.0
                    writer.writerow((*key, 6, score))
                    done[key] = score
                file.flush()
            print("screened", arena, len(group["candidates"]), flush=True)
    summary = {}
    for arena, group in enumerate(state["groups"]):
        candidates = []
        for item in group["candidates"]:
            scores = [score for (a, name, _), score in done.items()
                      if a == arena and name == Path(item["path"]).name]
            if len(scores) == 2:
                candidates.append((sum(scores)/2, item["path"]))
        summary[str(arena)] = sorted(candidates, reverse=True)[:60]
    (RUN / "screen_top60.json").write_text(json.dumps(summary, indent=2) + "\n")
    final_path = RUN / "screen_final.csv"
    final_done = {}
    if final_path.exists():
        with final_path.open(newline="") as file:
            final_done = {(int(row["arena"]), row["candidate"], row["opponent"]):
                          float(row["score"]) for row in csv.DictReader(file)}
    with final_path.open("a", newline="") as file:
        writer = csv.writer(file)
        if not final_done:
            writer.writerow(("arena", "candidate", "opponent", "rounds", "score"))
        for arena in range(4):
            field = ROOT / ".local/tournament-overnight-pair-8h-20261113"
            field_state = json.loads((field / "state.json").read_text())
            groups = field_state["fields"][str(arena)]
            opponents = [field / p for p in
                         groups["A"][2:3] + groups["B"][:2] + groups["C"][7:9]]
            for _, relative in summary[str(arena)]:
                candidate = RUN / relative
                for opponent in opponents:
                    key = arena, candidate.name, opponent.name
                    if key in final_done:
                        continue
                    try:
                        value = safe_battle(candidate, opponent, PROFILES[arena], 20,
                                            seed=21139)[0]
                    except (RuntimeError, subprocess.TimeoutExpired):
                        value = 0.0
                    writer.writerow((*key, 20, value))
                    final_done[key] = value
                file.flush()
            print("final screened", arena, len(summary[str(arena)]), flush=True)
    chosen = {}
    for arena in range(4):
        scored = []
        for early, relative in summary[str(arena)]:
            scores = [value for (a, name, _), value in final_done.items()
                      if a == arena and name == Path(relative).name]
            if len(scores) == 5:
                scored.append((sum(scores)/5, early, relative))
        scored.sort(reverse=True)
        selected = []
        for score, early, relative in scored:
            lines = (RUN / relative).read_text().splitlines()
            if any(sum(x == y for x, y in zip(lines, prior)) > 30
                   for _, _, _, prior in selected):
                continue
            selected.append((score, early, relative, lines))
            if len(selected) == 12:
                break
        chosen[str(arena)] = [{"path": path, "final_mean": score,
                               "early_mean": early} for score, early, path, _ in selected]
    (RUN / "shortlist.json").write_text(json.dumps(chosen, indent=2) + "\n")
    print("shortlist", {a: len(v) for a, v in chosen.items()}, flush=True)


def inject() -> None:
    prior = ROOT / ".local/tournament-pair-hill-6h-20261113"
    final = ROOT / ".local/tournament-public-intermix-2h-20261113"
    target = final.with_name(final.name + ".preparing")
    old = json.loads((prior / "state.json").read_text())
    shortlist = json.loads((RUN / "shortlist.json").read_text())
    if time.time() < old["deadline"] or target.exists() or final.exists():
        raise RuntimeError("Prior run still active or intermix run already exists")
    if any(len(shortlist[str(arena)]) < 8 for arena in range(4)):
        raise RuntimeError("Insufficient screened public donors")
    for folder in ("fields", "pool", "partners", "seeds", "champions",
                   "improvements", "restarts"):
        shutil.copytree(prior / folder, target / folder)
    (target / "scratch").mkdir()
    state = copy.deepcopy(old)
    for key in ("attempts", "accepted", "restarts", "last_improve"):
        state[key] = {name: 0 for name in state[key]}
    added = {}
    for arena in range(4):
        partner = assemble((target / state["partners"][str(arena)]).read_bytes(), arena)
        if partner is None:
            raise RuntimeError("Frozen partner failed assembly")
        added[str(arena)] = []
        for item in shortlist[str(arena)]:
            source = RUN / item["path"]
            compiled = assemble(source.read_bytes(), arena)
            if compiled is None or len(compiled[1]) > 50:
                continue
            if sum(a == b for a, b in zip(compiled[1], partner[1])) > 20:
                continue
            destination = target / "pool" / f"public_a{arena}_{source.name}"
            destination.write_text('\n'.join(crossover_lines(source, arena)) + '\n')
            state["pool"][str(arena)].append({"path": str(destination.relative_to(target)),
                                                "source": "public_markov_screened"})
            added[str(arena)].append({"path": str(destination.relative_to(target)),
                                       "early_mean": item["early_mean"],
                                       "final_mean": item["final_mean"]})
        if len(added[str(arena)]) < 8:
            raise RuntimeError(f"Only {len(added[str(arena)])} legal diverse donors in {arena}")
    state["seed_sources"] = {
        f"{arena}:{lane}": str(prior / "champions" / f"a{arena}_lane{lane}.red")
        for arena in range(4) for lane in range(4)}
    state["parent_run"] = str(prior)
    state["wall_start"] = time.time()
    state["deadline"] = state["wall_start"] + 2 * 3600
    save_json(target / "state.json", state)
    (target / "public_donors.json").write_text(json.dumps(added, indent=2) + "\n")
    manifest = {str(path.relative_to(target)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(target.rglob("*.red"))}
    (target / "seed_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (target / "RUNBOOK.md").write_text(
        "# Two-hour public donor intermix\n\nContinues the completed six-hour four-arena "
        "run without replacing any champion, seed or frozen partner. Twelve screened "
        "public-source Markov candidates per arena enter only the donor pools; "
        "ordinary parent selection gives them a small chance to intermix. "
        "All source inputs and scores are saved locally. The same telemetry, "
        "promotion gate, partner cap and six-hour run's cached opponents apply. "
        "No source crawl or tournament submission occurs.\n")
    target.rename(final)
    print("prepared intermix", final, "added", {a: len(v) for a, v in added.items()},
          "deadline", time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(state["deadline"])),
          flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("generate", "screen", "inject"))
    parser.add_argument("--count", type=int, default=750)
    args = parser.parse_args()
    if args.action == "generate":
        RUN.mkdir(parents=True, exist_ok=True)
        if (RUN / "generated.json").exists():
            raise RuntimeError("Generated pool already exists")
        groups = [generate(arena, args.count, 61307) for arena in range(4)]
        (RUN / "generated.json").write_text(json.dumps({"seed": 61307,
                                                       "groups": groups}, indent=2) + "\n")
        print("generated", sum(len(g["candidates"]) for g in groups), flush=True)
    elif args.action == "screen":
        screen()
    else:
        inject()


if __name__ == "__main__":
    main()
