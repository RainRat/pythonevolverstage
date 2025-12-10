import argparse
import csv
import os
import random
import shutil
import statistics
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple, Union, TextIO

from engine import *
import config as _config_module
from config import (
    _CONFIG_PARSERS,
    BenchmarkWarrior,
    EvolverConfig,
    get_active_config as _config_get_active_config,
    load_configuration as _config_load_configuration,
    set_active_config as _config_set_active_config,
    validate_config as _config_validate_config,
)
from ui import (
    BattleStatisticsTracker,
    ChampionDisplay,
    ConsoleInterface,
    PseudoGraphicalConsole,
    SimpleConsole,
    StatusDisplay,
    VerbosityLevel,
    close_console,
    console_clear_status,
    console_log,
    console_update_champions,
    console_update_status,
    get_console,
    set_console_verbosity,
)


@dataclass
class BenchmarkBattleResult:
    warriors: list[int]
    scores: list[int]
    benchmarks_played: int


config = _config_module.config

_RNG_SEQUENCE: Optional[list[int]] = None
_RNG_INDEX: int = 0

_BENCHMARK_WARRIOR_ID_BASE = MAX_WARRIOR_FILENAME_ID - 10_000

_FINAL_STANDINGS_DISPLAY_LIMIT = 20
_PER_WARRIOR_SUMMARY_LIMIT = 20

def set_rng_sequence(sequence: list[int]) -> None:
    """Set a deterministic RNG sequence for tests."""

    global _RNG_SEQUENCE, _RNG_INDEX
    if sequence:
        _RNG_SEQUENCE = list(sequence)
    else:
        _RNG_SEQUENCE = None
    _RNG_INDEX = 0


def get_random_int(min_val: int, max_val: int) -> int:
    """Return a random integer within ``[min_val, max_val]``."""

    if min_val > max_val:
        raise ValueError("min_val cannot be greater than max_val")

    global _RNG_SEQUENCE, _RNG_INDEX
    if _RNG_SEQUENCE is not None:
        if _RNG_INDEX >= len(_RNG_SEQUENCE):
            raise RuntimeError("Deterministic RNG sequence exhausted")
        value = _RNG_SEQUENCE[_RNG_INDEX]
        _RNG_INDEX += 1
        if value < min_val or value > max_val:
            raise ValueError(
                f"Deterministic RNG value {value} outside range [{min_val}, {max_val}]"
            )
        return value

    return random.randint(min_val, max_val)


configure_rng(
    get_random_int,
    lambda sequence: sequence[get_random_int(0, len(sequence) - 1)]
    if sequence
    else (_ for _ in ()).throw(ValueError("Cannot choose from an empty sequence")),
)


def _select_arena_index(active_config: EvolverConfig) -> int:
    """Choose an arena index, honouring optional per-arena weights."""

    arena_count = active_config.last_arena + 1
    if arena_count <= 0:
        raise ValueError("No arenas configured to select from.")

    weights = active_config.arena_weight_list
    if not weights:
        return get_random_int(0, active_config.last_arena)

    limited_weights = [max(0, weight) for weight in weights[:arena_count]]
    weighted_indices = [
        (index, weight)
        for index, weight in enumerate(limited_weights)
        if weight > 0
    ]

    if not weighted_indices:
        return get_random_int(0, active_config.last_arena)

    total_weight = sum(weight for _, weight in weighted_indices)
    roll = get_random_int(1, total_weight)
    cumulative = 0
    for index, weight in weighted_indices:
        cumulative += weight
        if roll <= cumulative:
            return index

    # Fallback; should not occur but protects against rounding mistakes.
    return weighted_indices[-1][0]



def set_active_config(new_config: EvolverConfig) -> None:
    _config_set_active_config(new_config)
    globals()["config"] = _config_module.config
    set_engine_config(new_config)


def get_active_config() -> EvolverConfig:
    return _config_get_active_config()


def load_configuration(path: str) -> EvolverConfig:
    return _config_load_configuration(path)


def validate_config(active_config: EvolverConfig, config_path: Optional[str] = None) -> None:
    _config_validate_config(active_config, config_path=config_path)




def _run_benchmark_battle(
    arena_index: int,
    cont1: int,
    cont2: int,
    era: int,
    active_config: EvolverConfig,
) -> Optional[BenchmarkBattleResult]:
    benchmark_warriors = active_config.benchmark_sets.get(arena_index)
    if not benchmark_warriors or era < 0:
        return None

    storage = get_arena_storage()
    cont1_lines = storage.get_warrior_lines(arena_index, cont1)
    cont2_lines = storage.get_warrior_lines(arena_index, cont2)
    if not cont1_lines or not cont2_lines:
        return None

    cont1_code = "".join(cont1_lines)
    cont2_code = "".join(cont2_lines)
    if not cont1_code.strip() or not cont2_code.strip():
        return None

    totals: defaultdict[int, int] = defaultdict(int)
    benchmarks_played = 0

    for bench_index, benchmark in enumerate(benchmark_warriors):
        bench_identifier = max(
            1, _BENCHMARK_WARRIOR_ID_BASE - (arena_index * 1000 + bench_index)
        )
        round_scores: dict[int, int] = {}
        for warrior_id, warrior_code in ((cont1, cont1_code), (cont2, cont2_code)):
            match_seed = _stable_internal_battle_seed(
                arena_index, warrior_id, bench_identifier, era
            )
            warriors, scores = execute_battle_with_sources(
                arena_index,
                warrior_id,
                warrior_code,
                bench_identifier,
                benchmark.code,
                era,
                verbose=False,
                seed=match_seed,
            )
            try:
                warrior_pos = warriors.index(warrior_id)
            except ValueError:
                return None
            round_scores[warrior_id] = scores[warrior_pos]

        if len(round_scores) < 2:
            return None

        for warrior_id, score in round_scores.items():
            totals[warrior_id] += score
        benchmarks_played += 1

    if benchmarks_played == 0:
        return None

    cont1_total = totals.get(cont1, 0)
    cont2_total = totals.get(cont2, 0)
    return BenchmarkBattleResult(
        warriors=[cont1, cont2],
        scores=[cont1_total, cont2_total],
        benchmarks_played=benchmarks_played,
    )


class DataLogger:
    def __init__(self, filename: Optional[str]):
        self.filename = filename
        self.fieldnames = ['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with']
        self.file_handle: Optional[TextIO] = None
        self.writer: Optional[csv.DictWriter] = None

    def open(self) -> None:
        if not self.filename or self.file_handle is not None:
            return

        file_handle = open(self.filename, 'a', newline='')
        writer = csv.DictWriter(file_handle, fieldnames=self.fieldnames)
        if file_handle.tell() == 0:
            writer.writeheader()

        self.file_handle = file_handle
        self.writer = writer

    def close(self) -> None:
        if self.file_handle is not None:
            self.file_handle.close()
            self.file_handle = None
            self.writer = None

    def log_data(self, **kwargs):
        if not self.filename:
            return

        if self.writer is None:
            self.open()

        if self.writer is not None:
            self.writer.writerow(kwargs)
            if self.file_handle is not None:
                self.file_handle.flush()


class BenchmarkLogger:
    def __init__(self, filename: Optional[str]):
        self.filename = filename
        self.fieldnames = [
            "era",
            "generation",
            "arena",
            "champion",
            "benchmark",
            "score",
            "benchmark_path",
        ]
        self.file_handle: Optional[TextIO] = None
        self.writer: Optional[csv.DictWriter] = None

    @property
    def enabled(self) -> bool:
        return bool(self.filename)

    def open(self) -> None:
        if not self.filename or self.file_handle is not None:
            return

        file_handle = open(self.filename, "a", newline="")
        writer = csv.DictWriter(file_handle, fieldnames=self.fieldnames)
        if file_handle.tell() == 0:
            writer.writeheader()

        self.file_handle = file_handle
        self.writer = writer

    def close(self) -> None:
        if self.file_handle is not None:
            self.file_handle.close()
            self.file_handle = None
            self.writer = None

    def log_score(
        self,
        *,
        era: int,
        generation: int,
        arena: int,
        champion: int,
        benchmark: str,
        score: int,
        benchmark_path: Optional[str],
    ) -> None:
        if not self.filename:
            return

        if self.writer is None:
            self.open()

        if self.writer is not None:
            self.writer.writerow(
                {
                    "era": era,
                    "generation": generation,
                    "arena": arena,
                    "champion": champion,
                    "benchmark": benchmark,
                    "score": score,
                    "benchmark_path": benchmark_path or "",
                }
            )
            if self.file_handle is not None:
                self.file_handle.flush()


def _score_warrior_against_benchmarks(
    arena_index: int,
    warrior_id: int,
    era: int,
    active_config: EvolverConfig,
) -> list[tuple[BenchmarkWarrior, int]]:
    benchmark_warriors = active_config.benchmark_sets.get(arena_index)
    if not benchmark_warriors or era < 0:
        return []

    storage = get_arena_storage()
    warrior_lines = storage.get_warrior_lines(arena_index, warrior_id)
    if not warrior_lines:
        return []

    warrior_code = "".join(warrior_lines)
    if not warrior_code.strip():
        return []

    results: list[tuple[BenchmarkWarrior, int]] = []
    for bench_index, benchmark in enumerate(benchmark_warriors):
        bench_identifier = max(
            1, _BENCHMARK_WARRIOR_ID_BASE - (arena_index * 1000 + bench_index)
        )
        match_seed = _stable_internal_battle_seed(
            arena_index, warrior_id, bench_identifier, era
        )
        warriors, scores = execute_battle_with_sources(
            arena_index,
            warrior_id,
            warrior_code,
            bench_identifier,
            benchmark.code,
            era,
            verbose=False,
            seed=match_seed,
        )
        try:
            warrior_pos = warriors.index(warrior_id)
        except ValueError:
            continue
        results.append((benchmark, scores[warrior_pos]))

    return results


def _log_benchmark_scores_for_champions(
    *,
    era: int,
    generation: int,
    champions: dict[int, int],
    active_config: EvolverConfig,
    benchmark_logger: BenchmarkLogger,
) -> None:
    if era < 0 or generation <= 0 or not benchmark_logger.enabled:
        return

    for arena_index in range(active_config.last_arena + 1):
        champion_id = champions.get(arena_index)
        if champion_id is None:
            continue

        scores = _score_warrior_against_benchmarks(
            arena_index, champion_id, era, active_config
        )
        for benchmark, score in scores:
            benchmark_logger.log_score(
                era=era,
                generation=generation,
                arena=arena_index,
                champion=champion_id,
                benchmark=benchmark.name,
                score=score,
                benchmark_path=benchmark.path,
            )


def _count_instruction_library_entries(library_path: Optional[str]) -> int:
    if not library_path:
        return 0

    library_cache = ensure_instruction_library_cache(library_path)
    return sum(1 for line in library_cache if line.strip() and not line.lstrip().startswith(";"))


def _print_run_configuration_summary(active_config: EvolverConfig) -> None:
    log_display = active_config.battle_log_file if active_config.battle_log_file else "Disabled"
    if active_config.benchmark_log_file:
        benchmark_log_display = (
            f"{active_config.benchmark_log_file} "
            f"(every {active_config.benchmark_log_generation_interval} generations)"
        )
    else:
        benchmark_log_display = "Disabled"
    arena_count = active_config.last_arena + 1 if active_config.last_arena is not None else 0
    archive_count = get_archive_storage().count()
    library_entries = _count_instruction_library_entries(active_config.library_path)
    if active_config.library_path:
        library_display = f"{library_entries} entries from {active_config.library_path}"
    else:
        library_display = f"{library_entries} entries (no library configured)"

    console_log("Run configuration summary:", minimum_level=VerbosityLevel.TERSE)
    console_log(
        f"  Battle log: {log_display}", minimum_level=VerbosityLevel.TERSE
    )
    console_log(
        f"  Benchmark log: {benchmark_log_display}",
        minimum_level=VerbosityLevel.TERSE,
    )
    console_log(f"  Arenas: {arena_count}", minimum_level=VerbosityLevel.TERSE)
    console_log(
        f"  Battle engine: {active_config.battle_engine}",
        minimum_level=VerbosityLevel.TERSE,
    )
    if active_config.use_in_memory_arenas:
        storage_display = (
            "In-memory (checkpoint every "
            f"{active_config.arena_checkpoint_interval} battles)"
        )
    else:
        storage_display = "On-disk"
    console_log(
        f"  Arena storage: {storage_display}",
        minimum_level=VerbosityLevel.TERSE,
    )
    console_log(
        "  Final tournament enabled: "
        f"{'Yes' if active_config.run_final_tournament else 'No'}",
        minimum_level=VerbosityLevel.TERSE,
    )
    csv_display = active_config.final_tournament_csv or "Disabled"
    console_log(
        f"  Final tournament CSV export: {csv_display}",
        minimum_level=VerbosityLevel.TERSE,
    )
    console_log("", minimum_level=VerbosityLevel.TERSE)


def _print_evolution_statistics(
    battles_per_era: Sequence[int],
    total_battles: int,
    runtime_seconds: float,
) -> None:
    console_log("Evolution statistics:", minimum_level=VerbosityLevel.TERSE)
    if not battles_per_era:
        console_log("  No battles were executed.", minimum_level=VerbosityLevel.TERSE)
    else:
        for index, battle_count in enumerate(battles_per_era, start=1):
            console_log(
                f"  Era {index}: {battle_count} battles",
                minimum_level=VerbosityLevel.TERSE,
            )
        console_log(
            f"  Total battles: {total_battles}", minimum_level=VerbosityLevel.TERSE
        )

    if runtime_seconds > 0 and total_battles > 0:
        battles_per_hour = total_battles / (runtime_seconds / 3600)
        console_log(
            f"  Approximate speed: {battles_per_hour:.2f} battles/hour",
            minimum_level=VerbosityLevel.TERSE,
        )
    else:
        console_log("  Approximate speed: n/a", minimum_level=VerbosityLevel.TERSE)
    console_log("", minimum_level=VerbosityLevel.TERSE)


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f} seconds"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)} minutes {secs:.2f} seconds"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)} hours {int(minutes)} minutes {secs:.2f} seconds"


def _get_progress_status(
    start_time: float, total_duration_hr: float, current_era: int
) -> tuple[str, str]:
    runtime_seconds = time.time() - start_time
    runtime_in_hours = runtime_seconds / 3600
    if total_duration_hr > 0:
        seconds_remaining = max((total_duration_hr - runtime_in_hours) * 3600, 0.0)
        percent_complete = (runtime_in_hours / total_duration_hr) * 100
        percent_complete = min(max(percent_complete, 0.0), 100.0)
    else:
        seconds_remaining = 0.0
        percent_complete = 100.0

    display_era = current_era + 1
    if current_era >= 0:
        progress_line = (
            f"{_format_duration(seconds_remaining)} remaining "
            f"({percent_complete:.2f}% complete) Era: {display_era}"
        )
        detail_line = f"Era {display_era}"
    else:
        progress_line = (
            f"{_format_duration(seconds_remaining)} remaining "
            f"({percent_complete:.2f}% complete)"
        )
        detail_line = "No active era"

    return progress_line, detail_line


def _update_final_tournament_status(
    *,
    battles_completed: int,
    total_battles: int,
    tournament_start: float,
    active_config: EvolverConfig,
    final_era_index: int,
    detail_line: Optional[str],
) -> None:
    percent_complete = (
        battles_completed / total_battles * 100 if total_battles else 100.0
    )
    time_progress, default_detail = _get_progress_status(
        tournament_start, active_config.clock_time, final_era_index
    )
    progress_segments = []
    if active_config.clock_time:
        progress_segments.append(time_progress)
    progress_segments.append(
        f"Final Tournament Progress: {battles_completed}/{total_battles} "
        f"battles ({percent_complete:.2f}% complete)"
    )
    progress_line = " | ".join(progress_segments)
    console_update_status(progress_line, detail_line or default_detail)


def _run_benchmark_tournament(
    arena: int,
    warrior_ids: Sequence[int],
    benchmark_warriors: Sequence[BenchmarkWarrior],
    *,
    storage: ArenaStorage,
    final_era_index: int,
    active_config: EvolverConfig,
    total_battles: int,
    tournament_start: float,
    battles_completed: int,
    warrior_scores_by_arena: dict[int, list[int]],
) -> tuple[dict[int, int], int, dict[int, float], dict[int, int]]:
    total_scores = {warrior_id: 0 for warrior_id in warrior_ids}
    benchmark_totals: dict[int, float] = {}
    benchmark_counts: dict[int, int] = {}
    missing_warriors: set[tuple[int, int]] = set()

    for bench_index, benchmark in enumerate(benchmark_warriors):
        benchmark_totals.setdefault(bench_index, 0.0)
        benchmark_counts.setdefault(bench_index, 0)
        bench_identifier = max(
            1,
            _BENCHMARK_WARRIOR_ID_BASE - (arena * 1000 + bench_index),
        )

        for warrior_id in warrior_ids:
            warrior_lines = storage.get_warrior_lines(arena, warrior_id)
            if not warrior_lines:
                if (arena, warrior_id) not in missing_warriors:
                    console_log(
                        f"Arena {arena}: warrior {warrior_id} has no code; skipping benchmark match.",
                        minimum_level=VerbosityLevel.TERSE,
                    )
                    missing_warriors.add((arena, warrior_id))
                continue
            warrior_code = "".join(warrior_lines)
            if not warrior_code.strip():
                if (arena, warrior_id) not in missing_warriors:
                    console_log(
                        f"Arena {arena}: warrior {warrior_id} is empty; skipping benchmark match.",
                        minimum_level=VerbosityLevel.TERSE,
                    )
                    missing_warriors.add((arena, warrior_id))
                continue

            match_seed = _stable_internal_battle_seed(
                arena, warrior_id, bench_identifier, final_era_index
            )
            warriors, scores = execute_battle_with_sources(
                arena,
                warrior_id,
                warrior_code,
                bench_identifier,
                benchmark.code,
                final_era_index,
                verbose=False,
                seed=match_seed,
            )

            try:
                warrior_pos = warriors.index(warrior_id)
                benchmark_pos = warriors.index(bench_identifier)
            except ValueError:
                console_log(
                    "Benchmark battle returned unexpected warrior identifiers; ignoring result.",
                    minimum_level=VerbosityLevel.TERSE,
                )
                continue

            warrior_score = scores[warrior_pos]
            benchmark_score = scores[benchmark_pos]
            total_scores[warrior_id] = total_scores.get(warrior_id, 0) + warrior_score
            warrior_scores_by_arena.setdefault(warrior_id, []).append(warrior_score)
            benchmark_totals[bench_index] += benchmark_score
            benchmark_counts[bench_index] += 1

            battles_completed += 1
            detail_line = (
                f"Arena {arena} | Warrior {warrior_id} ({warrior_score}) vs "
                f"benchmark {benchmark.name} ({benchmark_score})"
            )
            _update_final_tournament_status(
                battles_completed=battles_completed,
                total_battles=total_battles,
                tournament_start=tournament_start,
                active_config=active_config,
                final_era_index=final_era_index,
                detail_line=detail_line,
            )

    return total_scores, battles_completed, benchmark_totals, benchmark_counts


def _run_round_robin_tournament(
    arena: int,
    warrior_ids: Sequence[int],
    *,
    final_era_index: int,
    active_config: EvolverConfig,
    total_battles: int,
    tournament_start: float,
    battles_completed: int,
    warrior_scores_by_arena: dict[int, list[int]],
) -> tuple[dict[int, int], int]:
    total_scores = {warrior_id: 0 for warrior_id in warrior_ids}

    for idx, cont1 in enumerate(warrior_ids):
        for cont2 in warrior_ids[idx + 1 :]:
            match_seed = _stable_internal_battle_seed(
                arena, cont1, cont2, final_era_index
            )
            warriors, scores = execute_battle(
                arena,
                cont1,
                cont2,
                final_era_index,
                verbose=False,
                battlerounds_override=1,
                seed=match_seed,
            )
            for warrior_id, score in zip(warriors, scores):
                total_scores[warrior_id] = total_scores.get(warrior_id, 0) + score
                warrior_scores_by_arena.setdefault(warrior_id, []).append(score)

            battles_completed += 1
            if len(warriors) >= 2 and len(scores) >= 2:
                detail_line = (
                    f"Arena {arena} | {warriors[0]} ({scores[0]}) vs "
                    f"{warriors[1]} ({scores[1]})"
                )
            else:
                detail_line = f"Arena {arena} battle in progress"
            _update_final_tournament_status(
                battles_completed=battles_completed,
                total_battles=total_battles,
                tournament_start=tournament_start,
                active_config=active_config,
                final_era_index=final_era_index,
                detail_line=detail_line,
            )

    return total_scores, battles_completed


def _log_era_summary(
    era_index: int,
    battles_per_era: Sequence[int],
    archived_per_era: Sequence[int],
    unarchived_per_era: Sequence[int],
) -> None:
    if not (0 <= era_index < len(battles_per_era)):
        return
    era_number = era_index + 1
    summary_lines = [
        f"Era {era_number} summary:",
        f"  Battles: {battles_per_era[era_index]}",
        f"  Warriors archived: {archived_per_era[era_index]}",
        f"  Warriors unarchived: {unarchived_per_era[era_index]}",
    ]
    console_log("\n".join(summary_lines), minimum_level=VerbosityLevel.DEFAULT)


def _build_marble_bag(
    era: int, active_config: EvolverConfig
) -> list[BaseMutationStrategy]:
    bag: list[BaseMutationStrategy] = []

    bag.extend(DoNothingMutation() for _ in range(active_config.nothing_list[era]))
    bag.extend(MajorMutation() for _ in range(active_config.random_list[era]))
    bag.extend(NabInstruction() for _ in range(active_config.nab_list[era]))
    bag.extend(MinorMutation() for _ in range(active_config.mini_mut_list[era]))
    bag.extend(MicroMutation() for _ in range(active_config.micro_mut_list[era]))
    bag.extend(
        InstructionLibraryMutation()
        for _ in range(active_config.library_list[era])
    )
    bag.extend(
        MagicNumberMutation() for _ in range(active_config.magic_number_list[era])
    )

    return bag


def _load_tournament_warriors(
    arena: int,
    active_config: EvolverConfig,
    storage: ArenaStorage,
    *,
    final_era_index: int,
    use_benchmarks: bool,
    use_in_memory_internal: bool,
) -> tuple[list[int], list[BenchmarkWarrior], int] | None:
    if not use_in_memory_internal:
        arena_dir = os.path.join(active_config.base_path, f"arena{arena}")
        if not os.path.isdir(arena_dir):
            console_log(
                f"Arena {arena} directory '{arena_dir}' not found. Skipping.",
                minimum_level=VerbosityLevel.TERSE,
            )
            return None

    warrior_ids = [
        warrior_id
        for warrior_id in range(1, active_config.numwarriors + 1)
        if storage.get_warrior_lines(arena, warrior_id)
    ]

    if not warrior_ids:
        console_log(
            f"Arena {arena}: no warriors available for the final tournament.",
            minimum_level=VerbosityLevel.TERSE,
        )
        return None

    benchmark_warriors = (
        list(active_config.benchmark_sets.get(arena, [])) if use_benchmarks else []
    )
    if use_benchmarks and not benchmark_warriors:
        console_log(
            f"Arena {arena}: no benchmark warriors configured; using round-robin scoring.",
            minimum_level=VerbosityLevel.TERSE,
        )

    if benchmark_warriors:
        arena_battles = len(warrior_ids) * len(benchmark_warriors)
    else:
        if len(warrior_ids) < 2:
            console_log(
                f"Arena {arena}: not enough warriors for a round-robin tournament. Skipping.",
                minimum_level=VerbosityLevel.TERSE,
            )
            return None

        arena_battles = (
            len(warrior_ids)
            * (len(warrior_ids) - 1)
            // 2
            * active_config.battlerounds_list[final_era_index]
        )

    return warrior_ids, benchmark_warriors, arena_battles


def _print_tournament_standings(
    arena: int,
    rankings: list[tuple[int, int]],
    benchmark_summary: Optional[Sequence[dict[str, object]]],
    active_config: EvolverConfig,
) -> None:
    console_clear_status()
    console_log(
        f"\nArena {arena} final standings:",
        minimum_level=VerbosityLevel.TERSE,
    )
    standings_to_show = rankings[:_FINAL_STANDINGS_DISPLAY_LIMIT]
    for position, (warrior_id, score) in enumerate(standings_to_show, start=1):
        console_log(
            f"{position}. Warrior {warrior_id}: {score} points",
            minimum_level=VerbosityLevel.TERSE,
        )
    hidden_count = max(0, len(rankings) - len(standings_to_show))
    if hidden_count:
        if active_config.final_tournament_csv:
            destination_hint = (
                f"Full standings exported to {active_config.final_tournament_csv}."
            )
        else:
            destination_hint = "Configure FINAL_TOURNAMENT_CSV to export full standings."
        console_log(
            f"  ...and {hidden_count} more warrior(s) not shown. {destination_hint}",
            minimum_level=VerbosityLevel.TERSE,
        )
    champion_id, champion_score = rankings[0]
    console_log(
        f"Champion: Warrior {champion_id} with {champion_score} points",
        minimum_level=VerbosityLevel.TERSE,
    )
    if benchmark_summary:
        console_log(
            "Benchmark reference (scores from the benchmark perspective):",
            minimum_level=VerbosityLevel.TERSE,
        )
        for entry in benchmark_summary:
            console_log(
                "  {name}: {avg:.2f} over {count} match(es)".format(
                    name=entry.get("name", "unknown"),
                    avg=float(entry.get("average", 0.0)),
                    count=int(entry.get("matches", 0)),
                ),
                minimum_level=VerbosityLevel.TERSE,
            )


def run_final_tournament(active_config: EvolverConfig):
    console_clear_status()
    if active_config.last_arena < 0:
        console_log(
            "No arenas configured. Skipping final tournament.",
            minimum_level=VerbosityLevel.TERSE,
        )
        return
    benchmark_available = (
        active_config.benchmark_final_tournament
        and any(active_config.benchmark_sets.values())
    )
    if active_config.numwarriors <= 1 and not benchmark_available:
        console_log(
            "Not enough warriors to run a final tournament.",
            minimum_level=VerbosityLevel.TERSE,
        )
        return
    if not active_config.battlerounds_list:
        console_log(
            "Battle rounds configuration missing. Cannot run final tournament.",
            minimum_level=VerbosityLevel.TERSE,
        )
        return

    try:
        storage = get_arena_storage()
    except RuntimeError:
        storage = create_arena_storage(active_config)
        set_arena_storage(storage)
    else:
        storage_config = getattr(storage, "_config", None)
        if storage_config is not None and storage_config.base_path != active_config.base_path:
            storage = create_arena_storage(active_config)
            set_arena_storage(storage)
    if active_config.use_in_memory_arenas:
        storage.load_existing()

    final_era_index = max(0, len(active_config.battlerounds_list) - 1)
    use_in_memory_internal = (
        active_config.use_in_memory_arenas and active_config.battle_engine == 'internal'
    )
    use_benchmarks = (
        active_config.benchmark_final_tournament
        and any(active_config.benchmark_sets.values())
    )
    console_log(
        "\n================ Final Tournament ================",
        minimum_level=VerbosityLevel.TERSE,
    )
    arenas_to_run: list[tuple[int, list[int], list[BenchmarkWarrior]]] = []
    total_battles = 0
    arena_summaries: list[dict[str, object]] = []
    warrior_scores_by_arena: dict[int, list[int]] = {}
    for arena in range(0, active_config.last_arena + 1):
        load_result = _load_tournament_warriors(
            arena,
            active_config,
            storage,
            final_era_index=final_era_index,
            use_benchmarks=use_benchmarks,
            use_in_memory_internal=use_in_memory_internal,
        )
        if load_result is None:
            continue
        warrior_ids, benchmark_warriors, arena_battles = load_result
        total_battles += arena_battles
        arenas_to_run.append((arena, warrior_ids, benchmark_warriors))

    if not arenas_to_run:
        console_log(
            "No arenas with enough warriors for the final tournament.",
            minimum_level=VerbosityLevel.TERSE,
        )
        return

    for _, warrior_ids, _ in arenas_to_run:
        for warrior_id in warrior_ids:
            warrior_scores_by_arena.setdefault(warrior_id, [])

    tournament_start = time.time()
    battles_completed = 0
    try:
        for arena, warrior_ids, benchmark_warriors in arenas_to_run:
            if benchmark_warriors:
                (
                    total_scores,
                    battles_completed,
                    benchmark_totals,
                    benchmark_counts,
                ) = _run_benchmark_tournament(
                    arena,
                    warrior_ids,
                    benchmark_warriors,
                    storage=storage,
                    final_era_index=final_era_index,
                    active_config=active_config,
                    total_battles=total_battles,
                    tournament_start=tournament_start,
                    battles_completed=battles_completed,
                    warrior_scores_by_arena=warrior_scores_by_arena,
                )
            else:
                benchmark_totals = {}
                benchmark_counts = {}
                total_scores, battles_completed = _run_round_robin_tournament(
                    arena,
                    warrior_ids,
                    final_era_index=final_era_index,
                    active_config=active_config,
                    total_battles=total_battles,
                    tournament_start=tournament_start,
                    battles_completed=battles_completed,
                    warrior_scores_by_arena=warrior_scores_by_arena,
                )

            rankings = sorted(total_scores.items(), key=lambda item: item[1], reverse=True)
            benchmark_summary: Optional[list[dict[str, object]]] = None
            if benchmark_warriors:
                benchmark_summary = []
                for bench_index, benchmark in enumerate(benchmark_warriors):
                    count = benchmark_counts.get(bench_index, 0)
                    average = (
                        benchmark_totals.get(bench_index, 0.0) / count
                        if count
                        else 0.0
                    )
                    benchmark_summary.append(
                        {
                            "name": benchmark.name,
                            "average": average,
                            "matches": count,
                            "path": benchmark.path,
                        }
                    )

            _print_tournament_standings(
                arena,
                rankings,
                benchmark_summary,
                active_config,
            )

            arena_average = (
                statistics.mean(total_scores.values()) if total_scores else 0.0
            )
            summary_entry: dict[str, object] = {
                "arena": arena,
                "rankings": list(rankings),
                "average": arena_average,
                "mode": "benchmark" if benchmark_warriors else "round_robin",
            }

            if benchmark_summary:
                summary_entry["benchmark"] = benchmark_summary

            arena_summaries.append(summary_entry)
    except KeyboardInterrupt:
        console_clear_status()
        console_log(
            "Final tournament interrupted by user.",
            minimum_level=VerbosityLevel.TERSE,
        )
        return

    console_clear_status()
    duration = time.time() - tournament_start
    _report_final_tournament_statistics(arena_summaries, warrior_scores_by_arena)
    _export_final_tournament_results(arena_summaries, active_config)
    console_log(
        f"Final tournament completed in {_format_duration(duration)}.",
        minimum_level=VerbosityLevel.TERSE,
    )

def _report_final_tournament_statistics(
    arena_summaries: Sequence[dict[str, object]],
    warrior_scores_by_arena: dict[int, list[int]],
) -> None:
    if not arena_summaries:
        return

    console_log(
        "\nTournament statistics:", minimum_level=VerbosityLevel.TERSE
    )
    aggregated_benchmarks: dict[str, dict[str, float]] = {}

    for summary in arena_summaries:
        arena_id = summary.get("arena")
        arena_average = float(summary.get("average", 0.0))
        console_log(
            f"  Arena {arena_id} average score: {arena_average:.2f}",
            minimum_level=VerbosityLevel.TERSE,
        )
        benchmark_info = summary.get("benchmark")
        if benchmark_info:
            total_matches = 0
            for entry in benchmark_info:
                name = entry.get("name", "unknown")
                average = float(entry.get("average", 0.0))
                count = int(entry.get("matches", 0))
                total_matches += count
                aggregate = aggregated_benchmarks.setdefault(
                    name, {"total": 0.0, "matches": 0}
                )
                aggregate["total"] += average * count
                aggregate["matches"] += count
            console_log(
                f"    Benchmarks played: {total_matches} match(es) across {len(benchmark_info)} warrior(s)",
                minimum_level=VerbosityLevel.TERSE,
            )

    if aggregated_benchmarks:
        console_log(
            "\nBenchmark performance summary (benchmark perspective):",
            minimum_level=VerbosityLevel.TERSE,
        )
        for name in sorted(aggregated_benchmarks):
            matches = int(aggregated_benchmarks[name]["matches"])
            total = float(aggregated_benchmarks[name]["total"])
            average = total / matches if matches else 0.0
            console_log(
                f"  {name}: {average:.2f} over {matches} match(es)",
                minimum_level=VerbosityLevel.TERSE,
            )

    all_scores = [score for scores in warrior_scores_by_arena.values() for score in scores]
    if all_scores:
        overall_average = statistics.mean(all_scores)
        console_log(
            f"  Overall average score: {overall_average:.2f}",
            minimum_level=VerbosityLevel.TERSE,
        )

    warrior_stats: list[dict[str, object]] = []
    for warrior_id in sorted(warrior_scores_by_arena):
        scores = warrior_scores_by_arena[warrior_id]
        if not scores:
            continue
        average_score = statistics.mean(scores)
        deviation = statistics.pstdev(scores) if len(scores) > 1 else 0.0
        warrior_stats.append(
            {
                "warrior_id": warrior_id,
                "average": average_score,
                "stdev": deviation,
                "appearances": len(scores),
            }
        )

    if not warrior_stats:
        return

    console_log(
        "\nPer-warrior performance summary:",
        minimum_level=VerbosityLevel.TERSE,
    )
    sorted_warriors = sorted(
        warrior_stats,
        key=lambda data: (
            -float(data["average"]),
            float(data["stdev"]),
            int(data["warrior_id"]),
        ),
    )
    warriors_to_show = sorted_warriors[:_PER_WARRIOR_SUMMARY_LIMIT]
    for entry in warriors_to_show:
        console_log(
            "  Warrior {warrior_id}: avg {avg:.2f}, σ {stdev:.2f} across {count} match(es)".format(
                warrior_id=entry["warrior_id"],
                avg=entry["average"],
                stdev=entry["stdev"],
                count=entry["appearances"],
            ),
            minimum_level=VerbosityLevel.TERSE,
        )
    hidden_warriors = max(0, len(sorted_warriors) - len(warriors_to_show))
    if hidden_warriors:
        console_log(
            f"  ...and {hidden_warriors} more warrior(s) not shown.",
            minimum_level=VerbosityLevel.TERSE,
        )

    consistent_candidates = [
        entry
        for entry in warrior_stats
        if int(entry["appearances"]) > 1 and float(entry["average"]) > 0.0
    ]
    if not consistent_candidates:
        consistent_candidates = [
            entry for entry in warrior_stats if int(entry["appearances"]) > 1
        ]
    if not consistent_candidates:
        consistent_candidates = list(warrior_stats)

    consistent_candidates.sort(
        key=lambda data: (
            float(data["stdev"]),
            -float(data["average"]),
            int(data["warrior_id"]),
        )
    )
    top_consistent = consistent_candidates[: min(3, len(consistent_candidates))]
    if top_consistent:
        console_log(
            "\nMost consistent performers:",
            minimum_level=VerbosityLevel.TERSE,
        )
        for entry in top_consistent:
            console_log(
                "  Warrior {warrior_id}: σ {stdev:.2f} across {count} match(es) (avg {avg:.2f})".format(
                    warrior_id=entry["warrior_id"],
                    stdev=entry["stdev"],
                    count=entry["appearances"],
                    avg=entry["average"],
                ),
                minimum_level=VerbosityLevel.TERSE,
            )


def _export_final_tournament_results(
    arena_summaries: Sequence[dict[str, object]], active_config: EvolverConfig
) -> None:
    if not active_config.final_tournament_csv or not arena_summaries:
        return

    output_path = active_config.final_tournament_csv
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    try:
        with open(output_path, "w", newline="") as csv_file:
            fieldnames = ["arena", "warrior_id", "rank", "score"]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for summary in arena_summaries:
                arena_id = summary.get("arena")
                rankings = summary.get("rankings", [])
                for rank, result in enumerate(rankings, start=1):
                    warrior_id, score = result
                    writer.writerow(
                        {
                            "arena": arena_id,
                            "warrior_id": warrior_id,
                            "rank": rank,
                            "score": score,
                        }
                    )
        console_log(
            f"Final tournament results exported to {output_path}",
            minimum_level=VerbosityLevel.TERSE,
        )
    except OSError as exc:
        console_log(
            f"Unable to write final tournament CSV '{output_path}': {exc}",
            minimum_level=VerbosityLevel.TERSE,
        )


def run_evolution_loop(
    active_config: EvolverConfig,
    storage: ArenaStorage,
    *,
    verbosity: VerbosityLevel,
) -> None:
    start_time = time.time()
    era = -1
    data_logger = DataLogger(filename=active_config.battle_log_file)
    benchmark_logger = BenchmarkLogger(filename=active_config.benchmark_log_file)
    bag: list[BaseMutationStrategy] = []
    interrupted = False
    era_count = len(active_config.battlerounds_list)
    era_duration = active_config.clock_time / era_count
    battles_per_era = [0 for _ in range(era_count)]
    archived_per_era = [0 for _ in range(era_count)]
    unarchived_per_era = [0 for _ in range(era_count)]
    total_battles = 0
    generation_counter = 0
    champions: dict[int, int] = {
        arena_index: 1 for arena_index in range(active_config.last_arena + 1)
    }

    def _sync_champion_display() -> None:
        champion_payload: dict[int, ChampionDisplay] = {}
        for arena_index, warrior_id in champions.items():
            lines = storage.get_warrior_lines(arena_index, warrior_id)
            sanitized = tuple(line.rstrip("\r\n") for line in lines)
            champion_payload[arena_index] = ChampionDisplay(
                warrior_id=warrior_id, lines=sanitized
            )
        console_update_champions(champion_payload)

    _sync_champion_display()

    data_logger.open()
    benchmark_logger.open()

    try:
        while True:
            previous_era = era
            runtime_seconds = time.time() - start_time
            runtime_in_hours = runtime_seconds / 3600

            if runtime_in_hours > active_config.clock_time:
                console_clear_status()
                console_log(
                    "Clock time exceeded. Ending evolution loop.",
                    minimum_level=VerbosityLevel.TERSE,
                )
                break

            if active_config.final_era_only:
                era = era_count - 1
            else:
                era = min(int(runtime_in_hours / era_duration), era_count - 1)

            if era != previous_era:
                console_clear_status()
                if previous_era >= 0:
                    _log_era_summary(
                        previous_era,
                        battles_per_era,
                        archived_per_era,
                        unarchived_per_era,
                    )
                if previous_era < 0:
                    console_log(
                        f"========== Starting evolution in era {era + 1} of {era_count} ==========",
                        minimum_level=VerbosityLevel.DEFAULT,
                    )
                else:
                    console_log(
                        f"************** Advancing from era {previous_era + 1} to {era + 1} *******************",
                        minimum_level=VerbosityLevel.DEFAULT,
                    )
                    storage.flush_all()
                bag = _build_marble_bag(era, active_config)

            arena_index = _select_arena_index(active_config)
            champion_id = champions.get(arena_index)
            random_pair_weight = active_config.random_pair_battle_frequency_list[era]
            champion_weight = active_config.champion_battle_frequency_list[era]
            benchmark_weight = active_config.benchmark_battle_frequency_list[era]
            benchmark_available = bool(active_config.benchmark_sets.get(arena_index))
            effective_benchmark_weight = benchmark_weight if benchmark_available else 0
            try:
                battle_type = choose_battle_type(
                    random_pair_weight,
                    champion_weight,
                    effective_benchmark_weight,
                )
            except ValueError:
                battle_type = BattleType.RANDOM_PAIR

            use_benchmark_battle = battle_type == BattleType.BENCHMARK and benchmark_available
            if battle_type == BattleType.BENCHMARK and not use_benchmark_battle:
                battle_type = BattleType.RANDOM_PAIR
            cont1, cont2 = select_opponents(
                active_config.numwarriors,
                champion_id,
                battle_type=battle_type,
            )
            display_era = era + 1
            benchmark_result: Optional[BenchmarkBattleResult] = None
            if use_benchmark_battle:
                battle_label = "Benchmark battle"
            elif battle_type == BattleType.CHAMPION:
                battle_label = "Champion battle"
            else:
                battle_label = "Battle"
            progress_line, _ = _get_progress_status(
                start_time, active_config.clock_time, era
            )
            pending_battle_line = (
                f"{battle_label}: "
                f"Era {display_era}, Arena {arena_index} | {cont1} vs {cont2} | Running..."
            )
            console_update_status(progress_line, pending_battle_line)

            if use_benchmark_battle:
                benchmark_result = _run_benchmark_battle(
                    arena_index, cont1, cont2, era, active_config
                )
                if benchmark_result is None:
                    use_benchmark_battle = False
                    battle_label = "Battle"
                    progress_line, _ = _get_progress_status(
                        start_time, active_config.clock_time, era
                    )
                    pending_battle_line = (
                        f"{battle_label}: "
                        f"Era {display_era}, Arena {arena_index} | {cont1} vs {cont2} | Running..."
                    )
                    console_update_status(progress_line, pending_battle_line)

            if use_benchmark_battle and benchmark_result is not None:
                warriors = benchmark_result.warriors
                scores = benchmark_result.scores
            else:
                battle_seed = _generate_internal_battle_seed()
                warriors, scores = execute_battle(
                    arena_index,
                    cont1,
                    cont2,
                    era,
                    verbose=verbosity == VerbosityLevel.VERBOSE,
                    seed=battle_seed,
                )
                benchmark_result = None
            if 0 <= era < len(battles_per_era):
                battles_per_era[era] += 1
            total_battles += 1
            if (
                active_config.arena_checkpoint_interval
                and total_battles % active_config.arena_checkpoint_interval == 0
            ):
                storage.flush_all()
            winner, loser, was_draw = determine_winner_and_loser(warriors, scores)
            champion_id = champions.get(arena_index)
            if (
                champion_id in warriors
                and not was_draw
                and winner != champion_id
            ):
                champions[arena_index] = winner
                _sync_champion_display()
            get_console().record_battle(winner, loser, was_draw)

            if len(warriors) >= 2 and len(scores) >= 2:
                matchup = (
                    f"{warriors[0]} ({scores[0]}) vs {warriors[1]} ({scores[1]})"
                )
            else:
                matchup = " vs ".join(str(warrior) for warrior in warriors)
            if use_benchmark_battle and benchmark_result is not None:
                battle_result_description = None
            else:
                if was_draw:
                    battle_result_description = (
                        f"Result: Draw | Winner (selected): {winner} | Loser: {loser}"
                    )
                else:
                    battle_result_description = f"Winner: {winner} | Loser: {loser}"

            archiving_result = handle_archiving(
                winner, loser, arena_index, era, active_config
            )
            if archiving_result.events and 0 <= era < len(archived_per_era):
                for event in archiving_result.events:
                    if event.action == "archived":
                        archived_per_era[era] += 1
                    else:
                        unarchived_per_era[era] += 1

            if archiving_result.skip_breeding:
                continue

            partner_id = breed_offspring(
                winner,
                loser,
                arena_index,
                era,
                active_config,
                bag,
                data_logger,
                scores,
                warriors,
            )

            generation_counter += 1
            log_interval = active_config.benchmark_log_generation_interval
            if (
                log_interval > 0
                and generation_counter % log_interval == 0
                and benchmark_logger.enabled
            ):
                _log_benchmark_scores_for_champions(
                    era=era,
                    generation=generation_counter,
                    champions=champions,
                    active_config=active_config,
                    benchmark_logger=benchmark_logger,
                )

            battle_segments = [
                f"{battle_label}: Era {display_era}, Arena {arena_index}",
                matchup,
            ]
            if battle_result_description:
                battle_segments.append(battle_result_description)
            battle_segments.append(f"Partner: {partner_id}")
            battle_line = " | ".join(battle_segments)
            progress_line, default_detail = _get_progress_status(
                start_time, active_config.clock_time, era
            )
            console_update_status(progress_line, battle_line or default_detail)

        if 0 <= era < len(battles_per_era):
            _log_era_summary(
                era, battles_per_era, archived_per_era, unarchived_per_era
            )

    except KeyboardInterrupt:
        console_clear_status()
        console_log(
            "Evolution interrupted by user.",
            minimum_level=VerbosityLevel.TERSE,
        )
        interrupted = True

    finally:
        data_logger.close()
        benchmark_logger.close()

    end_time = time.time()

    if not interrupted:
        console_clear_status()
        console_log(
            "Evolution loop completed.",
            minimum_level=VerbosityLevel.TERSE,
        )

    _print_evolution_statistics(
        battles_per_era=battles_per_era,
        total_battles=total_battles,
        runtime_seconds=end_time - start_time,
    )

    if active_config.run_final_tournament:
        run_final_tournament(active_config)


def _main_impl(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Python Evolver Stage")
    parser.add_argument(
        "--config",
        default="settings.ini",
        help="Path to configuration INI file (default: settings.ini)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Seed the RNG for reproducible runs",
    )
    parser.add_argument(
        "--verbosity",
        choices=[level.value for level in VerbosityLevel],
        default=VerbosityLevel.DEFAULT.value,
        help="Console verbosity: terse, default, verbose, or pseudo-graphical",
    )
    args = parser.parse_args(argv)

    verbosity = VerbosityLevel(args.verbosity)

    verbosity = set_console_verbosity(verbosity)

    active_config = load_configuration(args.config)

    set_active_config(active_config)

    archive_storage = DiskArchiveStorage(archive_path=active_config.archive_path)
    set_archive_storage(archive_storage)
    archive_storage.initialize()

    _print_run_configuration_summary(active_config)

    seed_enabled = args.seed is not None
    if seed_enabled:
        random.seed(args.seed)

    storage = create_arena_storage(active_config)
    set_arena_storage(storage)
    storage.load_existing()

    if active_config.final_tournament_only:
        console_log(
            "Final tournament only mode enabled. Skipping evolution loop.",
            minimum_level=VerbosityLevel.TERSE,
        )
        run_final_tournament(active_config)
        return 0

    if not active_config.alreadyseeded:
        console_log("Seeding", minimum_level=VerbosityLevel.TERSE)
        for arena in range(0, active_config.last_arena + 1):
            arena_dir = os.path.join(active_config.base_path, f"arena{arena}")
            os.makedirs(arena_dir, exist_ok=True)
            for warrior_id in range(1, active_config.numwarriors + 1):
                new_lines = [
                    instruction_to_line(generate_random_instruction(arena), arena)
                    for _ in range(1, active_config.warlen_list[arena] + 1)
                ]
                storage.set_warrior_lines(arena, warrior_id, new_lines)
        storage.flush_all()

    run_evolution_loop(active_config, storage, verbosity=verbosity)

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    try:
        return _main_impl(argv)
    finally:
        try:
            active_config = get_active_config()
        except RuntimeError:
            active_config = None
        try:
            storage = get_arena_storage()
        except RuntimeError:
            storage = None
        if storage is not None:
            try:
                should_flush = True
                if should_flush:
                    wrote_any = storage.flush_all()
            except RuntimeError:
                pass
        close_console()


if __name__ == "__main__" and os.getenv("PYTHONEVOLVER_SKIP_MAIN") != "1":
    sys.exit(main())
