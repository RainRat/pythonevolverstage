"""Console user interface helpers for the Core War evolver stage."""

from __future__ import annotations

import sys
import time
import warnings
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Mapping, Optional, Tuple


class VerbosityLevel(Enum):
    TERSE = "terse"
    DEFAULT = "default"
    VERBOSE = "verbose"
    PSEUDO_GRAPHICAL = "pseudo-graphical"

    def order(self) -> int:
        ordering = {
            VerbosityLevel.TERSE: 0,
            VerbosityLevel.DEFAULT: 1,
            VerbosityLevel.VERBOSE: 2,
            VerbosityLevel.PSEUDO_GRAPHICAL: 1,
        }
        return ordering[self]


_VERBOSITY_LEVEL: VerbosityLevel = VerbosityLevel.DEFAULT

_STATUS_UPDATE_MIN_INTERVAL = 0.1


@dataclass(frozen=True)
class ChampionDisplay:
    """Renderable information about an arena's current champion."""

    warrior_id: Optional[int]
    lines: Tuple[str, ...] = ()

    def formatted_lines(self, max_lines: int) -> list[str]:
        """Return display lines capped at ``max_lines`` entries."""

        header = (
            "No champion"
            if self.warrior_id is None
            else f"Warrior {self.warrior_id}"
        )
        combined = [header, *self.lines]
        if len(combined) <= max_lines:
            return combined
        if max_lines <= 0:
            return []
        visible = combined[: max_lines - 1]
        visible.append("…")
        return visible


class BattleStatisticsTracker:
    """Track simple statistics derived from battle outcomes."""

    def __init__(self) -> None:
        self._current_streaks: dict[int, int] = {}
        self._longest_streak: int = 0
        self._longest_streak_warrior: Optional[int] = None

    def record_battle(self, winner: int, loser: int, was_draw: bool) -> None:
        if was_draw:
            self._current_streaks[winner] = 0
            self._current_streaks[loser] = 0
            return

        current = self._current_streaks.get(winner, 0) + 1
        self._current_streaks[winner] = current
        self._current_streaks[loser] = 0

        if current > self._longest_streak:
            self._longest_streak = current
            self._longest_streak_warrior = winner

    @property
    def longest_streak(self) -> Tuple[Optional[int], int]:
        return self._longest_streak_warrior, self._longest_streak


class ConsoleInterface:
    def __init__(self, level: VerbosityLevel) -> None:
        self.level = level
        self.tracker = BattleStatisticsTracker()

    def should_log(self, minimum_level: VerbosityLevel) -> bool:
        if self.level == VerbosityLevel.PSEUDO_GRAPHICAL:
            return minimum_level in (VerbosityLevel.TERSE, VerbosityLevel.DEFAULT)
        return self.level.order() >= minimum_level.order()

    def log(
        self,
        message: str,
        *,
        minimum_level: VerbosityLevel = VerbosityLevel.DEFAULT,
        flush: bool = False,
    ) -> None:
        raise NotImplementedError

    def update_status(self, progress_line: str, detail_line: str) -> None:
        raise NotImplementedError

    def clear_status(self) -> None:
        raise NotImplementedError

    def record_battle(self, winner: int, loser: int, was_draw: bool) -> None:
        self.tracker.record_battle(winner, loser, was_draw)

    def update_champions(self, champions: Mapping[int, ChampionDisplay]) -> None:
        """Update the rendered champion roster (if supported)."""

        return None

    def close(self) -> None:
        pass


class StatusDisplay:
    """Utility for maintaining a two-line rolling status output."""

    def __init__(self) -> None:
        self._active_lines = 0
        self._last_update_time = 0.0
        self._last_lines: Optional[Tuple[str, str]] = None
        self._pending_lines: Optional[Tuple[str, str]] = None

    def _stream(self):
        return sys.stdout

    def _supports_ansi(self, stream) -> bool:
        return bool(getattr(stream, "isatty", lambda: False)())

    def update(self, line1: str, line2: str) -> None:
        lines_tuple = (line1, line2)
        if self._last_lines == lines_tuple and self._pending_lines is None:
            return

        now = time.monotonic()
        self._pending_lines = lines_tuple
        if self._last_update_time:
            elapsed = now - self._last_update_time
            if elapsed < _STATUS_UPDATE_MIN_INTERVAL:
                return

        self._emit_pending(now)

    def _emit_pending(self, now: Optional[float] = None) -> None:
        if self._pending_lines is None:
            return
        if self._pending_lines == self._last_lines:
            self._pending_lines = None
            return

        if now is None:
            now = time.monotonic()

        self._last_update_time = now

        stream = self._stream()
        supports_ansi = self._supports_ansi(stream)
        line1, line2 = self._pending_lines
        lines = [line1, line2]

        if supports_ansi and self._active_lines:
            stream.write(f"\x1b[{self._active_lines}F")

        for line in lines:
            if supports_ansi:
                stream.write("\x1b[2K")
                stream.write(line)
                stream.write("\n")
            else:
                stream.write(line + "\n")

        stream.flush()
        self._active_lines = len(lines) if supports_ansi else 0
        self._last_lines = self._pending_lines
        self._pending_lines = None

    def clear(self) -> None:
        if not self._active_lines:
            self._last_lines = None
            self._last_update_time = 0.0
            self._pending_lines = None
            return

        stream = self._stream()
        supports_ansi = self._supports_ansi(stream)
        if not supports_ansi:
            self._active_lines = 0
            self._last_lines = None
            self._last_update_time = 0.0
            self._pending_lines = None
            return

        stream.write(f"\x1b[{self._active_lines}F")
        for index in range(self._active_lines):
            stream.write("\x1b[2K")
            if index < self._active_lines - 1:
                stream.write("\x1b[1E")
        stream.write("\r")
        stream.flush()
        self._active_lines = 0
        self._last_lines = None
        self._last_update_time = 0.0
        self._pending_lines = None


class SimpleConsole(ConsoleInterface):
    def __init__(self, level: VerbosityLevel) -> None:
        super().__init__(level)
        self._status_display = StatusDisplay()

    def log(
        self,
        message: str,
        *,
        minimum_level: VerbosityLevel = VerbosityLevel.DEFAULT,
        flush: bool = False,
    ) -> None:
        if not self.should_log(minimum_level):
            return
        print(message, flush=flush)

    def update_status(self, progress_line: str, detail_line: str) -> None:
        if self.level == VerbosityLevel.PSEUDO_GRAPHICAL:
            return
        if self.level == VerbosityLevel.TERSE:
            detail_line = ""
        self._status_display.update(progress_line, detail_line)

    def clear_status(self) -> None:
        if self.level == VerbosityLevel.PSEUDO_GRAPHICAL:
            return
        self._status_display.clear()

    def close(self) -> None:
        self.clear_status()

    def update_champions(self, champions: Mapping[int, ChampionDisplay]) -> None:
        return None


class PseudoGraphicalConsole(ConsoleInterface):
    def __init__(self) -> None:
        import curses

        super().__init__(VerbosityLevel.PSEUDO_GRAPHICAL)
        self._curses = curses
        self._screen = curses.initscr()
        curses.noecho()
        curses.cbreak()
        self._screen.keypad(True)
        self._log_lines: Deque[str] = deque(maxlen=200)
        self._progress_line = ""
        self._detail_line = ""
        self._champions: dict[int, ChampionDisplay] = {}
        self._max_champion_lines = 12

    def log(
        self,
        message: str,
        *,
        minimum_level: VerbosityLevel = VerbosityLevel.DEFAULT,
        flush: bool = False,
    ) -> None:
        if not self.should_log(minimum_level):
            return
        self._log_lines.append(message)
        self._refresh()

    def update_status(self, progress_line: str, detail_line: str) -> None:
        self._progress_line = progress_line
        self._detail_line = detail_line
        self._refresh()

    def clear_status(self) -> None:
        self._progress_line = ""
        self._detail_line = ""
        self._refresh()

    def update_champions(self, champions: Mapping[int, ChampionDisplay]) -> None:
        self._champions = dict(champions)
        self._refresh()

    def _refresh(self) -> None:
        height, width = self._screen.getmaxyx()
        self._screen.erase()

        lines_to_draw: list[str] = []

        champion_block = self._render_champions(width)
        lines_to_draw.extend(champion_block)

        header_block = self._render_status_block(height, width, len(champion_block))
        lines_to_draw.extend(header_block)

        remaining_rows = max(0, height - len(lines_to_draw))
        if remaining_rows:
            log_lines = list(self._log_lines)[-remaining_rows:]
            lines_to_draw.extend(log_lines)

        for row, line in enumerate(lines_to_draw[:height]):
            self._screen.addnstr(row, 0, line, width - 1)

        self._screen.refresh()

    def _render_champions(self, width: int) -> list[str]:
        if not self._champions or width < 4:
            return []

        sorted_items = sorted(self._champions.items())
        num_arenas = len(sorted_items)
        min_inner = 16

        max_columns = max(1, (width - 1) // (min_inner + 1))
        columns = min(num_arenas, max_columns)
        while columns > 1:
            total_inner = width - (columns + 1)
            if total_inner >= columns * min_inner:
                break
            columns -= 1

        total_inner = max(0, width - (columns + 1))
        if columns <= 0 or total_inner < 0:
            return []

        base_width = total_inner // columns if columns else total_inner
        remainder = total_inner % columns if columns else 0
        column_widths = [
            base_width + (1 if index < remainder else 0) for index in range(columns)
        ]

        lines: list[str] = []
        for start_index in range(0, num_arenas, columns):
            row_items = sorted_items[start_index : start_index + columns]
            row_widths = column_widths[: len(row_items)]

            header_line = "+"
            for (arena_index, champion), col_width in zip(row_items, row_widths):
                title = f" Arena {arena_index} Champion "
                if champion.warrior_id is not None:
                    title += f"#{champion.warrior_id} "
                header_line += title.strip().center(col_width, "-")[:col_width]
                header_line += "+"
            lines.append(header_line)

            formatted_columns = [
                champion.formatted_lines(self._max_champion_lines)
                for _arena, champion in row_items
            ]
            max_height = max((len(column) for column in formatted_columns), default=0)

            for line_index in range(max_height):
                content_line = "|"
                for col_width, column_lines in zip(row_widths, formatted_columns):
                    segment = (
                        column_lines[line_index] if line_index < len(column_lines) else ""
                    )
                    segment = segment[:col_width]
                    content_line += segment.ljust(col_width)
                    content_line += "|"
                lines.append(content_line)

            footer_line = "+"
            for col_width in row_widths:
                footer_line += "-" * col_width
                footer_line += "+"
            lines.append(footer_line)

        return lines

    def _render_status_block(
        self, height: int, width: int, champion_rows: int
    ) -> list[str]:
        available_rows = max(0, height - champion_rows)
        if available_rows <= 0:
            return []

        header_lines: list[str] = []
        if self._progress_line:
            header_lines.append(self._progress_line)
        if self._detail_line:
            header_lines.append(self._detail_line)

        longest_warrior, longest_streak = self.tracker.longest_streak
        if longest_warrior is not None and available_rows > 0:
            header_lines.append(
                f"Longest streak: Warrior {longest_warrior} ({longest_streak} wins)"
            )

        if not header_lines or width < 4:
            return header_lines[:available_rows]

        content_width = width - 2
        box_lines = ["+" + "-" * content_width + "+"]
        for line in ["[Statistics]"] + header_lines:
            text = line[:content_width]
            box_lines.append("|" + text.ljust(content_width) + "|")
        box_lines.append("+" + "-" * content_width + "+")
        return box_lines[:available_rows]

    def close(self) -> None:
        try:
            self.clear_status()
        finally:
            self._curses.nocbreak()
            self._screen.keypad(False)
            self._curses.echo()
            self._curses.endwin()
        for line in self._log_lines:
            print(line)


_console_manager: ConsoleInterface = SimpleConsole(VerbosityLevel.DEFAULT)


def get_console() -> ConsoleInterface:
    return _console_manager


def set_console_verbosity(level: VerbosityLevel) -> VerbosityLevel:
    global _console_manager, _VERBOSITY_LEVEL

    previous_manager = _console_manager

    if isinstance(previous_manager, PseudoGraphicalConsole):
        try:
            previous_manager.close()
        except Exception:
            pass

    if level == VerbosityLevel.PSEUDO_GRAPHICAL:
        try:
            import curses  # noqa: F401

            _console_manager = PseudoGraphicalConsole()
        except ImportError:
            warnings.warn(
                "Pseudo-graphical console failed to load; falling back to default.",
                RuntimeWarning,
            )
            level = VerbosityLevel.DEFAULT
            _console_manager = SimpleConsole(level)
        except Exception as exc:
            warnings.warn(
                f"Unable to start pseudo-graphical console: {exc}. "
                "Falling back to default output.",
                RuntimeWarning,
            )
            level = VerbosityLevel.DEFAULT
            _console_manager = SimpleConsole(level)
    else:
        _console_manager = SimpleConsole(level)

    _VERBOSITY_LEVEL = level
    return _VERBOSITY_LEVEL


def close_console() -> None:
    try:
        _console_manager.close()
    except Exception:
        pass


def console_log(
    message: str,
    *,
    minimum_level: VerbosityLevel = VerbosityLevel.DEFAULT,
    flush: bool = False,
) -> None:
    get_console().log(message, minimum_level=minimum_level, flush=flush)


def console_update_status(progress_line: str, detail_line: str) -> None:
    get_console().update_status(progress_line, detail_line)


def console_clear_status() -> None:
    get_console().clear_status()


def console_update_champions(
    champions: Mapping[int, ChampionDisplay]
) -> None:
    get_console().update_champions(champions)


__all__ = [
    "VerbosityLevel",
    "BattleStatisticsTracker",
    "ConsoleInterface",
    "StatusDisplay",
    "SimpleConsole",
    "PseudoGraphicalConsole",
    "get_console",
    "set_console_verbosity",
    "close_console",
    "console_log",
    "console_update_status",
    "console_clear_status",
    "console_update_champions",
    "ChampionDisplay",
]

