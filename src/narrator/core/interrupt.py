"""Interrupt detection manager for long-running tasks."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field

from narrator.models import LongActionStatus
from narrator.models.base import DomainModel
from narrator.models.world import WorldState


class InterruptSignal(DomainModel):
    character_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    tick: int = Field(..., ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InterruptRule(Protocol):
    def check(self, world: WorldState, tick: int) -> tuple[InterruptSignal, ...]:
        ...


class InterruptManager:
    """Collect interrupt signals from registered interrupt rules."""

    def __init__(self) -> None:
        self._rules: list[InterruptRule] = []

    def register(self, rule: InterruptRule) -> None:
        self._rules.append(rule)

    def check(self, world: WorldState, tick: int) -> tuple[InterruptSignal, ...]:
        if tick < 0:
            raise ValueError("tick must be >= 0")
        signals: list[InterruptSignal] = []
        for rule in self._rules:
            signals.extend(rule.check(world, tick))
        return tuple(signals)


class TargetedEventInterruptRule:
    """Interrupt long actions when an unresolved targeted event appears."""

    def check(self, world: WorldState, tick: int) -> tuple[InterruptSignal, ...]:
        signals: list[InterruptSignal] = []
        for event in sorted(world.events.values(), key=lambda item: (item.tick_created, item.id)):
            if event.resolved:
                continue
            target_id = event.impact_scope.get("target_character_id")
            if not isinstance(target_id, str):
                continue
            character = world.characters.get(target_id)
            if character is None or character.long_action is None:
                continue
            if character.long_action.status is not LongActionStatus.IN_PROGRESS:
                continue
            signals.append(
                InterruptSignal(
                    character_id=target_id,
                    reason="targeted_event_interrupt",
                    tick=tick,
                    metadata={
                        "event_id": event.id,
                        "action_type": character.long_action.action_type,
                    },
                )
            )
        return tuple(signals)


def build_default_interrupt_manager() -> InterruptManager:
    manager = InterruptManager()
    manager.register(TargetedEventInterruptRule())
    return manager
