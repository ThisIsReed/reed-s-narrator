"""Objective fact storage with visibility filtering."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from narrator.models.base import DomainModel
from narrator.models.character import Character

VisibilityScope = Literal["global", "location", "private"]


class FactVisibility(DomainModel):
    scope: VisibilityScope = "global"
    location_ids: tuple[str, ...] = ()
    character_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_targets(self) -> "FactVisibility":
        if self.scope == "location" and not self.location_ids:
            raise ValueError("location scope requires location_ids")
        if self.scope == "private" and not self.character_ids:
            raise ValueError("private scope requires character_ids")
        if self.scope != "location" and self.location_ids:
            raise ValueError("location_ids only allowed for location scope")
        if self.scope != "private" and self.character_ids:
            raise ValueError("character_ids only allowed for private scope")
        return self


class Fact(DomainModel):
    id: str = Field(..., min_length=1)
    tick_created: int = Field(..., ge=0)
    content: str = Field(..., min_length=1)
    visibility: FactVisibility = Field(default_factory=FactVisibility)
    source_event_id: str | None = None
    tags: tuple[str, ...] = ()


class FactStore:
    def __init__(self, facts: tuple[Fact, ...] = ()) -> None:
        self._facts = {fact.id: fact for fact in facts}

    def upsert(self, fact: Fact) -> None:
        self._facts[fact.id] = fact

    def get(self, fact_id: str) -> Fact:
        fact = self._facts.get(fact_id)
        if fact is None:
            raise LookupError(f"fact not found: {fact_id}")
        return fact

    def list_all(self) -> tuple[Fact, ...]:
        return tuple(sorted(self._facts.values(), key=lambda item: item.id))

    def list_visible_for(self, character: Character) -> tuple[Fact, ...]:
        visible = [fact for fact in self._facts.values() if self._can_view(character, fact)]
        return tuple(sorted(visible, key=lambda item: item.id))

    def _can_view(self, character: Character, fact: Fact) -> bool:
        visibility = fact.visibility
        if visibility.scope == "global":
            return True
        if visibility.scope == "location":
            return character.location_id in visibility.location_ids
        return character.id in visibility.character_ids
