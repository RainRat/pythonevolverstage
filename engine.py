"""Core battle and evolutionary logic for the Core War evolver stage."""

from __future__ import annotations

import os
import random
import sys
from abc import ABC, abstractmethod
from collections import defaultdict
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Callable,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    cast,
)
import battle_runner as _battle_runner
import storage as _storage

import redcode
from battle_runner import (
    CPP_WORKER_LIB,
    CPP_WORKER_MAX_CORE_SIZE,
    CPP_WORKER_MAX_CYCLES,
    CPP_WORKER_MAX_PROCESSES,
    CPP_WORKER_MAX_ROUNDS,
    CPP_WORKER_MAX_WARRIOR_LENGTH,
    CPP_WORKER_MIN_CORE_SIZE,
    CPP_WORKER_MIN_DISTANCE,
    _candidate_nmars_paths,
    _candidate_pmars_paths,
    _generate_internal_battle_seed,
    _get_evolverstage_override,
    _normalize_internal_seed,
    _resolve_external_command,
    _run_external_command,
    _run_external_battle,
    _stable_internal_battle_seed,
    configure_battle_rng,
    execute_battle,
    execute_battle_with_sources,
    run_internal_battle,
    set_sync_export as _set_battle_sync_export,
)
from config import (
    MAX_WARRIOR_FILENAME_ID,
    get_active_config,
    get_arena_spec,
)
from redcode import (
    ADDRESSING_MODES,
    BASE_ADDRESSING_MODES,
    CANONICAL_SUPPORTED_OPCODES,
    DEFAULT_1988_GENERATION_POOL,
    DEFAULT_1988_MODIFIERS,
    DEFAULT_1988_MODES,
    DEFAULT_MODE,
    DEFAULT_MODIFIER,
    GENERATION_OPCODE_POOL,
    GENERATION_OPCODE_POOL_1988,
    OPCODE_ALIASES,
    RedcodeInstruction,
    SPEC_1988,
    SPEC_1994,
    SPEC_ALLOWED_ADDRESSING_MODES,
    SPEC_ALLOWED_MODIFIERS,
    SPEC_ALLOWED_OPCODES,
    SUPPORTED_OPCODES,
    UNSUPPORTED_OPCODES,
    choose_random_modifier,
    choose_random_mode,
    choose_random_opcode,
    corenorm,
    coremod,
    default_instruction,
    format_redcode_instruction,
    generate_random_instruction,
    generate_warrior_lines_until_non_dat,
    instruction_to_line,
    parse_instruction_or_default,
    parse_redcode_instruction,
    _ensure_int,
    _parse_operand,
    rebuild_instruction_tables,
    sanitize_instruction,
    weighted_random_number,
)
from storage import (
    ArchivingEvent,
    ArchivingResult,
    ArchiveStorage,
    ArenaStorage,
    DiskArchiveStorage,
    DiskArenaStorage,
    InMemoryArenaStorage,
    create_arena_storage,
    configure_storage_rng,
    get_archive_storage,
    get_arena_storage,
    handle_archiving,
    set_archive_storage,
    set_arena_storage,
)
from ui import VerbosityLevel, console_log

if TYPE_CHECKING:  # pragma: no cover - imported only for type checking
    from config import EvolverConfig
    from evolverstage import DataLogger


T = TypeVar("T")


_active_config: Optional["EvolverConfig"] = None
_LIBRARY_CACHE: list[str] | None = None
_LIBRARY_CACHE_PATH: Optional[str] = None


def _load_instruction_library_cache(library_path: Optional[str]) -> None:
    """Load the instruction library into a module-level cache."""

    global _LIBRARY_CACHE
    global _LIBRARY_CACHE_PATH
    _LIBRARY_CACHE_PATH = library_path

    if not library_path or not os.path.exists(library_path):
        _LIBRARY_CACHE = []
        return

    try:
        with open(library_path, "r") as library_handle:
            _LIBRARY_CACHE = library_handle.readlines()
    except OSError:
        _LIBRARY_CACHE = []


def get_instruction_library_cache() -> list[str] | None:
    return _LIBRARY_CACHE


def ensure_instruction_library_cache(library_path: Optional[str]) -> list[str]:
    """Return the cached instruction library, loading it once if needed."""

    global _LIBRARY_CACHE, _LIBRARY_CACHE_PATH
    if _LIBRARY_CACHE is None or _LIBRARY_CACHE_PATH != library_path:
        _load_instruction_library_cache(library_path)
    return _LIBRARY_CACHE or []


def set_engine_config(config: "EvolverConfig") -> None:
    """Register the active configuration for helpers that require it."""

    global _active_config
    _active_config = config
    rebuild_instruction_tables(config)
    _load_instruction_library_cache(config.library_path)




def _require_config() -> "EvolverConfig":
    config = _active_config or get_active_config()
    if config is None:
        raise RuntimeError(
            "Engine configuration has not been set. Call set_active_config() first."
        )
    return config


def weighted_choice(
    items: Sequence[Tuple[T, int]], rng: Optional[Callable[[int, int], int]] = None
) -> T:
    """Select an item from a list of (item, weight) tuples."""
    total_weight = sum(weight for _, weight in items)
    if total_weight <= 0:
        raise ValueError("Total weight must be positive")

    effective_rng = rng or _rng_int
    roll = effective_rng(1, total_weight)
    cumulative = 0
    for item, weight in items:
        cumulative += weight
        if roll <= cumulative:
            return item

    return items[-1][0]


_rng_int: Callable[[int, int], int] = random.randint
_rng_choice: Callable[[Sequence[T]], T] = random.choice  # type: ignore[assignment]

redcode.set_rng_helpers(_rng_int, _rng_choice)


def configure_rng(
    random_int_func: Callable[[int, int], int],
    random_choice_func: Callable[[Sequence[T]], T],
) -> None:
    """Wire in evolverstage's deterministic RNG helpers."""

    global _rng_int, _rng_choice
    _rng_int = random_int_func
    _rng_choice = random_choice_func
    redcode.set_rng_helpers(_rng_int, _rng_choice)
    configure_battle_rng(random_int_func)
    configure_storage_rng(random_int_func, random_choice_func)


def _sync_export(name: str, value) -> None:
    globals()[name] = value
    module = sys.modules.get("evolverstage")
    if module is not None:
        setattr(module, name, value)


redcode.set_override_helper(_get_evolverstage_override)
redcode.set_sync_export(_sync_export)


class BattleType(Enum):
    RANDOM_PAIR = "random_pair"
    CHAMPION = "champion"
    BENCHMARK = "benchmark"

_set_battle_sync_export(_sync_export)

class BaseMutationStrategy(ABC):
    """Common interface for all mutation strategies."""

    @abstractmethod
    def apply(
        self,
        instruction: RedcodeInstruction,
        arena: int,
        config: "EvolverConfig",
        magic_number: int,
    ) -> RedcodeInstruction:
        """Apply the mutation to the provided instruction."""
        raise NotImplementedError


class DoNothingMutation(BaseMutationStrategy):
    def apply(
        self,
        instruction: RedcodeInstruction,
        _arena: int,
        _config: "EvolverConfig",
        _magic_number: int,
    ) -> RedcodeInstruction:
        return instruction


class MajorMutation(BaseMutationStrategy):
    def apply(
        self,
        instruction: RedcodeInstruction,
        arena: int,
        config: "EvolverConfig",
        magic_number: int,
    ) -> RedcodeInstruction:
        return generate_random_instruction(arena)


class NabInstruction(BaseMutationStrategy):
    def apply(
        self,
        instruction: RedcodeInstruction,
        arena: int,
        config: "EvolverConfig",
        magic_number: int,
    ) -> RedcodeInstruction:
        if config.last_arena == 0:
            return instruction

        donor_arena = _rng_int(0, config.last_arena)
        while donor_arena == arena and config.last_arena > 0:
            donor_arena = _rng_int(0, config.last_arena)

        console_log(
            "Nab instruction from arena " + str(donor_arena),
            minimum_level=VerbosityLevel.VERBOSE,
        )
        storage = get_arena_storage()
        donor_warrior = _rng_int(1, config.numwarriors)
        donor_lines = storage.get_warrior_lines(donor_arena, donor_warrior)

        if donor_lines:
            return parse_instruction_or_default(_rng_choice(donor_lines))

        console_log(
            "Donor warrior empty; skipping mutation.",
            minimum_level=VerbosityLevel.VERBOSE,
        )
        return instruction


class MinorMutation(BaseMutationStrategy):
    def apply(
        self,
        instruction: RedcodeInstruction,
        arena: int,
        config: "EvolverConfig",
        magic_number: int,
    ) -> RedcodeInstruction:
        r = _rng_int(1, 6)
        if r == 1:
            instruction.opcode = choose_random_opcode(arena)
        elif r == 2:
            instruction.modifier = choose_random_modifier(arena)
        elif r == 3:
            instruction.a_mode = choose_random_mode(arena)
        elif r == 4:
            instruction.a_field = weighted_random_number(
                config.coresize_list[arena], config.warlen_list[arena]
            )
        elif r == 5:
            instruction.b_mode = choose_random_mode(arena)
        elif r == 6:
            instruction.b_field = weighted_random_number(
                config.coresize_list[arena], config.warlen_list[arena]
            )
        return instruction


class MicroMutation(BaseMutationStrategy):
    def apply(
        self,
        instruction: RedcodeInstruction,
        arena: int,
        config: "EvolverConfig",
        magic_number: int,
    ) -> RedcodeInstruction:
        target_field = "a_field" if _rng_int(1, 2) == 1 else "b_field"
        current_value = _ensure_int(getattr(instruction, target_field))
        if _rng_int(1, 2) == 1:
            current_value += 1
        else:
            current_value -= 1
        setattr(instruction, target_field, current_value)
        return instruction


class InstructionLibraryMutation(BaseMutationStrategy):
    def apply(
        self,
        instruction: RedcodeInstruction,
        arena: int,
        config: "EvolverConfig",
        magic_number: int,
    ) -> RedcodeInstruction:
        if not config.library_path:
            return instruction

        library_cache = ensure_instruction_library_cache(config.library_path)

        if library_cache:
            return parse_instruction_or_default(_rng_choice(library_cache))
        return default_instruction()


class MagicNumberMutation(BaseMutationStrategy):
    def apply(
        self,
        instruction: RedcodeInstruction,
        arena: int,
        config: "EvolverConfig",
        magic_number: int,
    ) -> RedcodeInstruction:
        if _rng_int(1, 2) == 1:
            instruction.a_field = magic_number
        else:
            instruction.b_field = magic_number
        return instruction


def breed_offspring(
    winner: int,
    loser: int,
    arena: int,
    era: int,
    config: "EvolverConfig",
    bag: list[BaseMutationStrategy],
    data_logger: "DataLogger",
    scores: list[int],
    warriors: list[int],
) -> int:
    storage = get_arena_storage()
    winlines = storage.get_warrior_lines(arena, winner)

    partner_id = _rng_int(1, config.numwarriors)
    ranlines = storage.get_warrior_lines(arena, partner_id)

    if _rng_int(1, config.transpositionrate_list[era]) == 1:
        transpositions = _rng_int(1, int((config.warlen_list[arena] + 1) / 2))
        for _ in range(1, transpositions):
            fromline = _rng_int(0, config.warlen_list[arena] - 1)
            toline = _rng_int(0, config.warlen_list[arena] - 1)
            if _rng_int(1, 2) == 1:
                if fromline < len(winlines) and toline < len(winlines):
                    winlines[toline], winlines[fromline] = (
                        winlines[fromline],
                        winlines[toline],
                    )
            else:
                if fromline < len(ranlines) and toline < len(ranlines):
                    ranlines[toline], ranlines[fromline] = (
                        ranlines[fromline],
                        ranlines[toline],
                    )

    def _breed_offspring_once() -> list[str]:
        if config.prefer_winner_list[era] is True:
            pickingfrom = 1
        else:
            pickingfrom = _rng_int(1, 2)

        magic_number = weighted_random_number(
            config.coresize_list[arena], config.warlen_list[arena]
        )
        offspring_lines: list[str] = []
        for i in range(0, config.warlen_list[arena]):
            if _rng_int(1, config.crossoverrate_list[era]) == 1:
                pickingfrom = 2 if pickingfrom == 1 else 1

            if pickingfrom == 1:
                source_line = winlines[i] if i < len(winlines) else ""
            else:
                source_line = ranlines[i] if i < len(ranlines) else ""

            instruction = parse_instruction_or_default(source_line)
            chosen_strategy = _rng_choice(bag)
            instruction = chosen_strategy.apply(
                instruction, arena, config, magic_number
            )

            offspring_lines.append(instruction_to_line(instruction, arena))
            magic_number -= 1

        return offspring_lines

    new_lines = generate_warrior_lines_until_non_dat(
        _breed_offspring_once,
        context=f"Breeding offspring for arena {arena}, warrior {loser}",
        arena=arena,
    )

    storage.set_warrior_lines(arena, loser, new_lines)

    data_logger.log_data(
        era=era,
        arena=arena,
        winner=winner,
        loser=loser,
        score1=scores[0],
        score2=scores[1],
        bred_with=str(partner_id),
    )
    return partner_id


def determine_winner_and_loser(
    warriors: list[int], scores: list[int]
) -> tuple[int, int, bool]:
    if len(warriors) < 2 or len(scores) < 2:
        raise ValueError("Expected scores for two warriors")

    if scores[1] == scores[0]:
        draw_rng = _get_evolverstage_override("get_random_int", _rng_int)
        draw_selection = draw_rng(1, 2)
        if draw_selection == 1:
            winner = warriors[1]
            loser = warriors[0]
        else:
            winner = warriors[0]
            loser = warriors[1]
        return winner, loser, True
    if scores[1] > scores[0]:
        return warriors[1], warriors[0], False
    return warriors[0], warriors[1], False


def choose_battle_type(
    random_pair_weight: int,
    champion_weight: int,
    benchmark_weight: int,
) -> BattleType:
    weighted_types = [
        (BattleType.RANDOM_PAIR, max(0, random_pair_weight)),
        (BattleType.CHAMPION, max(0, champion_weight)),
        (BattleType.BENCHMARK, max(0, benchmark_weight)),
    ]
    positive = [(battle_type, weight) for battle_type, weight in weighted_types if weight > 0]

    if not positive:
        raise ValueError("At least one battle weight must be positive.")

    return weighted_choice(positive, rng=_rng_int)


def select_opponents(
    num_warriors: int,
    champion: Optional[int] = None,
    battle_type: BattleType = BattleType.RANDOM_PAIR,
) -> tuple[int, int]:
    if battle_type == BattleType.CHAMPION and champion is not None:
        challenger = champion
        while challenger == champion:
            challenger = _rng_int(1, num_warriors)
        return champion, challenger

    cont1 = _rng_int(1, num_warriors)
    cont2 = cont1
    while cont2 == cont1:
        cont2 = _rng_int(1, num_warriors)
    return cont1, cont2


_DYNAMIC_FORWARD_ATTRS = {
    "CPP_WORKER_LIB",
    "_ARENA_STORAGE",
    "_ARCHIVE_STORAGE",
}


def __getattr__(name: str):
    if name == "CPP_WORKER_LIB":
        return _battle_runner.CPP_WORKER_LIB
    if name == "_ARENA_STORAGE":
        return _storage._ARENA_STORAGE
    if name == "_ARCHIVE_STORAGE":
        return _storage._ARCHIVE_STORAGE
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "set_engine_config",
    "configure_rng",
    "get_instruction_library_cache",
    "ensure_instruction_library_cache",
    "rebuild_instruction_tables",
    "SPEC_1994",
    "SPEC_1988",
    "DEFAULT_MODE",
    "DEFAULT_MODIFIER",
    "BASE_ADDRESSING_MODES",
    "ADDRESSING_MODES",
    "CANONICAL_SUPPORTED_OPCODES",
    "SUPPORTED_OPCODES",
    "UNSUPPORTED_OPCODES",
    "GENERATION_OPCODE_POOL",
    "GENERATION_OPCODE_POOL_1988",
    "get_arena_spec",
    "weighted_random_number",
    "coremod",
    "corenorm",
    "MAX_WARRIOR_FILENAME_ID",
    "RedcodeInstruction",
    "parse_redcode_instruction",
    "default_instruction",
    "sanitize_instruction",
    "format_redcode_instruction",
    "instruction_to_line",
    "parse_instruction_or_default",
    "choose_random_opcode",
    "choose_random_modifier",
    "choose_random_mode",
    "generate_random_instruction",
    "generate_warrior_lines_until_non_dat",
    "CPP_WORKER_LIB",
    "CPP_WORKER_MIN_DISTANCE",
    "CPP_WORKER_MIN_CORE_SIZE",
    "CPP_WORKER_MAX_CORE_SIZE",
    "CPP_WORKER_MAX_CYCLES",
    "CPP_WORKER_MAX_PROCESSES",
    "CPP_WORKER_MAX_WARRIOR_LENGTH",
    "CPP_WORKER_MAX_ROUNDS",
    "_normalize_internal_seed",
    "_generate_internal_battle_seed",
    "_stable_internal_battle_seed",
    "_candidate_pmars_paths",
    "_candidate_nmars_paths",
    "_resolve_external_command",
    "_run_external_command",
    "_run_external_battle",
    "run_internal_battle",
    "execute_battle",
    "execute_battle_with_sources",
    "ArenaStorage",
    "DiskArenaStorage",
    "InMemoryArenaStorage",
    "set_arena_storage",
    "get_arena_storage",
    "create_arena_storage",
    "ArchiveStorage",
    "DiskArchiveStorage",
    "set_archive_storage",
    "get_archive_storage",
    "BaseMutationStrategy",
    "DoNothingMutation",
    "MajorMutation",
    "NabInstruction",
    "MinorMutation",
    "MicroMutation",
    "InstructionLibraryMutation",
    "MagicNumberMutation",
    "BattleType",
    "choose_battle_type",
    "ArchivingEvent",
    "ArchivingResult",
    "handle_archiving",
    "breed_offspring",
    "determine_winner_and_loser",
    "select_opponents",
    "weighted_choice",
]

