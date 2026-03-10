"""Tick stage models for orchestrator audit."""

from __future__ import annotations

from pydantic import Field

from narrator.models import ActionResult, StateChange, WorldState
from narrator.models.base import DomainModel
from narrator.orchestrator.spotlight import SpotlightAssignments


class TickStageResult(DomainModel):
    stage: str = Field(..., min_length=1)
    audit_log: tuple[str, ...] = ()
    state_changes: tuple[StateChange, ...] = ()
    artifact_ids: tuple[str, ...] = ()


class TickResult(DomainModel):
    tick: int
    world: WorldState
    granularity_reason: str
    event_ids: tuple[str, ...] = ()
    spotlight: SpotlightAssignments
    action_results: tuple[ActionResult, ...] = ()
    checkpoint_saved: bool
    stages: tuple[TickStageResult, ...] = ()
