"""Screen evolved warriors against cached Koenigstuhl opponents with pMARS.

This is a bounded tournament proxy. It uses the announced battle profiles and
an approximate iterative SD-score push-off, with an explicitly small top-x.
It only reads cached Koenigstuhl archives and ranking pages from
references/koenigstuhl/; see that directory's README for source URLs.
Set PMARS_BIN to a compiled pMARS binary when the local reference build is
unavailable. Run after evolution with an isolated config directory, for example:
python tools/tournament_benchmark.py .local/tournament-four-arena-20261030
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PMARS = Path(os.environ.get("PMARS_BIN", ROOT / ".local/corewar-prep-2026-10-28/pmars-reference/src/pmars"))
REF = ROOT / "references/koenigstuhl"
PROFILES = (
    ("limited_process", "lp", 8000, 8, 80000, 200, False),
    ("94x", "x", 55440, 10000, 500000, 200, False),
    ("88", "88", 8000, 8000, 80000, 100, True),
    ("94nop", "94", 8000, 8000, 80000, 100, False),
)


def opponent_names(kind: str, limit: int) -> list[str]:
    html = (REF / f"{kind}_rank.html").read_text()
    names = []
    for line in html.splitlines():
        match = re.search(r'^\s*\d+\s+<a href="HILL32/([^"/]+\.red)"', line)
        if not match or "P-Space" in line:
            continue
        names.append(match.group(1))
        if len(names) == limit:
            break
    if len(names) != limit:
        raise RuntimeError(f"Only {len(names)} usable ranked {kind} opponents")
    return names


def prepare_opponents(kind: str, names: list[str], destination: Path) -> list[Path]:
    archive = REF / (f"{kind}top50.tar.gz" if kind in {"88", "94"} else f"{kind}.tar.gz")
    destination.mkdir(parents=True, exist_ok=True)
    paths = []
    with tarfile.open(archive) as members:
        for name in names:
            data = members.extractfile(f"HILL32/{name}")
            if data is None:
                raise RuntimeError(f"Missing {name} in {archive}")
            code = data.read()
            if re.search(rb"\b(?:LDP|STP)\b", code, re.I):
                raise RuntimeError(f"P-space instruction in {name}")
            path = destination / name
            if path.exists() and path.read_bytes() != code:
                raise RuntimeError(f"Changed cached opponent {path}")
            path.write_bytes(code)
            paths.append(path)
    return paths


def battle(candidate: Path, opponent: Path, profile: tuple, rounds: int) -> tuple[float, float]:
    _, _, size, processes, cycles, distance, strict88 = profile
    command = [str(PMARS), "-b", "-f", "-r", str(rounds), "-s", str(size),
               "-p", str(processes), "-c", str(cycles), "-d", str(distance),
               "-l", str(distance)]
    if strict88:
        command.append("-8")
    result = subprocess.run(command + [str(candidate), str(opponent)],
                            text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError(f"pMARS rejected {candidate} vs {opponent}: {result.stderr or result.stdout}")
    scores = re.findall(r"scores\s+(-?\d+)", result.stdout)
    if len(scores) != 2:
        raise RuntimeError(f"Unexpected pMARS output: {result.stdout}")
    return int(scores[0]) / rounds, int(scores[1]) / rounds


def push_off(paths: list[Path], profile: tuple, rounds: int) -> dict[Path, tuple[int, float]]:
    """Approximate the announced iterative average-score × SD-distance rule.

    The organizer has not specified the exact top-x size, round count, or
    treatment of self scores, so these ranks are diagnostic only.
    """
    matrix = [[1.5 for _ in paths] for _ in paths]
    for i, left in enumerate(paths):
        for j in range(i + 1, len(paths)):
            matrix[i][j], matrix[j][i] = battle(left, paths[j], profile, rounds)
    active = list(range(len(paths)))
    result = {}
    while active:
        stdev = []
        for column in active:
            values = [matrix[row][column] for row in active]
            mean = sum(values) / len(values)
            stdev.append(math.sqrt(sum((value - mean) ** 2 for value in values) / len(values)))
        scale = sum(stdev) or 1.0
        ratings = {}
        for row in active:
            peers = [other for other in active if other != row]
            if not peers:
                ratings[row] = 0.0
                continue
            mean_score = sum(matrix[row][other] for other in peers) / len(peers)
            nearest = min(sum(abs(matrix[row][column] - matrix[other][column])
                              for column in active) / scale for other in peers)
            ratings[row] = mean_score * nearest
        removed = min(active, key=lambda row: (ratings[row], paths[row].name))
        result[paths[removed]] = (len(active), round(ratings[removed], 4))
        active.remove(removed)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="isolated evolution directory")
    parser.add_argument("--screen-opponents", type=int, default=3)
    parser.add_argument("--final-opponents", type=int, default=10)
    parser.add_argument("--screen-rounds", type=int, default=3)
    parser.add_argument("--final-rounds", type=int, default=12)
    parser.add_argument("--top", type=int, default=2)
    args = parser.parse_args()
    run = args.run.resolve()
    if not PMARS.is_file():
        raise FileNotFoundError(PMARS)
    rows = []
    for arena, profile in enumerate(PROFILES):
        label, kind, *_ = profile
        candidates = sorted((run / f"arena{arena}").glob("*.red"))
        if not candidates:
            raise RuntimeError(f"No candidates in arena {arena}")
        for candidate in candidates:
            lines = [line for line in candidate.read_text().splitlines() if line.strip()]
            if len(lines) > 50:
                raise RuntimeError(f"Overlength candidate: {candidate}")
        names = opponent_names(kind, args.final_opponents)
        opponents = prepare_opponents(kind, names, run / "opponents" / label)
        screened = []
        for candidate in candidates:
            score = sum(battle(candidate, opponent, profile, args.screen_rounds)[0]
                        for opponent in opponents[:args.screen_opponents]) / args.screen_opponents
            screened.append((score, candidate))
        screened.sort(reverse=True)
        finalists = screened[:args.top]
        ranks = push_off(opponents + [candidate for _, candidate in finalists],
                         profile, args.final_rounds)
        for screen_score, candidate in finalists:
            scores = [battle(candidate, opponent, profile, args.final_rounds)[0]
                      for opponent in opponents]
            rows.append((label, candidate.name, round(screen_score, 3),
                         round(sum(scores) / len(scores), 3),
                         round(min(scores), 3), ranks[candidate][0],
                         ranks[candidate][1], args.final_rounds, len(scores)))
        print(label, "screened", len(candidates), "top", [(p.name, round(s, 2)) for s, p in screened[:args.top]], flush=True)
    output = run / "pmars_tournament_proxy.csv"
    with output.open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("profile", "candidate", "screen_mean", "final_mean", "final_min", "push_off_rank", "push_off_rating_at_removal", "rounds_per_opponent", "opponents"))
        writer.writerows(rows)
    print(output)


if __name__ == "__main__":
    main()
