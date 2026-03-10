"""Granularity decision support for orchestrator loop."""

from __future__ import annotations

from narrator.models import Event, Granularity
from narrator.models.base import DomainModel

GRANULARITY_TAG_PREFIX = "granularity:"
GRANULARITY_PRIORITY = {
    Granularity.YEAR: 0,
    Granularity.MONTH: 1,
    Granularity.DAY: 2,
    Granularity.INSTANT: 3,
}


class GranularityDecision(DomainModel):
    granularity: Granularity
    reason: str
    instant_rounds: int = 0


class GranularityPlanner:
    def __init__(self, instant_mode_max_rounds: int) -> None:
        if instant_mode_max_rounds <= 0:
            raise ValueError("instant_mode_max_rounds must be > 0")
        self._instant_mode_max_rounds = instant_mode_max_rounds

    def decide(
        self,
        current: Granularity,
        events: tuple[Event, ...],
        instant_rounds: int,
    ) -> GranularityDecision:
        requested = _event_requested_granularity(events)
        if requested is not None:
            return self._requested_decision(requested, instant_rounds)
        if current is Granularity.INSTANT:
            return self._rolling_instant_decision(instant_rounds)
        return GranularityDecision(
            granularity=current,
            reason="keep current granularity without event override",
            instant_rounds=0,
        )

    def _requested_decision(
        self,
        requested: Granularity,
        instant_rounds: int,
    ) -> GranularityDecision:
        if requested is not Granularity.INSTANT:
            return GranularityDecision(
                granularity=requested,
                reason=f"event requested {requested.value}",
                instant_rounds=0,
            )
        next_round = instant_rounds + 1
        if next_round > self._instant_mode_max_rounds:
            return GranularityDecision(
                granularity=Granularity.DAY,
                reason="instant mode capped, fallback to DAY",
                instant_rounds=0,
            )
        return GranularityDecision(
            granularity=Granularity.INSTANT,
            reason="event requested INSTANT",
            instant_rounds=next_round,
        )

    def _rolling_instant_decision(self, instant_rounds: int) -> GranularityDecision:
        next_round = instant_rounds + 1
        if next_round >= self._instant_mode_max_rounds:
            return GranularityDecision(
                granularity=Granularity.DAY,
                reason="instant mode exhausted, return to DAY",
                instant_rounds=0,
            )
        return GranularityDecision(
            granularity=Granularity.INSTANT,
            reason="continue instant mode",
            instant_rounds=next_round,
        )


def _event_requested_granularity(events: tuple[Event, ...]) -> Granularity | None:
    requested = [_event_tag_to_granularity(event.tags) for event in events]
    values = [item for item in requested if item is not None]
    if not values:
        return None
    return max(values, key=lambda item: GRANULARITY_PRIORITY[item])


def _event_tag_to_granularity(tags: tuple[str, ...]) -> Granularity | None:
    for tag in tags:
        if not tag.startswith(GRANULARITY_TAG_PREFIX):
            continue
        raw_value = tag.removeprefix(GRANULARITY_TAG_PREFIX).upper()
        return Granularity(raw_value)
    return None
