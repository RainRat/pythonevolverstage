"""Restartable eight-hour pMARS hill-climb against cached tournament fields.

The ranking is an approximation: organizer top-x size and match rounds are unknown.
No source downloads or submissions occur here.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import time

from tools.tournament_benchmark import PROFILES, battle, opponent_names
from tools.tournament_multiday import TELEMETRY, RECOVERY_SECONDS, disk_ok, health


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.local/tournament-general-12h-20261109'
CACHED = ROOT / '.local/tournament-multiday-20261030/opponents'
SEEDS = {
    0: ('lp_145.red', 'lp_330.red'),
    1: ('x_455.red', 'x_479.red'),
    2: ('88_464.red', '88_342.red'),
    3: ('nop_44717.red', 'nop_178.red'),
}
WEIGHTED_LANES = [(0, 0), (0, 1), (1, 0), (1, 0), (1, 1), (1, 1),
                  (1, 0), (1, 1), (2, 0), (2, 1), (3, 0), (3, 1)]
FIELD_ROUNDS = 12
HOLDOUT_ROUNDS = 60
HOURS = 8
NUMBER = re.compile(r'[-+]?\d+')


def save_json(path: Path, value: object) -> None:
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(pending, path)


def mutate(lines: list[str], donor: list[str], rng: random.Random) -> list[str]:
    result = lines.copy()
    choice = rng.randrange(5)
    index = rng.randrange(len(result))
    if choice == 0:
        matches = list(NUMBER.finditer(result[index]))
        if matches:
            match = rng.choice(matches)
            old = int(match.group())
            step = rng.choice((-17, -7, -3, -1, 1, 3, 7, 17))
            result[index] = result[index][:match.start()] + str(old + step) + result[index][match.end():]
    elif choice == 1:
        result[index] = donor[rng.randrange(len(donor))]
    elif choice == 2:
        end = min(len(result), index + rng.randint(2, 6))
        result[index:end] = donor[index:end]
    elif choice == 3:
        other = rng.randrange(len(result))
        result[index], result[other] = result[other], result[index]
    else:
        # One insertion/deletion keeps entry point zero and warrior length fixed.
        result.pop(index)
        result.insert(rng.randrange(len(result) + 1), donor[rng.randrange(len(donor))])
    return result


def fitness(matrix: list[list[float]], partner_index: int | None = None
            ) -> tuple[float, tuple[int, int], float]:
    """Candidate survival in approximate push-off for top 8 and full field."""
    candidate = len(matrix) - 1
    ranks = []
    sizes = []
    for size in (8, len(matrix) - 1):
        active = list(range(size))
        if partner_index is not None and partner_index not in active:
            active.append(partner_index)
        active.append(candidate)
        sizes.append(len(active) - 1)
        while len(active) > 1:
            stdev = []
            for column in active:
                values = [matrix[row][column] for row in active]
                mean = sum(values) / len(values)
                stdev.append(math.sqrt(sum((v - mean)**2 for v in values) / len(values)))
            scale = sum(stdev) or 1.0
            rating = {}
            for row in active:
                peers = [other for other in active if other != row]
                mean = sum(matrix[row][other] for other in peers) / len(peers)
                nearest = min(sum(abs(matrix[row][column] - matrix[other][column])
                                  for column in active) / scale for other in peers)
                rating[row] = mean * nearest
            loser = min(active, key=lambda row: (rating[row], row))
            if loser == candidate:
                break
            active.remove(loser)
        ranks.append(len(active))
    mean = sum(matrix[candidate][other] for other in range(candidate)) / candidate
    survival = sum((size + 1 - rank) / size for size, rank in zip(sizes, ranks)) / 2
    return survival + mean / 15, tuple(ranks), mean


def field_matrix(field: list[Path], profile: tuple,
                 seed: int | None = None, battle_fn=None) -> list[list[float]]:
    battle_fn = battle_fn or battle
    matrix = [[1.5 for _ in field] for _ in field]
    for i, left in enumerate(field):
        for j in range(i + 1, len(field)):
            matrix[i][j], matrix[j][i] = battle_fn(left, field[j], profile, FIELD_ROUNDS,
                                                  seed=seed)
    return matrix


def score(candidate: Path, field: list[Path], base: list[list[float]], profile: tuple,
          seed: int | None = None, battle_fn=None, partner_index: int | None = None):
    battle_fn = battle_fn or battle
    pairs = [battle_fn(candidate, opponent, profile, FIELD_ROUNDS, seed=seed)
             for opponent in field]
    matrix = [row + [pairs[i][1]] for i, row in enumerate(base)]
    matrix.append([pair[0] for pair in pairs] + [1.5])
    return fitness(matrix, partner_index=partner_index)


def holdout_score(candidate: Path, arena: int) -> float:
    opponents = sorted((ROOT / '.local/tournament-polish-20261104/independent' /
                        f'arena{arena}').glob('*.red'))[:5]
    if len(opponents) != 5:
        raise RuntimeError(f'Missing independent opponents for arena {arena}')
    return sum(battle(candidate, opponent, PROFILES[arena], HOLDOUT_ROUNDS)[0]
               for opponent in opponents) / len(opponents)


def prepare(run: Path) -> dict:
    run.mkdir(parents=True, exist_ok=True)
    state_path = run / 'state.json'
    if state_path.exists():
        return json.loads(state_path.read_text())
    for folder in ('seeds', 'champions', 'improvements', 'scratch', 'fields'):
        (run / folder).mkdir()
    field_names = {}
    for arena, profile in enumerate(PROFILES):
        kind = profile[0]
        ranked = opponent_names(profile[1], 20)
        cached = {path.name: path for path in (CACHED / kind).glob('*.red')}
        chosen = [cached[name] for name in ranked if name in cached][:10]
        if len(chosen) != 10:
            raise RuntimeError(f'Only {len(chosen)} cached ranked opponents for {kind}')
        field_names[str(arena)] = []
        for opponent in chosen:
            target = run / 'fields' / f'a{arena}_{opponent.name}'
            shutil.copy2(opponent, target)
            field_names[str(arena)].append(str(target.relative_to(run)))
        for lane, name in enumerate(SEEDS[arena]):
            source = SOURCE / 'baseline_keepers' / name
            lines = source.read_text().splitlines()
            if len(lines) != 50 or any('LDP' in line or 'STP' in line for line in lines):
                raise RuntimeError(f'Illegal seed {source}')
            shutil.copy2(source, run / 'seeds' / f'a{arena}_lane{lane}.red')
            shutil.copy2(source, run / 'champions' / f'a{arena}_lane{lane}.red')
    state = {'wall_start': time.time(), 'deadline': time.time() + HOURS*3600,
             'attempts': {f'{a}:{l}': 0 for a in SEEDS for l in range(2)},
             'accepted': {f'{a}:{l}': 0 for a in SEEDS for l in range(2)},
             'fields': field_names, 'source': str(SOURCE), 'rounds': FIELD_ROUNDS}
    save_json(state_path, state)
    (run/'RUNBOOK.md').write_text(
        f'# Tournament-shaped eight-hour hill-climb\n\n'
        f'Start epoch: {state["wall_start"]}; deadline epoch: {state["deadline"]}. '
        'Resume with `python -m tools.tournament_hillclimb --run <this directory>`. '
        'Ten cached ranked warriors per arena and a frozen partner seed form the field. '
        'The two approximate top-x checks use eight and eleven field members. '
        'Each accepted warrior is saved under improvements; seeds and source remain unchanged. '
        'Current champions are in champions; accepted holdout scores are in events.jsonl. '
        'No source crawling or tournament submission occurs.\n')
    return state


def run_search(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    lock = (run / 'supervisor.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = prepare(run)
    if not disk_ok(run):
        raise RuntimeError('Insufficient disk space')
    rng = random.Random()
    fields = {}
    bases = {}
    incumbents = {}
    holdout_floor = {}
    for arena, lane in dict.fromkeys(WEIGHTED_LANES):
        ranked = [run / name for name in state['fields'][str(arena)]]
        partner = run / 'seeds' / f'a{arena}_lane{1-lane}.red'
        field = ranked + [partner]
        fields[arena, lane] = field
        bases[arena, lane] = field_matrix(field, PROFILES[arena])
        champion = run / 'champions' / f'a{arena}_lane{lane}.red'
        seed = run / 'seeds' / f'a{arena}_lane{lane}.red'
        holdout_floor[arena, lane] = holdout_score(seed, arena) - .05
        if champion.read_bytes() != seed.read_bytes() and holdout_score(champion, arena) < holdout_floor[arena, lane]:
            shutil.copy2(seed, champion)
            print('reset weak holdout champion to saved seed', arena, lane, flush=True)
        incumbents[arena, lane] = score(champion, field, bases[arena, lane], PROFILES[arena])
        print('baseline', arena, lane, incumbents[arena, lane], flush=True)
    last_save = time.monotonic()
    last_health = 0.0
    last_critical = -RECOVERY_SECONDS
    duty = 1.0
    reason = 'healthy'
    while time.time() < state['deadline']:
        now = time.monotonic()
        if now - last_health >= 20:
            duty, reason = health(TELEMETRY)
            last_health = now
            if duty == 0:
                last_critical = now
            if not disk_ok(run):
                raise RuntimeError('Disk limit reached')
        if now - last_save >= 300:
            save_json(run / 'state.json', state)
            print('progress', state['attempts'], state['accepted'], reason, flush=True)
            last_save = now
        if duty == 0 or now - last_critical < RECOVERY_SECONDS:
            time.sleep(min(20, max(0, state['deadline'] - time.time())))
            continue
        trial_start = time.monotonic()
        arena, lane = rng.choice(WEIGHTED_LANES)
        key = f'{arena}:{lane}'
        champion = run / 'champions' / f'a{arena}_lane{lane}.red'
        seeds = [run / 'seeds' / f'a{arena}_lane{n}.red' for n in range(2)]
        parent = champion if rng.random() < .85 else rng.choice(seeds)
        donor = champion if rng.random() < .7 else rng.choice(seeds)
        lines = mutate(parent.read_text().splitlines(), donor.read_text().splitlines(), rng)
        trial = run / 'scratch' / f'a{arena}_lane{lane}.red'
        trial.write_text('\n'.join(lines) + '\n')
        state['attempts'][key] += 1
        if lines == champion.read_text().splitlines():
            continue
        try:
            result = score(trial, fields[arena, lane], bases[arena, lane], PROFILES[arena])
        except RuntimeError:
            continue  # pMARS rejects a malformed mutation; the champion stays intact.
        if result[0] > incumbents[arena, lane][0] + 1e-5:
            holdout_mean = holdout_score(trial, arena)
            if holdout_mean < holdout_floor[arena, lane]:
                continue
            state['accepted'][key] += 1
            number = state['accepted'][key]
            target = run / 'improvements' / f'a{arena}_lane{lane}_{number:05d}.red'
            shutil.copy2(trial, target)
            shutil.copy2(trial, champion)
            incumbents[arena, lane] = result
            event = {'time': time.time(), 'arena': arena, 'lane': lane, 'attempt': state['attempts'][key],
                     'accepted': number, 'fitness': result[0], 'ranks': result[1],
                     'field_mean': result[2], 'holdout_mean': holdout_mean,
                     'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'path': str(target)}
            with (run / 'events.jsonl').open('a') as output:
                output.write(json.dumps(event) + '\n')
            save_json(run / 'state.json', state)
            print('accepted', event, flush=True)
        if duty < 1:
            active = time.monotonic() - trial_start
            time.sleep(min(active*(1/duty-1), max(0, state['deadline']-time.time())))
    save_json(run / 'state.json', state)
    print('finished at wall deadline', state['attempts'], state['accepted'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    run_search(args.run.resolve())
