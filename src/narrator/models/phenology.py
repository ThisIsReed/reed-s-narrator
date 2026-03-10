"""Phenology domain models."""

from __future__ import annotations

from pydantic import Field

from narrator.models.base import DomainModel


class PhenologyState(DomainModel):
    day_of_year: int = Field(default=0, ge=0, lt=120)
    season: str = Field(default="spring", min_length=1)
    climate: str = Field(default="mild", min_length=1)
    festivals: tuple[str, ...] = ()
    season_progress: float = Field(default=0.0, ge=0.0, le=1.0)
