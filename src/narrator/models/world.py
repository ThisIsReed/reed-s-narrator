"""World state domain model."""

from __future__ import annotations

from pydantic import Field, model_validator

from narrator.models.base import DomainModel
from narrator.models.character import Character
from narrator.models.enums import Granularity
from narrator.models.event import Event


class WorldState(DomainModel):
    tick: int = Field(..., ge=0)
    seed: int
    granularity: Granularity = Granularity.DAY
    characters: dict[str, Character] = Field(default_factory=dict)
    events: dict[str, Event] = Field(default_factory=dict)
    resources: dict[str, float] = Field(default_factory=dict)
    flags: dict[str, bool] = Field(default_factory=dict)

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
