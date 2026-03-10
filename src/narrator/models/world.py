"""World state domain model."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from narrator.models.base import DomainModel
from narrator.models.character import Character
from narrator.models.enums import Granularity
from narrator.models.event import Event
from narrator.models.knowledge import PropagationTask
from narrator.models.phenology import PhenologyState


class WorldState(DomainModel):
    tick: int = Field(..., ge=0)
    seed: int
    granularity: Granularity = Granularity.DAY
    characters: dict[str, Character] = Field(default_factory=dict)
    events: dict[str, Event] = Field(default_factory=dict)
    facts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    beliefs: dict[str, tuple[dict[str, Any], ...]] = Field(default_factory=dict)
    pending_propagation: tuple[PropagationTask, ...] = ()
    resources: dict[str, float] = Field(default_factory=dict)
    flags: dict[str, bool] = Field(default_factory=dict)
    phenology: PhenologyState = Field(default_factory=PhenologyState)

    @model_validator(mode="after")
    def validate_character_keys(self) -> "WorldState":
        for key, character in self.characters.items():
            if key != character.id:
                raise ValueError(f"character key mismatch: {key} != {character.id}")
        return self

    @model_validator(mode="after")
    def validate_event_keys(self) -> "WorldState":
        for key, event in self.events.items():
            if key != event.id:
                raise ValueError(f"event key mismatch: {key} != {event.id}")
        return self

    @model_validator(mode="after")
    def validate_fact_keys(self) -> "WorldState":
        for key, fact in self.facts.items():
            fact_id = fact.get("id")
            if key != fact_id:
                raise ValueError(f"fact key mismatch: {key} != {fact_id}")
        return self

    @model_validator(mode="after")
    def validate_belief_keys(self) -> "WorldState":
        for key, beliefs in self.beliefs.items():
            for belief in beliefs:
                character_id = belief.get("character_id")
                if key != character_id:
                    raise ValueError(f"belief key mismatch: {key} != {character_id}")
        return self
