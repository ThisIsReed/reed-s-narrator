"""Character belief storage for subjective knowledge."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from narrator.models.base import DomainModel

BeliefSource = Literal["direct", "rumor", "inference"]


class Belief(DomainModel):
    character_id: str = Field(..., min_length=1)
    belief_id: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    acquired_tick: int = Field(..., ge=0)
    fact_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_type: BeliefSource = "direct"


class BeliefStore:
    def __init__(self, beliefs: tuple[Belief, ...] = ()) -> None:
        self._beliefs = {
            self._belief_key(belief.character_id, belief.belief_id): belief for belief in beliefs
        }

    def upsert(self, belief: Belief) -> None:
        key = self._belief_key(belief.character_id, belief.belief_id)
        self._beliefs[key] = belief

    def list_for_character(self, character_id: str) -> tuple[Belief, ...]:
        beliefs = [
            belief
            for belief in self._beliefs.values()
            if belief.character_id == character_id
        ]
        return tuple(sorted(beliefs, key=lambda item: item.belief_id))

    def get(self, character_id: str, belief_id: str) -> Belief:
        belief = self._beliefs.get(self._belief_key(character_id, belief_id))
        if belief is None:
            raise LookupError(f"belief not found: {character_id}/{belief_id}")
        return belief

    @staticmethod
    def _belief_key(character_id: str, belief_id: str) -> str:
        return f"{character_id}:{belief_id}"
