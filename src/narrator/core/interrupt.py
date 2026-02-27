"""Interrupt detection manager for long-running tasks."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field

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
