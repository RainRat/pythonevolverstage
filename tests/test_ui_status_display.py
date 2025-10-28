"""Tests for the ``StatusDisplay`` helper used by the console UIs."""

from __future__ import annotations

import io
import pathlib
import sys

import pytest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ui


class _StringIOStatusDisplay(ui.StatusDisplay):
    """A ``StatusDisplay`` that writes to an in-memory buffer."""

    def __init__(self) -> None:
        super().__init__()
        self.buffer = io.StringIO()

    def _stream(self):  # type: ignore[override]
        return self.buffer

    def _supports_ansi(self, stream) -> bool:  # type: ignore[override]
        return False


def test_status_display_renders_updates_after_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even fast successive updates must eventually reach the stream."""

    fake_time = [1.0]

    def fake_monotonic() -> float:
        return fake_time[0]

    display = _StringIOStatusDisplay()

    monkeypatch.setattr(ui.time, "monotonic", fake_monotonic)

    display.update("progress 1", "detail 1")
    assert "progress 1" in display.buffer.getvalue()

    fake_time[0] += 0.01
    display.update("progress 2", "detail 2")

    # Throttled update should not immediately appear
    output_after_throttle = display.buffer.getvalue()
    assert "progress 2" not in output_after_throttle

    # Once enough time has elapsed, the buffered update is rendered on the next call
    fake_time[0] += ui._STATUS_UPDATE_MIN_INTERVAL
    display.update("progress 2", "detail 2")

    final_output = display.buffer.getvalue()
    assert "progress 2" in final_output
