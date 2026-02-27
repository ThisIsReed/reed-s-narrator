from __future__ import annotations

import pytest

from narrator.core.clock import GlobalClock


def test_clock_advance_is_monotonic() -> None:
    clock = GlobalClock(start_tick=10)
    assert clock.current_tick() == 10
    assert clock.advance() == 11
    assert clock.advance(step=3) == 14
    assert clock.current_tick() == 14


def test_clock_peek_does_not_mutate_state() -> None:
    clock = GlobalClock(start_tick=7)
    assert clock.peek() == 8
    assert clock.peek(step=5) == 12
    assert clock.current_tick() == 7


def test_clock_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        GlobalClock(start_tick=-1)

    clock = GlobalClock()
    with pytest.raises(ValueError):
        clock.advance(step=0)
    with pytest.raises(ValueError):
        clock.peek(step=-1)
