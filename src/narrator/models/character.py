"""Character domain model."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from narrator.models.base import DomainModel
from narrator.models.enums import LongActionStatus, StateMode


class LongActionInterruptRecord(DomainModel):
    tick: int = Field(..., ge=0)
    reason: str = Field(..., min_length=1)
    event_id: str | None = None


class LongActionState(DomainModel):
    action_type: str = Field(..., min_length=1)
    started_tick: int = Field(..., ge=0)
    remaining_ticks: int = Field(..., ge=0)
    status: LongActionStatus = LongActionStatus.IN_PROGRESS
    last_progress_tick: int = Field(default=0, ge=0)
    pause_reason: str | None = None
    interrupt_history: tuple[LongActionInterruptRecord, ...] = ()


class Character(DomainModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    state_mode: StateMode
    location_id: str = Field(..., min_length=1)
    narrative_importance: float = Field(default=0.5, ge=0.0, le=1.0)
    last_active_tick: int = Field(default=0, ge=0)
    status_effects: tuple[str, ...] = ()
    long_action: LongActionState | None = None
    state: dict[str, Any] = Field(default_factory=dict)
