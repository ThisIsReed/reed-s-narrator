from __future__ import annotations

import pytest

from narrator.phenology.calendar import PhenologyCalendar


def test_calendar_maps_tick_to_season_and_festival() -> None:
    calendar = PhenologyCalendar()

    spring = calendar.snapshot_for_tick(10)
    summer = calendar.snapshot_for_tick(45)
    autumn = calendar.snapshot_for_tick(75)
    winter = calendar.snapshot_for_tick(105)

    assert spring.season == "spring"
    assert spring.festivals == ("spring_rite",)
    assert summer.climate == "rainy"
    assert autumn.festivals == ("harvest_fair",)
    assert winter.season == "winter"


def test_calendar_rejects_negative_tick() -> None:
    with pytest.raises(ValueError):
        PhenologyCalendar().snapshot_for_tick(-1)
