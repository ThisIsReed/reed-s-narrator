"""Event domain model."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from narrator.models.base import DomainModel


class Event(DomainModel):
    id: str = Field(..., min_length=1)
    tick_created: int = Field(..., ge=0)
    tags: tuple[str, ...] = ()
    impact_scope: dict[str, Any] = Field(default_factory=dict)
    hard_effects: tuple[str, ...] = ()
    soft_prompts: tuple[str, ...] = ()
    resolved: bool = False
