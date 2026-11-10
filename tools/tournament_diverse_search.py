"""Restartable tournament search with archive islands and rotating cached fields.

Only limited-process and 94x are searched. No network access or submission occurs.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import tarfile
import time

from tools.tournament_benchmark import PROFILES, battle, opponent_names
from tools.tournament_hillclimb import ROOT, SOURCE, mutate, save_json, score, field_matrix
from tools.tournament_multiday import TELEMETRY, RECOVERY_SECONDS, disk_ok, health


PRIOR = ROOT / '.local/tournament-hillclimb-8h-20261110'
PUBLISHED = ROOT / 'references/koenigstuhl'
BASELINES = {0: ('lp_145.red', 'lp_330.red'), 1: ('x_455.red', 'x_479.red')}
HOURS = 8
ISLANDS = 8
RESTART_AFTER = 500
PROMOTION_ROUNDS = 60


def choose_diverse(candidates: list[tuple[float, tuple[float, ...], Path]], count: int) -> list[Path]:
    """Take strong archive entries with distinct code and matchup vectors."""
    candidates = sorted(candidates, reverse=True)[:200]
    if len(candidates) < count:
        raise RuntimeError(f'Only {len(candidates)} legal archive candidates')
    selected = [candidates.pop(0)]
    lines = {p: p.read_text().splitlines() for _, _, p in candidates + selected}
    while len(selected) < count:
        def value(item):
            points, vector, path = item
            novelty = min(sum(a != b for a, b in zip(lines[path], lines[other])) / 50
                          for _, _, other in selected)
            behavior = min(sum(abs(a - b) for a, b in zip(vector, other_vector)) /
                           (3 * len(vector)) for _, other_vector, _ in selected)
            return points / 3 + novelty + behavior
        chosen = max(candidates, key=value)
        selected.append(chosen)
        candidates.remove(chosen)
    return [path for _, _, path in selected]


def cached_fields(run: Path, arena: int) -> dict[str, list[str]]:
    profile = PROFILES[arena]
    archive = PUBLISHED / ('lp.tar.gz' if arena == 0 else 'x.tar.gz')
    ranked = opponent_names(profile[1], 80)
    output = {'A': [], 'B': [], 'C': []}
    with tarfile.open(archive) as source:
        members = {Path(m.name).name: m for m in source.getmembers() if m.name.endswith('.red')}
        for name in ranked:
            if name not in members:
                continue
            content = source.extractfile(members[name]).read()
            if re.search(rb'\b(?:LDP|STP)\b', content, re.I):
                continue
            index = sum(map(len, output.values()))
            if index >= 30:
                break
            group = 'ABC'[index // 10]
            target = run / 'fields' / f'arena{arena}' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            output[group].append(str(target.relative_to(run)))
    if any(len(paths) != 10 for paths in output.values()):
        raise RuntimeError(f'Insufficient cached {profile[0]} opponents: {output}')
    return output


def promotion(candidate: Path, opponents: list[Path], profile: tuple) -> float:
    return sum(battle(candidate, other, profile, PROMOTION_ROUNDS)[0]
               for other in opponents) / len(opponents)


def prepare(run: Path) -> dict:
    state_path = run / 'state.json'
    if state_path.exists():
        return json.loads(state_path.read_text())
    for name in ('fields', 'pool', 'seeds', 'champions', 'improvements', 'restarts', 'scratch'):
        (run / name).mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261110)
    archive = sorted((SOURCE / 'archive').glob('*.red'))
    assert len(archive) >= 1000
    sample = rng.sample(archive, min(500, len(archive)))
    fields = {}
    pool = {}
    for arena in (0, 1):
        profile = PROFILES[arena]
        fields[str(arena)] = cached_fields(run, arena)
        screen = [run / p for p in (fields[str(arena)]['A'][:2] + fields[str(arena)]['B'][:1])]
        scored = []
        for source in sample:
            lines = source.read_text().splitlines()
            if len(lines) != 50 or re.search(r'\b(?:LDP|STP)\b', source.read_text(), re.I):
                continue
            try:
                vector = tuple(battle(source, other, profile, 6)[0] for other in screen)
            except (RuntimeError, subprocess.TimeoutExpired):
                continue
            scored.append((sum(vector)/len(vector), vector, source))
        chosen = choose_diverse(scored, 40)
        pool[str(arena)] = []
        for index, source in enumerate(chosen):
            target = run / 'pool' / f'a{arena}_{index:02d}.red'
            shutil.copy2(source, target)
            pool[str(arena)].append({'path': str(target.relative_to(run)), 'source': source.name})
        for lane in range(ISLANDS):
            source = (SOURCE / 'baseline_keepers' / BASELINES[arena][lane]
                      if lane < 2 else run / pool[str(arena)][lane-2]['path'])
            for folder in ('seeds', 'champions'):
                shutil.copy2(source, run / folder / f'a{arena}_lane{lane}.red')
        print('prepared', profile[0], len(scored), 'legal archive screens', flush=True)
    start = time.time()
    state = {'wall_start': start, 'deadline': start + HOURS*3600,
             'fields': fields, 'pool': pool,
             'attempts': {f'{a}:{l}': 0 for a in (0, 1) for l in range(ISLANDS)},
             'accepted': {f'{a}:{l}': 0 for a in (0, 1) for l in range(ISLANDS)},
             'restarts': {f'{a}:{l}': 0 for a in (0, 1) for l in range(ISLANDS)},
             'last_improve': {f'{a}:{l}': 0 for a in (0, 1) for l in range(ISLANDS)},
             'floor': {}}
    for arena in (0, 1):
        gate = [run / p for p in fields[str(arena)]['C'][:5]]
        for lane in range(ISLANDS):
            key = f'{arena}:{lane}'
            seed = run / 'seeds' / f'a{arena}_lane{lane}.red'
            state['floor'][key] = promotion(seed, gate, PROFILES[arena]) - .05
    save_json(state_path, state)
    (run / 'RUNBOOK.md').write_text(
        f'# Diversity tournament search\n\nStart epoch: {start}; deadline epoch: {state["deadline"]}. '
        'Resume with `python -m tools.tournament_diverse_search --run <run directory>`. '
        'Two saved leaders and six archive seeds per event. Archive sampled locally (500 files), '
        'screened under the exact pMARS profile, then 40 strong diverse donors copied per event. '
        'Training fields A and B each contain ten cached ranked warriors; C has five promotion '
        'opponents and five untouched review opponents. Eight- and eleven-member push-off '
        'scores are approximations. Accepted versions and pre-restart champions are preserved. '
        'Host telemetry, three-minute recovery, disk limits, and the wall deadline apply. '
        'No network access or tournament submission occurs.\n')
    return state


def run_search(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    with (run / 'supervisor.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = prepare(run)
        if not disk_ok(run):
            raise RuntimeError('Disk limit reached')
        rng = random.Random()
        keys = [(0, lane) for lane in range(ISLANDS)] + [(1, lane) for lane in range(ISLANDS)]*2
        fields = {}
        matrices = {}
        incumbent = {}
        gate = {}
        for arena, lane in dict.fromkeys(keys):
            other_seed = run / 'seeds' / f'a{arena}_lane{1 if lane == 0 else 0}.red'
            gate[arena] = [run / p for p in state['fields'][str(arena)]['C'][:5]]
            for group in ('A', 'B'):
                field = [run / p for p in state['fields'][str(arena)][group]] + [other_seed]
                fields[arena, lane, group] = field
                matrices[arena, lane, group] = field_matrix(field, PROFILES[arena])
            candidate = run / 'champions' / f'a{arena}_lane{lane}.red'
            incumbent[arena, lane] = tuple(score(candidate, fields[arena,lane,g],
                                               matrices[arena,lane,g], PROFILES[arena])[0]
                                           for g in ('A', 'B'))
            print('baseline', arena, lane, incumbent[arena, lane], flush=True)
        last_health = 0.0
        last_critical = -RECOVERY_SECONDS
        last_save = time.monotonic()
        last_trial_start = None
        duty, reason = 1.0, 'healthy'
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
                print('progress', sum(state['attempts'].values()),
                      sum(state['accepted'].values()), reason, flush=True)
                last_save = now
            if time.time() >= state['wall_start'] + 2*3600 and not (run/'checkpoint-2h.json').exists():
                save_json(run/'checkpoint-2h.json',
                          {'time': time.time(), 'attempts': state['attempts'],
                           'accepted': state['accepted'], 'restarts': state['restarts'],
                           'telemetry': reason})
            if duty == 0 or now - last_critical < RECOVERY_SECONDS:
                last_trial_start = None
                time.sleep(min(20, max(0, state['deadline']-time.time())))
                continue
            if duty < 1 and last_trial_start is not None:
                active = now - last_trial_start
                time.sleep(min(active*(1/duty-1), 20, max(0,state['deadline']-time.time())))
            last_trial_start = time.monotonic()
            arena, lane = rng.choice(keys)
            key = f'{arena}:{lane}'
            champion = run/'champions'/f'a{arena}_lane{lane}.red'
            donors = [run / item['path'] for item in state['pool'][str(arena)]]
            if lane >= 2 and state['attempts'][key] - state['last_improve'][key] >= RESTART_AFTER:
                state['restarts'][key] += 1
                number = state['restarts'][key]
                shutil.copy2(champion, run/'restarts'/f'a{arena}_lane{lane}_{number:04d}_previous.red')
                replacement = rng.choice(donors)
                shutil.copy2(replacement, champion)
                state['floor'][key] = promotion(champion, gate[arena], PROFILES[arena]) - .05
                incumbent[arena,lane] = tuple(score(champion, fields[arena,lane,g],
                                                   matrices[arena,lane,g], PROFILES[arena])[0]
                                               for g in ('A','B'))
                state['last_improve'][key] = state['attempts'][key]
                save_json(run/'state.json', state)
                print('restarted archive island', arena, lane, number, flush=True)
            seed = run/'seeds'/f'a{arena}_lane{lane}.red'
            parent = rng.choices([champion, rng.choice(donors), seed], weights=[65,20,15])[0]
            donor = rng.choices([champion, rng.choice(donors), seed], weights=[40,40,20])[0]
            lines = mutate(parent.read_text().splitlines(), donor.read_text().splitlines(), rng)
            state['attempts'][key] += 1
            if lines == champion.read_text().splitlines():
                continue
            trial = run/'scratch'/f'a{arena}_lane{lane}.red'
            trial.write_text('\n'.join(lines)+'\n')
            try:
                values = tuple(score(trial, fields[arena,lane,g],
                                     matrices[arena,lane,g], PROFILES[arena])[0] for g in ('A','B'))
            except (RuntimeError, subprocess.TimeoutExpired):
                continue
            previous = incumbent[arena,lane]
            if sum(values) > sum(previous) + 1e-5 and all(a >= b-.10 for a,b in zip(values,previous)):
                gate_score = promotion(trial, gate[arena], PROFILES[arena])
                if gate_score < state['floor'][key]:
                    continue
                state['accepted'][key] += 1
                number = state['accepted'][key]
                target = run/'improvements'/f'a{arena}_lane{lane}_{number:05d}.red'
                shutil.copy2(trial, target)
                shutil.copy2(trial, champion)
                incumbent[arena,lane] = values
                state['last_improve'][key] = state['attempts'][key]
                event = {'time':time.time(),'arena':arena,'lane':lane,'attempt':state['attempts'][key],
                         'accepted':number,'fitness':values,'gate_score':gate_score,
                         'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
                with (run/'events.jsonl').open('a') as out:
                    out.write(json.dumps(event)+'\n')
                save_json(run/'state.json', state)
                print('accepted', event, flush=True)
        save_json(run/'state.json', state)
        print('finished at wall deadline', sum(state['attempts'].values()),
              sum(state['accepted'].values()), flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    run_search(args.run.resolve())
