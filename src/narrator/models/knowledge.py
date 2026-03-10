"""Knowledge-related runtime models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from narrator.models.base import DomainModel

PropagationSource = Literal["direct", "rumor", "inference"]


class PropagationTask(DomainModel):
    task_id: str = Field(..., min_length=1)
    belief_id: str = Field(..., min_length=1)
    origin_character_id: str = Field(..., min_length=1)
    target_character_id: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    available_at_tick: int = Field(..., ge=0)
    fact_id: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_type: PropagationSource = "rumor"
