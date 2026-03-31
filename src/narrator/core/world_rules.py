"""Built-in world rules for orchestrator settlement stages."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from narrator.core.rule_engine import RuleContext, RuleEngine
from narrator.models import (
    LongActionInterruptRecord,
    LongActionState,
    LongActionStatus,
    StateChange,
    WorldState,
)

INTERRUPT_SIGNALS_KEY = "interrupt_signals"
UNRESOLVED_EVENT_PRESSURE_KEY = "unresolved_event_pressure"


class LongActionInterruptRule:
    name = "long_action_interrupt"
    priority = 10

    def match(self, world: WorldState, context: RuleContext) -> bool:
        return any(_active_long_action(world, character_id) for character_id in _signal_map(context))

    def apply(self, world: WorldState, context: RuleContext) -> tuple[StateChange, ...]:
        changes: list[StateChange] = []
        for character_id, signals in sorted(_signal_map(context).items()):
            character = world.characters.get(character_id)
            if character is None or character.long_action is None:
                continue
            updated = _pause_long_action(character.long_action, signals, context.tick)
            changes.append(
                StateChange(
                    path=f"characters.{character_id}.long_action",
                    before=character.long_action.model_dump(mode="json"),
                    after=updated.model_dump(mode="json"),
                    reason="long action interrupted",
                )
            )
        return tuple(changes)


class LongActionResumeRule:
    name = "long_action_resume"
    priority = 20

    def match(self, world: WorldState, context: RuleContext) -> bool:
        return any(
            character.long_action is not None
            and character.long_action.status is LongActionStatus.PAUSED
            and character.id not in _signal_map(context)
            and not _has_unresolved_targeted_event(world, character.id)
            for character in world.characters.values()
        )

    def apply(self, world: WorldState, context: RuleContext) -> tuple[StateChange, ...]:
        changes: list[StateChange] = []
        for character_id, character in sorted(world.characters.items()):
            long_action = character.long_action
            if long_action is None or long_action.status is not LongActionStatus.PAUSED:
                continue
            if character_id in _signal_map(context):
                continue
            if _has_unresolved_targeted_event(world, character_id):
                continue
            updated = long_action.model_copy(
                update={"status": LongActionStatus.IN_PROGRESS, "pause_reason": None}
            )
            changes.append(
                StateChange(
                    path=f"characters.{character_id}.long_action",
                    before=long_action.model_dump(mode="json"),
                    after=updated.model_dump(mode="json"),
                    reason="long action resumed",
                )
            )
        return tuple(changes)


class LongActionProgressRule:
    name = "long_action_progress"
    priority = 30

    def match(self, world: WorldState, context: RuleContext) -> bool:
        return any(_progressible_action(character.long_action, context.tick) for character in world.characters.values())

    def apply(self, world: WorldState, context: RuleContext) -> tuple[StateChange, ...]:
        changes: list[StateChange] = []
        for character_id, character in sorted(world.characters.items()):
            long_action = character.long_action
            if not _progressible_action(long_action, context.tick):
                continue
            before = long_action.model_dump(mode="json")
            if long_action.remaining_ticks == 1:
                changes.append(
                    StateChange(
                        path=f"characters.{character_id}.long_action",
                        before=before,
                        after=None,
                        reason="long action completed",
                    )
                )
                continue
            updated = long_action.model_copy(
                update={
                    "remaining_ticks": long_action.remaining_ticks - 1,
                    "last_progress_tick": context.tick,
                }
            )
            changes.append(
                StateChange(
                    path=f"characters.{character_id}.long_action",
                    before=before,
                    after=updated.model_dump(mode="json"),
                    reason="long action progressed",
                )
            )
        return tuple(changes)


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
    engine.register(LongActionInterruptRule())
    engine.register(LongActionResumeRule())
    engine.register(LongActionProgressRule())
    engine.register(UnresolvedEventPressureRule())
    return engine


def _signal_map(context: RuleContext) -> dict[str, tuple[dict[str, Any], ...]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    raw_signals = context.metadata.get(INTERRUPT_SIGNALS_KEY, ())
    if not isinstance(raw_signals, tuple):
        return {}
    for signal in raw_signals:
        if not isinstance(signal, dict):
            continue
        character_id = signal.get("character_id")
        if isinstance(character_id, str):
            grouped[character_id].append(signal)
    return {character_id: tuple(items) for character_id, items in grouped.items()}


def _active_long_action(world: WorldState, character_id: str) -> bool:
    character = world.characters.get(character_id)
    if character is None or character.long_action is None:
        return False
    return character.long_action.status is LongActionStatus.IN_PROGRESS


def _pause_long_action(
    long_action: LongActionState,
    signals: tuple[dict[str, Any], ...],
    tick: int,
) -> LongActionState:
    last_signal = signals[-1]
    history = list(long_action.interrupt_history)
    for signal in signals:
        history.append(
            LongActionInterruptRecord(
                tick=tick,
                reason=str(signal["reason"]),
                event_id=_event_id(signal),
            )
        )
    return long_action.model_copy(
        update={
            "status": LongActionStatus.PAUSED,
            "pause_reason": str(last_signal["reason"]),
            "interrupt_history": tuple(history),
        }
    )


def _progressible_action(long_action: LongActionState | None, tick: int) -> bool:
    if long_action is None:
        return False
    if long_action.status is not LongActionStatus.IN_PROGRESS:
        return False
    return long_action.remaining_ticks > 0 and long_action.last_progress_tick < tick


def _event_id(signal: dict[str, Any]) -> str | None:
    metadata = signal.get("metadata")
    if not isinstance(metadata, dict):
        return None
    event_id = metadata.get("event_id")
    if event_id is None:
        return None
    return str(event_id)


def _has_unresolved_targeted_event(world: WorldState, character_id: str) -> bool:
    for event in world.events.values():
        if event.resolved:
            continue
        target_id = event.impact_scope.get("target_character_id")
        if target_id == character_id:
            return True
    return False
