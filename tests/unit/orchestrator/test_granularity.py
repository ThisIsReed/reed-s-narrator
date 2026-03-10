from __future__ import annotations

from narrator.models import Event, Granularity
from narrator.orchestrator import GranularityPlanner


def test_event_tag_can_switch_to_instant_mode() -> None:
    planner = GranularityPlanner(instant_mode_max_rounds=2)
    event = Event(
        id="alarm",
        tick_created=1,
        tags=("granularity:instant",),
    )

    decision = planner.decide(Granularity.DAY, (event,), instant_rounds=0)

    assert decision.granularity is Granularity.INSTANT
    assert decision.instant_rounds == 1


def test_instant_mode_returns_to_day_after_cap() -> None:
    planner = GranularityPlanner(instant_mode_max_rounds=2)

    decision = planner.decide(Granularity.INSTANT, (), instant_rounds=1)

    assert decision.granularity is Granularity.DAY
    assert decision.instant_rounds == 0
