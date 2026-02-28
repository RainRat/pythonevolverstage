from __future__ import annotations

import os
import random
import uuid
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional, Sequence, Tuple, TypeVar, Union

from config import EvolverConfig, MAX_WARRIOR_FILENAME_ID, get_active_config
from redcode import default_instruction, instruction_to_line, parse_redcode_instruction

T = TypeVar("T")

_rng_int: Callable[[int, int], int] = random.randint
_rng_choice: Callable[[Sequence[T]], T] = random.choice  # type: ignore[assignment]


def configure_storage_rng(
    random_int_func: Callable[[int, int], int],
    random_choice_func: Callable[[Sequence[T]], T],
) -> None:
    global _rng_int, _rng_choice
    _rng_int = random_int_func
    _rng_choice = random_choice_func


class _ArenaStorageNotLoaded:
    pass


class ArenaStorage:
    """Abstract storage backend for warrior source code."""

    def load_existing(self) -> None:
        raise NotImplementedError

    def get_warrior_lines(self, arena: int, warrior_id: int) -> list[str]:
        raise NotImplementedError

    def set_warrior_lines(
        self, arena: int, warrior_id: int, lines: Sequence[str]
    ) -> None:
        raise NotImplementedError

    def ensure_warriors_on_disk(
        self, arena: int, warrior_ids: Sequence[int]
    ) -> None:
        """Ensure the specified warriors are available on disk for battle engines."""

    def flush_arena(self, arena: int) -> bool:
        """Persist all warriors for a specific arena to disk."""

    def flush_all(self) -> bool:
        """Persist all arenas to disk."""


class DiskArenaStorage(ArenaStorage):
    """Storage backend that writes warrior changes directly to disk."""

    def __init__(self, config: EvolverConfig | None = None) -> None:
        self._config = config

    def load_existing(self) -> None:
        return None

    def get_warrior_lines(self, arena: int, warrior_id: int) -> list[str]:
        config = self._config if self._config is not None else get_active_config()
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
        try:
            with open(warrior_path, "r") as handle:
                return handle.readlines()
        except OSError:
            return []

    def set_warrior_lines(
        self, arena: int, warrior_id: int, lines: Sequence[str]
    ) -> None:
        config = self._config if self._config is not None else get_active_config()
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        os.makedirs(arena_dir, exist_ok=True)
        warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
        with open(warrior_path, "w") as handle:
            handle.writelines(lines)

    def ensure_warriors_on_disk(
        self, arena: int, warrior_ids: Sequence[int]
    ) -> None:
        return None

    def flush_arena(self, arena: int) -> bool:
        return False

    def flush_all(self) -> bool:
        return False


class InMemoryArenaStorage(ArenaStorage):
    """Store arena warriors in memory and persist on demand."""

    def __init__(self, config: EvolverConfig | None = None) -> None:
        self._config = config
        self._arenas: dict[int, dict[int, list[str]]] = defaultdict(dict)
        self._dirty: set[tuple[int, int]] = set()

    def _write_warrior(self, arena: int, warrior_id: int) -> None:
        config = self._config if self._config is not None else get_active_config()
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
        os.makedirs(arena_dir, exist_ok=True)
        with open(warrior_path, "w") as handle:
            handle.writelines(self._arenas[arena][warrior_id])

    def load_existing(self) -> None:
        config = self._config if self._config is not None else get_active_config()
        for arena in range(0, config.last_arena + 1):
            arena_dir = os.path.join(config.base_path, f"arena{arena}")
            if not os.path.isdir(arena_dir):
                continue
            for warrior_id in range(1, config.numwarriors + 1):
                warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
                try:
                    with open(warrior_path, "r") as handle:
                        self._arenas[arena][warrior_id] = handle.readlines()
                except OSError:
                    self._arenas[arena][warrior_id] = []
        self._dirty.clear()

    def get_warrior_lines(self, arena: int, warrior_id: int) -> list[str]:
        config = self._config if self._config is not None else get_active_config()
        if arena in self._arenas and warrior_id in self._arenas[arena]:
            return list(self._arenas[arena][warrior_id])
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        warrior_path = os.path.join(arena_dir, f"{warrior_id}.red")
        try:
            with open(warrior_path, "r") as handle:
                return handle.readlines()
        except OSError:
            return []

    def set_warrior_lines(
        self, arena: int, warrior_id: int, lines: Sequence[str]
    ) -> None:
        self._arenas[arena][warrior_id] = list(lines)
        self._dirty.add((arena, warrior_id))

    def ensure_warriors_on_disk(
        self, arena: int, warrior_ids: Sequence[int]
    ) -> None:
        config = self._config if self._config is not None else get_active_config()
        arena_dir = os.path.join(config.base_path, f"arena{arena}")
        if not self._dirty or not os.path.isdir(arena_dir):
            return None
        warrior_ids_set = set(warrior_ids)
        for (dirty_arena, warrior_id) in list(self._dirty):
            if dirty_arena != arena or warrior_id not in warrior_ids_set:
                continue
            self._write_warrior(dirty_arena, warrior_id)
            self._dirty.discard((dirty_arena, warrior_id))

    def flush_arena(self, arena: int) -> bool:
        any_flushed = False
        for (dirty_arena, warrior_id) in list(self._dirty):
            if dirty_arena != arena:
                continue
            self._write_warrior(dirty_arena, warrior_id)
            self._dirty.discard((dirty_arena, warrior_id))
            any_flushed = True
        return any_flushed

    def flush_all(self) -> bool:
        any_flushed = False
        for (dirty_arena, warrior_id) in list(self._dirty):
            self._write_warrior(dirty_arena, warrior_id)
            self._dirty.discard((dirty_arena, warrior_id))
            any_flushed = True
        return any_flushed


_ARENA_STORAGE: Union[ArenaStorage, _ArenaStorageNotLoaded] = _ArenaStorageNotLoaded()


def set_arena_storage(storage: ArenaStorage) -> None:
    global _ARENA_STORAGE
    _ARENA_STORAGE = storage


def get_arena_storage() -> ArenaStorage:
    storage = _ARENA_STORAGE
    if isinstance(storage, _ArenaStorageNotLoaded):
        raise RuntimeError(
            "Arena storage has not been initialized. Call set_arena_storage() before use."
        )
    return storage


def create_arena_storage(config: EvolverConfig) -> ArenaStorage:
    if config.use_in_memory_arenas:
        return InMemoryArenaStorage(config)
    return DiskArenaStorage(config)


class ArchiveStorage:
    """Abstract storage backend for warrior archives."""

    def initialize(self) -> None:
        """Prepare the archive backend for use."""
        raise NotImplementedError

    def archive_warrior(
        self,
        warrior_id: int,
        lines: Sequence[str],
        config: EvolverConfig,
        get_random_int: Callable[[int, int], int],
    ) -> Optional[str]:
        """Persist a warrior in the archive and return its filename if successful."""
        raise NotImplementedError

    def unarchive_warrior(
        self,
        config: EvolverConfig,
        get_random_choice: Callable[[Sequence[T]], T],
    ) -> Optional[Tuple[str, list[str]]]:
        """Retrieve a random warrior from the archive, returning its filename and lines."""
        raise NotImplementedError

    def count(self) -> int:
        """Return the number of warriors currently stored in the archive."""
        raise NotImplementedError


class DiskArchiveStorage(ArchiveStorage):
    """Archive storage implementation that reads and writes warriors on disk."""

    def __init__(self, archive_path: str, config: EvolverConfig | None = None) -> None:
        self._archive_path = os.path.abspath(archive_path)
        self._config = config

    @property
    def archive_path(self) -> str:
        return self._archive_path

    def initialize(self) -> None:
        os.makedirs(self._archive_path, exist_ok=True)

    def archive_warrior(
        self,
        warrior_id: int,
        lines: Sequence[str],
        config: EvolverConfig,
        get_random_int: Callable[[int, int], int],
    ) -> Optional[str]:
        archive_dir = self._archive_path
        configured_archive_path = os.path.abspath(config.archive_path)
        if configured_archive_path == archive_dir:
            archive_dir = configured_archive_path

        archive_filename: Optional[str] = None
        os.makedirs(archive_dir, exist_ok=True)
        for _ in range(10):
            candidate = f"{get_random_int(1, MAX_WARRIOR_FILENAME_ID)}.red"
            candidate_path = os.path.join(archive_dir, candidate)
            try:
                fd = os.open(
                    candidate_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o644,
                )
            except FileExistsError:
                continue
            else:
                with os.fdopen(fd, "w") as handle:
                    handle.writelines(lines)
                archive_filename = candidate
                break

        if archive_filename is None:
            archive_filename = f"{uuid.uuid4().hex}.red"
            fallback_path = os.path.join(archive_dir, archive_filename)
            with open(fallback_path, "w") as handle:
                handle.writelines(lines)

        return archive_filename

    def unarchive_warrior(
        self,
        _config: EvolverConfig,
        get_random_choice: Callable[[Sequence[T]], T],
    ) -> Optional[Tuple[str, list[str]]]:
        if not os.path.isdir(self._archive_path):
            return None
        archive_files = os.listdir(self._archive_path)
        if not archive_files:
            return None
        archive_choice = get_random_choice(archive_files)
        archive_path = os.path.join(self._archive_path, archive_choice)
        try:
            with open(archive_path, "r") as handle:
                sourcelines = handle.readlines()
        except OSError:
            return None
        return archive_choice, sourcelines

    def count(self) -> int:
        archive_dir = self._archive_path
        try:
            entries = os.listdir(archive_dir)
        except FileNotFoundError:
            return 0
        except OSError as exc:
            warnings.warn(
                f"Unable to inspect archive directory '{archive_dir}': {exc}",
                RuntimeWarning,
            )
            return 0

        total = 0
        for entry in entries:
            if not entry.lower().endswith(".red"):
                continue
            full_path = os.path.join(archive_dir, entry)
            if os.path.isfile(full_path):
                total += 1
        return total


_ARCHIVE_STORAGE: Union[ArchiveStorage, _ArenaStorageNotLoaded] = _ArenaStorageNotLoaded()


def set_archive_storage(storage: ArchiveStorage) -> None:
    global _ARCHIVE_STORAGE
    _ARCHIVE_STORAGE = storage


def get_archive_storage() -> ArchiveStorage:
    storage = _ARCHIVE_STORAGE
    if isinstance(storage, _ArenaStorageNotLoaded):
        raise RuntimeError(
            "Archive storage has not been initialized. Call set_archive_storage() before use."
        )
    return storage


@dataclass
class ArchivingEvent:
    action: Literal["archived", "unarchived"]
    warrior_id: int
    archive_filename: Optional[str] = None


@dataclass
class ArchivingResult:
    skip_breeding: bool = False
    events: list[ArchivingEvent] = field(default_factory=list)


def handle_archiving(
    winner: int, loser: int, arena: int, era: int, config: EvolverConfig
) -> ArchivingResult:
    events: list[ArchivingEvent] = []
    storage = get_arena_storage()
    archive_storage = get_archive_storage()

    if config.archive_list[era] != 0 and _rng_int(1, config.archive_list[era]) == 1:
        winlines = storage.get_warrior_lines(arena, winner)
        
        # Interpolate modifiers going out to archive (ensures archived warriors are valid 1994)
        from redcode import SPEC_1994, parse_redcode_instruction, format_redcode_instruction
        archived_lines = []
        for line in winlines:
            instr = parse_redcode_instruction(line)
            if instr:
                # format_redcode_instruction with SPEC_1994 (default) adds modifiers
                archived_lines.append(format_redcode_instruction(instr, spec=SPEC_1994))
            else:
                archived_lines.append(line)
        
        archive_filename = archive_storage.archive_warrior(
            warrior_id=winner,
            lines=archived_lines,
            config=config,
            get_random_int=_rng_int,
        )
        events.append(
            ArchivingEvent(
                action="archived",
                warrior_id=winner,
                archive_filename=archive_filename,
            )
        )

    if config.unarchive_list[era] != 0 and _rng_int(1, config.unarchive_list[era]) == 1:
        unarchive_result = archive_storage.unarchive_warrior(config, _rng_choice)
        if not unarchive_result:
            return ArchivingResult(events=events)
        archive_choice, sourcelines = unarchive_result

        instructions_written = 0
        new_lines: list[str] = []
        for line_number, line in enumerate(sourcelines, start=1):
            try:
                instruction = parse_redcode_instruction(line)
            except ValueError as exc:
                raise ValueError(
                    (
                        f"Failed to parse archived warrior '{archive_choice}' "
                        f"(line {line_number}): {exc}"
                    )
                ) from exc
            if instruction is None:
                continue
            new_lines.append(instruction_to_line(instruction, arena))
            instructions_written += 1
            if instructions_written >= config.warlen_list[arena]:
                break
        while instructions_written < config.warlen_list[arena]:
            new_lines.append(instruction_to_line(default_instruction(), arena))
            instructions_written += 1
        storage.set_warrior_lines(arena, loser, new_lines)
        events.append(
            ArchivingEvent(
                action="unarchived",
                warrior_id=loser,
                archive_filename=archive_choice,
            )
        )
        return ArchivingResult(skip_breeding=True, events=events)

    return ArchivingResult(events=events)


__all__ = [
    "ArenaStorage",
    "DiskArenaStorage",
    "InMemoryArenaStorage",
    "create_arena_storage",
    "set_arena_storage",
    "get_arena_storage",
    "ArchiveStorage",
    "DiskArchiveStorage",
    "set_archive_storage",
    "get_archive_storage",
    "ArchivingEvent",
    "ArchivingResult",
    "handle_archiving",
    "configure_storage_rng",
]
