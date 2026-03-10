"""Event pool aggregation for orchestrator main loop."""

from __future__ import annotations

from abc import ABC, abstractmethod

from narrator.models import Event, WorldState
from narrator.models.base import DomainModel


class EventPoolSnapshot(DomainModel):
    active_events: tuple[Event, ...] = ()
    new_events: tuple[Event, ...] = ()


class EventGenerator(ABC):
    @abstractmethod
    def generate(self, world: WorldState, tick: int) -> tuple[Event, ...]:
        """Return new events for the given tick."""


class EventPool:
    def __init__(self, generators: tuple[EventGenerator, ...] = ()) -> None:
        self._generators = generators

    def generate(self, world: WorldState, tick: int) -> EventPoolSnapshot:
        existing = tuple(event for event in world.events.values() if not event.resolved)
        generated = self._generate_new_events(world, tick)
        active_events = _sort_events(existing + generated)
        return EventPoolSnapshot(active_events=active_events, new_events=generated)

    def _generate_new_events(self, world: WorldState, tick: int) -> tuple[Event, ...]:
        events: list[Event] = []
        existing_ids = set(world.events)
        new_ids: set[str] = set()
        for generator in self._generators:
            for event in generator.generate(world, tick):
                _ensure_unique_event_id(event.id, existing_ids, new_ids)
                new_ids.add(event.id)
                events.append(event)
        return _sort_events(tuple(events))


def _sort_events(events: tuple[Event, ...]) -> tuple[Event, ...]:
    return tuple(sorted(events, key=lambda item: (item.tick_created, item.id)))


def _ensure_unique_event_id(
    event_id: str,
    existing_ids: set[str],
    new_ids: set[str],
) -> None:
    if event_id in existing_ids:
        raise ValueError(f"event id already exists in world: {event_id}")
    if event_id in new_ids:
        raise ValueError(f"duplicate event id generated in same tick: {event_id}")
