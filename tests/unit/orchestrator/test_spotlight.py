from __future__ import annotations

from random import Random

from narrator.config import SpotlightConfig, SpotlightWeights
from narrator.models import Character, Event, StateMode
from narrator.orchestrator import SpotlightDirector


def test_spotlight_assigns_active_passive_and_dormant() -> None:
    director = SpotlightDirector(
        SpotlightConfig(
            weights=SpotlightWeights(
                geo=0.25,
                relation=0.25,
                availability=0.2,
                narrative_importance=0.2,
                random_noise=0.1,
            ),
            threshold_active=0.7,
            threshold_passive=0.4,
        )
    )
    characters = {
        "hero": Character(
            id="hero",
            name="Hero",
            state_mode=StateMode.DORMANT,
            location_id="town",
            narrative_importance=0.9,
        ),
        "guard": Character(
            id="guard",
            name="Guard",
            state_mode=StateMode.DORMANT,
            location_id="town",
            narrative_importance=0.2,
        ),
        "sleeper": Character(
            id="sleeper",
            name="Sleeper",
            state_mode=StateMode.DORMANT,
            location_id="cave",
            narrative_importance=0.0,
            long_action="sleep",
        ),
    }
    events = (
        Event(
            id="alarm",
            tick_created=1,
            impact_scope={"location_id": "town", "target_character_id": "hero"},
        ),
    )

    assignments = director.assign(characters, events, Random(7))

    assert assignments.active_ids == ("hero",)
    assert assignments.passive_ids == ("guard",)
    assert assignments.dormant_ids == ("sleeper",)
