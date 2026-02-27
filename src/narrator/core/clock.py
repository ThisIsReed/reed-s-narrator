"""Global tick clock for deterministic simulation."""

from __future__ import annotations

DEFAULT_START_TICK = 0
DEFAULT_STEP = 1


class GlobalClock:
    """Maintain monotonic global tick progression."""

    def __init__(self, start_tick: int = DEFAULT_START_TICK) -> None:
        if start_tick < 0:
            raise ValueError("start_tick must be >= 0")
        self._tick = start_tick

    def current_tick(self) -> int:
        return self._tick

    def advance(self, step: int = DEFAULT_STEP) -> int:
        self._validate_step(step)
        self._tick += step
        return self._tick

    def peek(self, step: int = DEFAULT_STEP) -> int:
        self._validate_step(step)
        return self._tick + step

    @staticmethod
    def _validate_step(step: int) -> None:
        if step <= 0:
            raise ValueError("step must be > 0")
