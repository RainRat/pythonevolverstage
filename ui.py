"""Console user interface helpers for the Core War evolver stage."""

from __future__ import annotations

import sys
import time
import warnings
from collections import deque
from enum import Enum
from typing import Deque, Optional, Tuple


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

    def close(self) -> None:
        pass


class StatusDisplay:
    """Utility for maintaining a two-line rolling status output."""

    def __init__(self) -> None:
        self._active_lines = 0
        self._last_update_time = 0.0
        self._last_lines: Optional[Tuple[str, str]] = None

    def _stream(self):
        return sys.stdout

    def _supports_ansi(self, stream) -> bool:
        return bool(getattr(stream, "isatty", lambda: False)())

    def update(self, line1: str, line2: str) -> None:
        lines_tuple = (line1, line2)
        if self._last_lines == lines_tuple:
            return

        now = time.monotonic()
        if self._last_update_time:
            elapsed = now - self._last_update_time
            if elapsed < _STATUS_UPDATE_MIN_INTERVAL:
                return

        self._last_update_time = now

        stream = self._stream()
        supports_ansi = self._supports_ansi(stream)
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
        self._last_lines = lines_tuple

    def clear(self) -> None:
        if not self._active_lines:
            self._last_lines = None
            self._last_update_time = 0.0
            return

        stream = self._stream()
        supports_ansi = self._supports_ansi(stream)
        if not supports_ansi:
            self._active_lines = 0
            self._last_lines = None
            self._last_update_time = 0.0
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

    def _refresh(self) -> None:
        height, width = self._screen.getmaxyx()
        self._screen.erase()
        row = 0

        header_lines = []
        if self._progress_line:
            header_lines.append(self._progress_line)
        if self._detail_line:
            header_lines.append(self._detail_line)

        longest_warrior, longest_streak = self.tracker.longest_streak
        if longest_warrior is not None and height - len(header_lines) > 0:
            header_lines.append(
                f"Longest streak: Warrior {longest_warrior} ({longest_streak} wins)"
            )

        for line in header_lines:
            if row >= height:
                break
            self._screen.addnstr(row, 0, line, width - 1)
            row += 1

        remaining_rows = height - row
        if remaining_rows <= 0:
            self._screen.refresh()
            return

        log_lines = list(self._log_lines)[-remaining_rows:]
        for line in log_lines:
            if row >= height:
                break
            self._screen.addnstr(row, 0, line, width - 1)
            row += 1

        self._screen.refresh()

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
            _console_manager = PseudoGraphicalConsole()
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
]

