"""Action and settlement result models."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from narrator.models.base import DomainModel
from narrator.models.enums import Verdict


class Action(DomainModel):
    character_id: str = Field(..., min_length=1)
    action_type: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    target_id: str | None = None
    source_event_id: str | None = None
    reasoning: str | None = None


class StateChange(DomainModel):
    path: str = Field(..., min_length=1)
    before: Any
    after: Any
    reason: str = Field(..., min_length=1)


class ActionResult(DomainModel):
    action: Action
    verdict: Verdict
    state_changes: tuple[StateChange, ...] = ()
    retry_count: int = Field(default=0, ge=0)
    is_fallback: bool = False
    fallback_reason: str | None = None
    flavor_text: str | None = None
