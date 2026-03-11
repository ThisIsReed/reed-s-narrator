"""Narrative domain models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from narrator.models import ActionResult, StateChange
from narrator.models.base import DomainModel
from narrator.replay import ReplaySource

BeatPriority = Literal["event", "action", "world", "knowledge", "quiet"]


class NarrativeSourceTick(DomainModel):
    tick: int = Field(..., ge=0)
    source: ReplaySource
    granularity: str = Field(..., min_length=1)
    event_ids: tuple[str, ...] = ()
    active_character_ids: tuple[str, ...] = ()
    action_results: tuple[ActionResult, ...] = ()
    state_changes: tuple[StateChange, ...] = ()
    phenology_summary: str = Field(..., min_length=1)
    knowledge_summary: str = Field(..., min_length=1)
    unresolved_event_ids: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()


class NarrativeBeat(DomainModel):
    tick: int = Field(..., ge=0)
    title: str = Field(..., min_length=1)
    priority: BeatPriority
    background: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    result: str = Field(..., min_length=1)
    outlook: str = Field(..., min_length=1)
    mentioned_character_ids: tuple[str, ...] = ()
    mentioned_event_ids: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()


class NarrativeEntry(DomainModel):
    tick: int = Field(..., ge=0)
    title: str = Field(..., min_length=1)
    summary_text: str = Field(..., min_length=1)
    source_refs: tuple[str, ...] = ()
    mentioned_character_ids: tuple[str, ...] = ()
    mentioned_event_ids: tuple[str, ...] = ()


class NarrativeReport(DomainModel):
    source: ReplaySource
    ticks: tuple[int, ...] = ()
    entries: tuple[NarrativeEntry, ...] = ()
