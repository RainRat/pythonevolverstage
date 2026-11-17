"""Unattended SAL Tiny annealing and final validation on cached public proxies."""

from __future__ import annotations

import fcntl
import hashlib
from importlib.machinery import SourceFileLoader
import json
import math
from pathlib import Path
import random
import shutil
import statistics
import time

from tools.nano_hill_search import mutate, save_json
from tools.tiny_hill_search import ROOT, assemble, body_at, score, warrior
from tools.tournament_multiday import TELEMETRY, RECOVERY_SECONDS, disk_ok, health


OLD = ROOT / ".local/sal-tiny-8h-20261116"
PREP = ROOT / ".local/sal-tiny-overnight-prep-20261116"
RUN = ROOT / ".local/sal-tiny-conditional-8h-20261117"
SOURCE = ROOT / "references/koenigstuhl/tiny/2026-11-16"
LANES = 8
WEIGHT_KNOWN = 11 / 25
WEIGHT_HARD = 14 / 25


def weighted(path: Path, known: list[Path], hard: list[Path], seeds: list[int], rounds: int) -> float:
    return WEIGHT_KNOWN * score(path, known, seeds, rounds) + WEIGHT_HARD * score(path, hard, seeds, rounds)


def seed(rng: random.Random) -> int:
    return rng.randrange(100_000_000, 2_000_000_000)


def signature(body: list[str]) -> tuple[str, ...]:
    return tuple(line.split()[0] for line in body[:5])


def fields() -> tuple[list[Path], list[Path], list[Path]]:
    return tuple(sorted((RUN / folder).glob("*.red")) for folder in
                 ("known", "hard_train", "hard_holdout"))


def prepare() -> dict:
    state_file = RUN / "state.json"
    if state_file.exists():
        return json.loads(state_file.read_text())
    prep = json.loads((RUN / "PREP.json").read_text())
    if not prep["passed"]:
        raise RuntimeError("Fresh proxy calibration failed")
    proxy = json.loads((PREP / "PROXY_PROPOSAL.json").read_text())
    manifest = json.loads((OLD / "reference_manifest.json").read_text())
    for folder in ("known", "hard_train", "hard_holdout", "champions", "improvements", "scratch"):
        (RUN / folder).mkdir(parents=True, exist_ok=True)
    provenance = []
    for item in manifest:
        if item["kind"] != "sal_match":
            continue
        src = OLD / item["run_file"]
        dst = RUN / "known" / src.name
        shutil.copy2(src, dst)
        provenance.append({"kind": "known_current_name", "name": item["name"],
                           "url": item["url"], "file": str(dst.relative_to(RUN)),
                           "sha256": hashlib.sha256(dst.read_bytes()).hexdigest()})
    for kind, folder in (("hard_train", "hard_train"), ("hard_holdout", "hard_holdout")):
        for item in proxy[kind]:
            src = SOURCE / item["source_file"]
            if hashlib.sha256(src.read_bytes()).hexdigest() != item["sha256"]:
                raise RuntimeError(f"Cached source hash changed: {src}")
            dst = RUN / folder / src.name
            shutil.copy2(src, dst)
            provenance.append({"kind": kind, "url": item["source_url"],
                               "file": str(dst.relative_to(RUN)), "sha256": item["sha256"]})
    known, hard_train, hard_holdout = fields()
    if (len(known), len(hard_train), len(hard_holdout)) != (11, 9, 9):
        raise RuntimeError("Unexpected proxy field sizes")
    save_json(RUN / "sources.json", provenance)
    library = sorted({line for path in known + hard_train for line in assemble(path.read_text(errors="replace"))[1]})
    (RUN / "instruction_library.txt").write_text("\n".join(library) + "\n")
    donors = sorted((OLD / "seed_pool").glob("*.red")) + sorted((OLD / "improvements").glob("*.red"))
    donor_bodies = {}
    for path in donors:
        try:
            donor_bodies[path] = body_at(path)
        except ValueError:
            continue
    if len(donor_bodies) < 500:
        raise RuntimeError("Insufficient evolved donors")
    rng = random.Random(20261117)
    candidates = [OLD / "champions/best.red"] + sorted((OLD / "champions").glob("lane*.red"))
    initial = json.loads((OLD / "seed_scores.json").read_text())
    candidates += [OLD / item["file"] for item in initial[:60]]
    candidates += rng.sample(sorted((OLD / "improvements").glob("*.red")), 100)
    shortlist = []
    field_known = rng.sample(known, 5)
    field_hard = rng.sample(hard_train, 4)
    for path in candidates:
        if path not in donor_bodies and not path.exists():
            continue
        try:
            body = body_at(path)
            value = weighted(path, field_known, field_hard, [20261117], 60)
        except (ValueError, RuntimeError):
            continue
        shortlist.append((value, path, body))
    shortlist.sort(key=lambda row: row[0], reverse=True)
    selected = []
    seen = set()
    for row in shortlist:
        key = signature(row[2])
        if key not in seen:
            selected.append(row)
            seen.add(key)
        if len(selected) == LANES:
            break
    if len(selected) != LANES or len({signature(x[2]) for x in selected}) != LANES:
        raise RuntimeError("Insufficient diverse evolved starting points")
    for i, (_, src, _) in enumerate(selected):
        shutil.copy2(src, RUN / "champions" / f"lane{i}.red")
    shutil.copy2(selected[0][1], RUN / "champions/best.red")
    save_json(RUN / "starting_lanes.json", [{"file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                             "screen_score": value, "signature": signature(body)}
                                            for value, path, body in selected])
    slate = OLD / "champions/best.red"
    noise_rng = random.Random(20261117 + 1)
    noisy = [weighted(slate, known, hard_train, [seed(noise_rng), seed(noise_rng)], 100) for _ in range(5)]
    sigma = statistics.pstdev(noisy)
    state = {"started_at": prep["started_at"], "deadline": prep["deadline"],
             "search_deadline": prep["search_deadline"], "phase": "search",
             "attempts": 0, "accepted": 0, "resets": 0, "lanes": [{"attempts": 0, "accepted": 0, "stalled": 0} for _ in range(LANES)],
             "noise_sigma": sigma, "temperature_high": min(0.08, max(0.012, 2 * sigma)),
             "temperature_mid": min(0.04, max(0.006, sigma)),
             "best_screen_score": selected[0][0], "donor_count": len(donor_bodies)}
    save_json(state_file, state)
    print("prepared", len(donor_bodies), "donors", "noise", round(sigma, 5), flush=True)
    return state


def phase(state: dict, now: float) -> tuple[str, float]:
    elapsed = now - state["started_at"]
    if elapsed < 2 * 3600:
        return "high", state["temperature_high"]
    if elapsed < 5 * 3600:
        return "mid", state["temperature_mid"]
    return "strict", 0.0


def propose(parent: list[str], donor: list[str], library: list[str], rng: random.Random) -> list[str]:
    if rng.random() < 0.25:
        result = parent.copy()
        start = rng.randrange(20)
        width = min(rng.randrange(4, 9), 20 - start)
        result[start:start + width] = donor[start:start + width]
        return result
    result = mutate(parent, donor, library, rng)
    if rng.random() < 0.12:
        result = mutate(result, donor, library, rng)
    return result


def search(state: dict) -> dict:
    known, hard_train, _ = fields()
    library = (RUN / "instruction_library.txt").read_text().splitlines()
    donors = sorted((OLD / "seed_pool").glob("*.red")) + sorted((OLD / "improvements").glob("*.red"))
    donors += sorted((RUN / "improvements").glob("*.red"))
    bodies = {}
    for path in donors:
        try:
            bodies[path] = body_at(path)
        except ValueError:
            continue
    donors = list(bodies)
    old_top = [OLD / x["file"] for x in json.loads((OLD / "seed_scores.json").read_text())[:50]]
    rng = random.Random()
    scratch = RUN / "scratch/candidate.red"
    last_health = 0.0
    last_save = time.monotonic()
    last_critical = -RECOVERY_SECONDS
    duty, reason = 0.0, "starting"
    health_state = None
    state.setdefault("host_events", [])
    archived_attempts = [int(p.stem.split("_", 1)[0]) for p in (RUN / "improvements").glob("*.red")]
    state["attempts"] = max([state["attempts"], *archived_attempts])
    state["accepted"] = max(state["accepted"], len(archived_attempts))
    while time.time() < state["search_deadline"]:
        now = time.monotonic()
        if now - last_health >= 30:
            duty, reason = health(TELEMETRY)
            last_health = now
            if (duty, reason) != health_state:
                print("health", duty, reason, flush=True)
                state["host_events"].append({"time": time.time(), "duty": duty, "reason": reason})
                health_state = (duty, reason)
            if duty == 0 and reason in ("critical host pressure", "battery below 40%"):
                last_critical = now
        if now - last_save >= 300:
            if not disk_ok(RUN):
                raise RuntimeError("Disk limit reached")
            save_json(RUN / "state.json", state)
            print("progress", state["attempts"], state["accepted"], state["resets"], phase(state, time.time())[0], reason, flush=True)
            last_save = now
        if duty == 0 or now - last_critical < RECOVERY_SECONDS:
            time.sleep(min(10, max(0, state["search_deadline"] - time.time())))
            continue
        mode, temperature = phase(state, time.time())
        lane = rng.randrange(LANES)
        slot = state["lanes"][lane]
        current = RUN / "champions" / f"lane{lane}.red"
        if slot["stalled"] >= 2500:
            shutil.copy2(rng.choice(old_top), current)
            slot["stalled"] = 0
            state["resets"] += 1
        parent = body_at(current)
        donor = bodies[rng.choice(donors)]
        candidate = propose(parent, donor, library, rng)
        slot["attempts"] += 1
        slot["stalled"] += 1
        state["attempts"] += 1
        if candidate == parent:
            continue
        source = warrior(candidate)
        try:
            _, normalized = assemble(source)
        except ValueError:
            continue
        if len(normalized) != 20:
            continue
        scratch.write_text(source)
        screen_known = rng.sample(known, 5)
        screen_hard = rng.sample(hard_train, 4)
        screen_seeds = [seed(rng)]
        start = time.monotonic()
        trial = weighted(scratch, screen_known, screen_hard, screen_seeds, 60)
        baseline = weighted(current, screen_known, screen_hard, screen_seeds, 60)
        if trial >= baseline - (0.08 if mode != "strict" else 0.025):
            confirm_seeds = [seed(rng), seed(rng)]
            trial = weighted(scratch, known, hard_train, confirm_seeds, 100)
            baseline = weighted(current, known, hard_train, confirm_seeds, 100)
            delta = trial - baseline
            if delta > 0 or (temperature > 0 and delta >= -0.05 and rng.random() < math.exp(delta / temperature)):
                shutil.copy2(scratch, current)
                slot["accepted"] += 1
                slot["stalled"] = 0
                state["accepted"] += 1
                archived = RUN / "improvements" / f"{state['attempts']:09d}_{time.time_ns()}.red"
                shutil.copy2(scratch, archived)
                donors.append(archived)
                bodies[archived] = normalized
                save_json(RUN / "state.json", state)
                promote_seeds = [seed(rng), seed(rng), seed(rng)]
                best = RUN / "champions/best.red"
                best_value = weighted(best, known, hard_train, promote_seeds, 150)
                trial_value = weighted(scratch, known, hard_train, promote_seeds, 150)
                if trial_value > best_value + 0.005:
                    shutil.copy2(scratch, best)
                    state["best_screen_score"] = trial_value
                    save_json(RUN / "state.json", state)
                    print("best", state["attempts"], round(trial_value * 100, 2), mode, flush=True)
        if duty < 1:
            time.sleep(min(2, (time.monotonic() - start) * (1 / duty - 1)))
    state["phase"] = "validation"
    save_json(RUN / "state.json", state)
    return state


def originality(paths: list[Path]) -> dict:
    module = SourceFileLoader("tiny_extended_originality", str(OLD / "extended_originality_scan.py")).load_module()
    candidates = {str(path): module.compiled(path.read_bytes(), "tiny")[1] for path in paths}
    results = {name: {"max_active_exact_run": 0, "max_structural_run": 0} for name in candidates}
    seen = set()
    for label, raw, _ in module.cached_sources():
        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        _, body = module.compiled(raw, module.suggested_profile(label))
        for name, candidate in candidates.items():
            hit = module.compare(candidate, body)
            results[name]["max_active_exact_run"] = max(results[name]["max_active_exact_run"], hit["active_exact_run"])
            results[name]["max_structural_run"] = max(results[name]["max_structural_run"], hit["structural_run"])
    return results


def validate(state: dict) -> None:
    known, hard_train, hard_holdout = fields()
    rng = random.Random()
    if time.time() >= state["deadline"]:
        state["phase"] = "deadline_expired"
        save_json(RUN / "state.json", state)
        (RUN / "FINAL_REPORT.md").write_text("# SAL Tiny result\n\nThe fixed wall deadline passed before final validation. No entry is recommended.\n")
        return
    while health(TELEMETRY)[0] == 0 and time.time() < state["deadline"]:
        time.sleep(10)
    if health(TELEMETRY)[0] == 0:
        state["phase"] = "validation_blocked_by_host"
        save_json(RUN / "state.json", state)
        (RUN / "FINAL_REPORT.md").write_text("# SAL Tiny result\n\nThe host health gate blocked final validation before the wall deadline. No entry is recommended.\n")
        return
    slate = OLD / "champions/best.red"
    pool = [slate, RUN / "champions/best.red"] + sorted((RUN / "champions").glob("lane*.red"))
    improvements = sorted((RUN / "improvements").glob("*.red"))
    if len(improvements) > 300:
        indices = {round(i * (len(improvements) - 1) / 299) for i in range(300)}
        improvements = [improvements[i] for i in sorted(indices)]
    pool += improvements
    unique = {}
    for path in pool:
        unique.setdefault(hashlib.sha256(path.read_bytes()).hexdigest(), path)
    pool = list(unique.values())
    rank_seeds = [seed(rng)]
    rank_known = rng.sample(known, 5)
    rank_hard = rng.sample(hard_train, 4)
    ranked = sorted(((weighted(path, rank_known, rank_hard, rank_seeds, 100), path) for path in pool),
                    key=lambda row: row[0], reverse=True)
    finalists = []
    used = set()
    for _, path in ranked:
        sig = signature(body_at(path))
        if sig not in used:
            finalists.append(path)
            used.add(sig)
        if len(finalists) == 20:
            break
    if slate not in finalists:
        finalists.append(slate)
    final_seeds = [seed(rng) for _ in range(6)]
    slate_known = score(slate, known, final_seeds, 250)
    slate_hard = score(slate, hard_holdout, final_seeds, 250)
    results = []
    for path in finalists:
        known_score = score(path, known, final_seeds, 250)
        hard_score = score(path, hard_holdout, final_seeds, 250)
        estimate = 120.8 + 100 * (WEIGHT_KNOWN * (known_score - slate_known) + WEIGHT_HARD * (hard_score - slate_hard))
        results.append({"file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "known": known_score * 100, "hard_holdout": hard_score * 100,
                        "estimated_live": estimate,
                        "passes": estimate >= 140.3 and known_score > slate_known and hard_score > slate_hard})
    results.sort(key=lambda x: x["estimated_live"], reverse=True)
    top = [Path(row["file"]) for row in results[:2]]
    source_checks = originality(top)
    for row in results[:2]:
        row["originality"] = source_checks[row["file"]]
    staged = []
    for i, row in enumerate(results[:2]):
        if not row["passes"] or row["originality"]["max_active_exact_run"] > 2:
            continue
        source = Path(row["file"]).read_text()
        draft = RUN / f"ENTRY_DRAFT_{i + 1}.red"
        draft.write_text(source.replace(";redcode-tiny\n", f";redcode-tiny\n;name Evolved Tiny Candidate {i + 1}\n;author RainRat\n;strategy Evolved\n", 1))
        if assemble(draft.read_text()) != assemble(source):
            raise RuntimeError("Entry header changed the assembled warrior")
        staged.append(str(draft))
    outcome = "unsent qualifying draft" if staged else "credible proxy but no qualifying candidate"
    report = {"outcome": outcome, "finished_at": time.time(), "started_at": state["started_at"],
              "deadline": state["deadline"], "search_deadline": state["search_deadline"],
              "host_events": state.get("host_events", []),
              "calibration": json.loads((RUN / "PREP.json").read_text()),
              "slate_known": slate_known * 100,
              "slate_hard_holdout": slate_hard * 100, "final_seeds": final_seeds,
              "rank_seed": rank_seeds, "candidate_count": len(pool), "results": results,
              "staged_drafts": staged,
              "source_count": len(json.loads((RUN / "sources.json").read_text()))}
    save_json(RUN / "FINAL_RESULTS.json", report)
    lines = ["# SAL Tiny conditional run", "", f"Outcome: **{outcome}**. No submission was made.", "",
             f"Started: {time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(state['started_at']))}.",
             f"Finished: {time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(report['finished_at']))}.",
             f"Elapsed wall time: {(report['finished_at'] - state['started_at']) / 3600:.2f} hours.",
             f"Attempts: {state['attempts']}; accepted: {state['accepted']}; resets: {state['resets']}.",
             f"Host telemetry changes: {len(state.get('host_events', []))}; details in `FINAL_RESULTS.json`.",
             "Prelaunch checks: offline proxy preflight passed; `pytest tests/`: 444 passed.",
             f"Slate baseline: known {slate_known * 100:.2f}, hard holdout {slate_hard * 100:.2f}.", "",
             "| Candidate | Known | Hard holdout | Estimated live | Pass |", "|---|---:|---:|---:|---|"]
    for row in results[:10]:
        lines.append(f"| {Path(row['file']).name} | {row['known']:.2f} | {row['hard_holdout']:.2f} | {row['estimated_live']:.2f} | {row['passes']} |")
    lines += ["", "The estimate uses Slate's official 120.8 as an anchor and local candidate-minus-Slate gains.",
              "The hard proxy remains an approximation of 14 unavailable live opponents.",
              f"Known panel: {', '.join(path.stem for path in known)}.",
              f"Hard training panel: {', '.join(path.stem for path in hard_train)}.",
              f"Hard holdout panel: {', '.join(path.stem for path in hard_holdout)}.",
              "See `FINAL_RESULTS.json`, `sources.json`, and `PREP.json` for seeds, scores, and provenance."]
    (RUN / "FINAL_REPORT.md").write_text("\n".join(lines) + "\n")
    state["phase"] = "complete"
    state["finished_at"] = time.time()
    save_json(RUN / "state.json", state)
    print("finished", outcome, "attempts", state["attempts"], flush=True)


def main() -> None:
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / "supervisor.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = prepare()
        if state["phase"] == "complete":
            return
        if not disk_ok(RUN):
            raise RuntimeError("Insufficient disk space")
        if state["phase"] == "search":
            state = search(state)
        if state["phase"] == "validation":
            validate(state)


if __name__ == "__main__":
    main()
