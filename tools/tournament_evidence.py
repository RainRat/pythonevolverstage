"""Restartable, telemetry-guarded Saturday tournament evidence pass.

Prepare ranked sources before launch. This program reads only local files and
never submits entries. Its push-off ranks approximate unpublished event details.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import itertools
import json
import math
import random
import re
import sqlite3
import subprocess
import tarfile
import time
from pathlib import Path

from tools.tournament_benchmark import PROFILES, battle
from tools.tournament_hillclimb import ROOT, save_json
from tools.tournament_multiday import TELEMETRY, RECOVERY_SECONDS, disk_ok, health


SOURCE = ROOT / 'references/koenigstuhl'
SNAPSHOT = SOURCE / 'snapshots/2026-11-10'
MANIFEST = ROOT / '.local/tournament-overnight-prep-20261110/candidates.json'
HOURS = 8
FIELD = 40
X_VALUES = (10, 20, 40)
PHASES = {'screen': 12, 'confirm': 24, 'final': 120}


def prepare(run: Path) -> dict:
    path = run / 'state.json'
    if path.exists():
        return json.loads(path.read_text())
    candidates = json.loads(MANIFEST.read_text())['candidates']
    fields = {}
    selected = {}
    for arena, kind in ((0, 'lp'), (1, 'x')):
        page = (SNAPSHOT / f'{kind}_rank.html').read_text()
        archive = SOURCE / f'{kind}.tar.gz'
        reference_candidate = next(Path(item['path']) for item in candidates
                                   if item['profile'] == PROFILES[arena][0])
        with tarfile.open(archive) as sources:
            members = {Path(member.name).name: member for member in sources.getmembers()
                       if member.name.endswith('.red')}
            fields[str(arena)] = []
            for line in page.splitlines():
                match = re.search(r'^\s*\d+\s+<a href="HILL32/([^"/]+\.red)"', line)
                if not match or 'P-Space' in line or match.group(1) not in members:
                    continue
                name = match.group(1)
                data = sources.extractfile(members[name]).read()
                if re.search(rb'\b(?:LDP|STP)\b', data, re.I):
                    continue
                target = run / 'sources' / f'a{arena}_f{len(fields[str(arena)]):02d}_{name}'
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                try:
                    battle(reference_candidate,target,PROFILES[arena],1,seed=400)
                except (RuntimeError, subprocess.TimeoutExpired):
                    target.unlink()
                    continue
                fields[str(arena)].append({'id': f'f{len(fields[str(arena)]):02d}',
                                            'path': str(target.relative_to(run)),
                                            'name': name,
                                            'sha256': hashlib.sha256(data).hexdigest()})
                if len(fields[str(arena)]) == FIELD:
                    break
        if len(fields[str(arena)]) != FIELD:
            raise RuntimeError(f'Only {len(fields[str(arena)])} cached legal {kind} opponents')
        selected[str(arena)] = []
        for item in (row for row in candidates if row['profile'] == PROFILES[arena][0]):
            original = Path(item['path'])
            data = original.read_bytes()
            if hashlib.sha256(data).hexdigest() != item['sha256']:
                raise RuntimeError(f'Changed candidate {original}')
            if len(data.decode().splitlines()) != 50 or re.search(rb'\b(?:LDP|STP)\b', data, re.I):
                raise RuntimeError(f'Illegal candidate {original}')
            ident = f'c{len(selected[str(arena)]):02d}'
            target = run / 'sources' / f'a{arena}_{ident}.red'
            target.write_bytes(data)
            selected[str(arena)].append({'id': ident, 'path': str(target.relative_to(run)),
                                          'origin': str(original), 'reason': item['reason'],
                                          'sha256': item['sha256']})
    start = time.time()
    state = {'wall_start': start, 'deadline': start + HOURS*3600, 'stage': 'screen',
             'fields': fields, 'candidates': selected, 'screen_seeds': [400,1200,2400],
             'validation_seeds': None, 'final_seeds': None, 'shortlist': None,
             'selected_pairs': None, 'refine_seeds': [], 'matches': 0}
    save_json(path, state)
    (run / 'RUNBOOK.md').write_text(
        f'# Saturday evidence pass\n\nStart: {start}; deadline: {state["deadline"]}. '
        'Resume with `python -m tools.tournament_evidence --run <run directory>`. '
        'Offline local sources only: 40 ranked legal Koenigstuhl opponents and '
        'the manifest candidates per profile. Screen seeds 400/1200/2400; '
        'validation and final seeds are drawn only after the preceding stage. '
        'Match data is cached in matches.sqlite; state.json records progress. '
        'Host telemetry, three-minute critical recovery, disk limits and an '
        'eight-hour wall deadline apply. No entry is submitted.\n')
    return state


def push_off(matrix: list[list[float]], members: list[int]) -> dict[int, int]:
    """Return elimination position; 1 means last survivor."""
    active = members.copy()
    ranks = {}
    while active:
        if len(active) == 1:
            ranks[active.pop()] = 1
            break
        deviations = []
        for column in active:
            values = [matrix[row][column] for row in active]
            mean = sum(values)/len(values)
            deviations.append(math.sqrt(sum((v-mean)**2 for v in values)/len(values)))
        scale = sum(deviations) or 1.0
        ratings = {}
        for row in active:
            peers = [other for other in active if other != row]
            mean = sum(matrix[row][other] for other in peers)/len(peers)
            nearest = min(sum(abs(matrix[row][col]-matrix[other][col])
                              for col in active)/scale for other in peers)
            ratings[row] = mean*nearest
        loser = min(active, key=lambda row: (ratings[row],row))
        ranks[loser] = len(active)
        active.remove(loser)
    return ranks


def _tables(db: sqlite3.Connection) -> None:
    db.execute('CREATE TABLE IF NOT EXISTS matches ('
               'stage TEXT, arena INTEGER, seed INTEGER, left_id TEXT, right_id TEXT, '
               'left_score REAL, right_score REAL, '
               'PRIMARY KEY(stage, arena, seed, left_id, right_id))')
    db.commit()


def _matrix(db: sqlite3.Connection, stage: str, arena: int, seed: int,
            members: list[dict]) -> list[list[float]]:
    matrix = [[1.5 for _ in members] for _ in members]
    for i, left in enumerate(members):
        for j in range(i+1, len(members)):
            right = members[j]
            row = db.execute('SELECT left_score,right_score FROM matches WHERE '
                             'stage=? AND arena=? AND seed=? AND left_id=? AND right_id=?',
                             (stage,arena,seed,left['id'],right['id'])).fetchone()
            if row is None:
                raise RuntimeError(f'Missing {stage} match {arena} {seed} {left["id"]} {right["id"]}')
            matrix[i][j],matrix[j][i] = row
    return matrix


def _rankings(db: sqlite3.Connection, state: dict, stage: str,
              candidate_ids: dict[str,list[str]], seeds: list[int]) -> list[dict]:
    rows = []
    for arena in (0,1):
        field = state['fields'][str(arena)]
        chosen = [item for item in state['candidates'][str(arena)]
                  if item['id'] in candidate_ids[str(arena)]]
        members = field + chosen
        candidate_index = {item['id']: FIELD+i for i,item in enumerate(chosen)}
        for seed in seeds:
            matrix = _matrix(db,stage,arena,seed,members)
            for x in X_VALUES:
                for item in chosen:
                    ident = item['id']
                    indices = list(range(x)) + [candidate_index[ident]]
                    rank = push_off(matrix,indices)[candidate_index[ident]]
                    mean = sum(matrix[candidate_index[ident]][j] for j in range(x))/x
                    rows.append({'arena':arena,'seed':seed,'top_x':x,'candidate':ident,
                                 'partner':'','rank':rank,'survival':(x+1-rank)/x,
                                 'mean':mean})
                for first,second in itertools.combinations(chosen,2):
                    ids = (candidate_index[first['id']], candidate_index[second['id']])
                    ranks = push_off(matrix,list(range(x))+list(ids))
                    for item,index,partner in ((first,ids[0],second['id']),
                                               (second,ids[1],first['id'])):
                        rows.append({'arena':arena,'seed':seed,'top_x':x,
                                     'candidate':item['id'],'partner':partner,
                                     'rank':ranks[index],
                                     'survival':(x+2-ranks[index])/(x+1),
                                     'mean':sum(matrix[index][j] for j in range(x))/x})
    return rows


def _write_rows(path: Path, rows: list[dict]) -> None:
    import csv
    with path.open('w',newline='') as out:
        writer = csv.DictWriter(out,fieldnames=rows[0].keys())
        writer.writeheader();writer.writerows(rows)


def _choose_shortlist(rows: list[dict], state: dict) -> dict[str,list[str]]:
    shortlist = {}
    for arena in (0,1):
        alone = [row for row in rows if row['arena']==arena and not row['partner']]
        candidates = state['candidates'][str(arena)]
        quality = {item['id']:sum(row['survival'] + row['mean']/30 for row in alone
                                if row['candidate']==item['id']) for item in candidates}
        keep = len(candidates) if arena==0 else 4
        shortlist[str(arena)] = sorted(quality,key=quality.get,reverse=True)[:keep]
    return shortlist


def _choose_pairs(rows: list[dict], shortlist: dict[str,list[str]]) -> dict[str,list[str]]:
    result = {}
    for arena in (0,1):
        pairs = list(itertools.combinations(shortlist[str(arena)],2))
        def quality(pair):
            values = []
            for seed,x in itertools.product(sorted({r['seed'] for r in rows}),X_VALUES):
                two = [r['survival'] for r in rows if r['arena']==arena and r['seed']==seed
                       and r['top_x']==x and
                       ((r['candidate']==pair[0] and r['partner']==pair[1]) or
                        (r['candidate']==pair[1] and r['partner']==pair[0]))]
                if len(two)!=2:raise RuntimeError(f'Missing pair score: {arena} {pair} {seed} {x}')
                values.append(.6*max(two)+.4*min(two))
            return sum(values)/len(values)
        result[str(arena)] = list(max(pairs,key=quality))
    return result


def run_search(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    with (run/'supervisor.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=prepare(run)
        db=sqlite3.connect(run/'matches.sqlite')
        _tables(db)
        state['matches']=db.execute('SELECT count(*) FROM matches').fetchone()[0]
        if not disk_ok(run):raise RuntimeError('Disk limit reached')
        last_health=0.0;last_critical=-RECOVERY_SECONDS;last_trial=None
        duty=1.0;reason='healthy'

        def guarded_battle(left: dict, right: dict, arena: int, rounds: int, seed: int):
            nonlocal last_health,last_critical,last_trial,duty,reason
            while True:
                if time.time()>=state['deadline']:
                    raise TimeoutError('Eight-hour wall deadline reached')
                now=time.monotonic()
                if now-last_health>=20:
                    duty,reason=health(TELEMETRY)
                    last_health=now
                    if duty==0:last_critical=now
                    if not disk_ok(run):raise RuntimeError('Disk limit reached')
                if duty==0 or now-last_critical<RECOVERY_SECONDS:
                    last_trial=None
                    time.sleep(min(20,max(0,state['deadline']-time.time())))
                    continue
                if duty<1 and last_trial is not None:
                    time.sleep(min(now-last_trial,20)*(1/duty-1))
                last_trial=time.monotonic()
                return battle(run/left['path'],run/right['path'],PROFILES[arena],rounds,seed=seed)

        def fill(stage: str, seeds: list[int], ids: dict[str,list[str]], rounds: int):
            for arena in (0,1):
                members = state['fields'][str(arena)] + [item for item in state['candidates'][str(arena)]
                                                        if item['id'] in ids[str(arena)]]
                for seed in seeds:
                    for i,left in enumerate(members):
                        for right in members[i+1:]:
                            if stage=='final' and left['id'].startswith('f') and right['id'].startswith('f'):
                                continue  # Final stage checks entries against the field.
                            if stage=='refine' and left['id'][0]==right['id'][0]:
                                continue  # Refinement scores only entry-versus-field matches.
                            key=(stage,arena,seed,left['id'],right['id'])
                            if db.execute('SELECT 1 FROM matches WHERE stage=? AND arena=? AND '
                                          'seed=? AND left_id=? AND right_id=?',key).fetchone():
                                continue
                            a,b=guarded_battle(left,right,arena,rounds,seed)
                            db.execute('INSERT INTO matches VALUES (?,?,?,?,?,?,?)',(*key,a,b))
                            db.commit()
                            state['matches']+=1
                            if state['matches']%100==0:
                                save_json(run/'state.json',state)
                                print('progress',stage,state['matches'],reason,flush=True)

        try:
            if state['stage']=='screen':
                ids={str(a):[item['id'] for item in state['candidates'][str(a)]] for a in (0,1)}
                fill('screen',state['screen_seeds'],ids,PHASES['screen'])
                rows=_rankings(db,state,'screen',ids,state['screen_seeds'])
                _write_rows(run/'screen.csv',rows)
                state['shortlist']=_choose_shortlist(rows,state)
                used=set(state['screen_seeds'])
                state['validation_seeds']=random.SystemRandom().sample(
                    [n for n in range(300,7000) if n not in used],3)
                state['stage']='confirm';save_json(run/'state.json',state)
                print('screen complete',state['shortlist'],flush=True)
            if state['stage']=='confirm':
                fill('confirm',state['validation_seeds'],state['shortlist'],PHASES['confirm'])
                rows=_rankings(db,state,'confirm',state['shortlist'],state['validation_seeds'])
                _write_rows(run/'confirm.csv',rows)
                state['selected_pairs']=_choose_pairs(rows,state['shortlist'])
                used=set(state['screen_seeds']+state['validation_seeds'])
                state['final_seeds']=random.SystemRandom().sample(
                    [n for n in range(300,7000) if n not in used],3)
                state['stage']='final';save_json(run/'state.json',state)
                print('confirmation complete',state['selected_pairs'],flush=True)
            if state['stage']=='final':
                fill('final',state['final_seeds'],state['selected_pairs'],PHASES['final'])
                summary=[]
                for arena in (0,1):
                    for ident in state['selected_pairs'][str(arena)]:
                        values=[]
                        for field in state['fields'][str(arena)]:
                            points=[]
                            for seed in state['final_seeds']:
                                row=db.execute('SELECT right_score FROM matches WHERE '
                                               'stage=? AND arena=? AND seed=? AND left_id=? AND right_id=?',
                                               ('final',arena,seed,field['id'],ident)).fetchone()
                                if row is None:raise RuntimeError(f'Missing final score {arena} {ident}')
                                points.append(row[0])
                            values.append(sum(points)/len(points))
                        item=next(x for x in state['candidates'][str(arena)] if x['id']==ident)
                        summary.append({'arena':arena,'candidate':ident,'origin':item['origin'],
                                        'sha256':item['sha256'],'mean40':round(sum(values)/len(values),4),
                                        'minimum40':round(min(values),4)})
                _write_rows(run/'final.csv',summary)
                (run/'DRAFT.md').write_text(
                    '# Unsent Saturday candidate draft\n\n'
                    'Selected pairs and common-seed pMARS scores are in `final.csv`; '
                    'proxy ranks by top-x are in `confirm.csv`; extended scores '
                    'will be in `refine.csv`. These are local '
                    'approximations. Check current hill data, originality, exact '
                    'entry legality, and the concrete source files before any email. '
                    'No submission has been sent.\n')
                state['stage']='refine';save_json(run/'state.json',state)
                print('final checks complete',state['matches'],flush=True)
            if state['stage']=='refine':
                ids=state['selected_pairs']
                state.setdefault('refine_seeds',[])
                used=set(state['screen_seeds']+state['validation_seeds']+
                         state['final_seeds']+state['refine_seeds'])
                while time.time()<state['deadline']:
                    if not state['refine_seeds'] or db.execute(
                            'SELECT count(*) FROM matches WHERE stage=? AND seed=?',
                            ('refine',state['refine_seeds'][-1])).fetchone()[0] == 160:
                        seed=random.SystemRandom().choice([n for n in range(300,7000) if n not in used])
                        state['refine_seeds'].append(seed)
                        used.add(seed)
                        save_json(run/'state.json',state)
                    else:
                        seed=state['refine_seeds'][-1]
                    fill('refine',[seed],ids,1000)
                    summary=[]
                    for arena in (0,1):
                        for ident in ids[str(arena)]:
                            rows=db.execute('SELECT right_score FROM matches WHERE '
                                            'stage=? AND arena=? AND right_id=?',
                                            ('refine',arena,ident)).fetchall()
                            summary.append({'arena':arena,'candidate':ident,
                                            'seeds':len(state['refine_seeds']),
                                            'matches':len(rows),
                                            'mean':sum(row[0] for row in rows)/len(rows)})
                    _write_rows(run/'refine.csv',summary)
                    print('refine seed complete',seed,len(state['refine_seeds']),flush=True)
                state['stage']='deadline';save_json(run/'state.json',state)
        except TimeoutError:
            state['stage']='deadline';save_json(run/'state.json',state)
            print('stopped at wall deadline',state['matches'],flush=True)
        finally:
            db.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    run_search(args.run.resolve())
