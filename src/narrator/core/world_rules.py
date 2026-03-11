"""Built-in world rules for the orchestrator settlement stage."""

from __future__ import annotations

from narrator.core.rule_engine import RuleContext, RuleEngine
from narrator.models import StateChange, WorldState

UNRESOLVED_EVENT_PRESSURE_KEY = "unresolved_event_pressure"


class UnresolvedEventPressureRule:
    name = "unresolved_event_pressure"
    priority = 100

    def match(self, world: WorldState, context: RuleContext) -> bool:
        return self._current_value(world) != self._target_value(world)

    def apply(self, world: WorldState, context: RuleContext) -> tuple[StateChange, ...]:
        before = self._current_value(world)
        after = self._target_value(world)
        return (
            StateChange(
                path=f"resources.{UNRESOLVED_EVENT_PRESSURE_KEY}",
                before=before,
                after=after,
                reason="track unresolved event pressure",
            ),
        )

    def _current_value(self, world: WorldState) -> float | None:
        value = world.resources.get(UNRESOLVED_EVENT_PRESSURE_KEY)
        if value is None:
            return None
        return float(value)

    def _target_value(self, world: WorldState) -> float:
        unresolved_count = sum(1 for event in world.events.values() if not event.resolved)
        return float(unresolved_count)


def build_default_rule_engine() -> RuleEngine:
    engine = RuleEngine()
    engine.register(UnresolvedEventPressureRule())
    return engine
