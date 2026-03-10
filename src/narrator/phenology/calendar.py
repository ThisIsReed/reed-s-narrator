"""Deterministic phenology calendar."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field

from narrator.models.base import DomainModel
from narrator.models.phenology import PhenologyState

SEASON_LENGTH = 30
YEAR_LENGTH = SEASON_LENGTH * 4


@dataclass(frozen=True)
class SeasonDefinition:
    name: str
    climate: str
    festival_day: int
    festival_name: str


class PhenologySnapshot(DomainModel):
    tick: int = Field(..., ge=0)
    day_of_year: int = Field(..., ge=0, lt=YEAR_LENGTH)
    season: str = Field(..., min_length=1)
    climate: str = Field(..., min_length=1)
    festivals: tuple[str, ...] = ()
    season_progress: float = Field(..., ge=0.0, le=1.0)

    def to_state(self) -> PhenologyState:
        return PhenologyState(
            day_of_year=self.day_of_year,
            season=self.season,
            climate=self.climate,
            festivals=self.festivals,
            season_progress=self.season_progress,
        )


class PhenologyCalendar:
    """Map ticks into seasons, climate, and festivals."""

    _seasons = (
        SeasonDefinition("spring", "mild", 10, "spring_rite"),
        SeasonDefinition("summer", "rainy", 45, "river_prayer"),
        SeasonDefinition("autumn", "dry", 75, "harvest_fair"),
        SeasonDefinition("winter", "freezing", 105, "long_night_watch"),
    )

    def snapshot_for_tick(self, tick: int) -> PhenologySnapshot:
        if tick < 0:
            raise ValueError("tick must be >= 0")
        day_of_year = tick % YEAR_LENGTH
        season_index = day_of_year // SEASON_LENGTH
        season = self._seasons[season_index]
        season_start = season_index * SEASON_LENGTH
        season_progress = (day_of_year - season_start) / (SEASON_LENGTH - 1)
        festivals = (season.festival_name,) if day_of_year == season.festival_day else ()
        return PhenologySnapshot(
            tick=tick,
            day_of_year=day_of_year,
            season=season.name,
            climate=season.climate,
            festivals=festivals,
            season_progress=season_progress,
        )
