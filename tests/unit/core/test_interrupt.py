from __future__ import annotations

import pytest

from narrator.core.interrupt import InterruptManager, InterruptSignal
from narrator.models import Character, Granularity, StateMode, WorldState


class StaticInterruptRule:
    def __init__(self, signals: tuple[InterruptSignal, ...]) -> None:
        self._signals = signals

    def check(self, world: WorldState, tick: int) -> tuple[InterruptSignal, ...]:
        return self._signals


class FailingInterruptRule:
    def check(self, world: WorldState, tick: int) -> tuple[InterruptSignal, ...]:
        raise RuntimeError("interrupt check failed")


def _build_world() -> WorldState:
    character = Character(
        id="c-1",
        name="Alice",
        state_mode=StateMode.ACTIVE,
        location_id="loc-1",
    )
    return WorldState(
        tick=0,
        seed=99,
        granularity=Granularity.DAY,
        characters={"c-1": character},
    )


def test_interrupt_manager_aggregates_by_registration_order() -> None:
    world = _build_world()
    signal_a = InterruptSignal(character_id="c-1", reason="storm", tick=2)
    signal_b = InterruptSignal(character_id="c-1", reason="attack", tick=2)
    manager = InterruptManager()
    manager.register(StaticInterruptRule((signal_a,)))
    manager.register(StaticInterruptRule((signal_b,)))
    assert manager.check(world, tick=2) == (signal_a, signal_b)


def test_interrupt_manager_returns_empty_when_no_rule_matches() -> None:
    manager = InterruptManager()
    assert manager.check(_build_world(), tick=1) == ()


def test_interrupt_manager_bubbles_rule_error() -> None:
    manager = InterruptManager()
    manager.register(FailingInterruptRule())
    with pytest.raises(RuntimeError):
        manager.check(_build_world(), tick=3)
