from __future__ import annotations

from narrator.models import Character, Granularity, StateMode, WorldState
from narrator.phenology import apply_phenology


def _build_world(
    *,
    long_action: str | None = None,
    poor_harvest: bool = False,
) -> WorldState:
    character = Character(
        id="c-1",
        name="Alice",
        state_mode=StateMode.ACTIVE,
        location_id="loc-1",
        long_action=long_action,
    )
    return WorldState(
        tick=0,
        seed=2026,
        granularity=Granularity.DAY,
        characters={"c-1": character},
        resources={
            "military_readiness": 100.0,
            "disease_pressure": 5.0,
            "grain_stock": 80.0,
        },
        flags={"poor_harvest": poor_harvest},
    )


def test_winter_march_penalty_updates_numeric_state() -> None:
    result = apply_phenology(_build_world(long_action="march"), tick=105)

    assert result.world.resources["military_readiness"] == 85.0
    assert result.world.phenology.day_of_year == 105
    assert [change.path for change in result.state_changes] == [
        "phenology.day_of_year",
        "resources.military_readiness",
    ]


def test_rainy_season_raises_disease_pressure() -> None:
    result = apply_phenology(_build_world(), tick=45)

    assert result.world.resources["disease_pressure"] == 15.0
    assert result.snapshot.climate == "rainy"
    assert result.audit_log[1].matched is True


def test_poor_harvest_reduces_grain_stock() -> None:
    result = apply_phenology(_build_world(poor_harvest=True), tick=75)

    assert result.world.resources["grain_stock"] == 60.0
    assert result.snapshot.season == "autumn"
    assert result.audit_log[2].rule_name == "poor_harvest_grain_drop"


def test_phenology_update_still_advances_numeric_state_without_special_rule() -> None:
    result = apply_phenology(_build_world(), tick=5)

    assert result.world.resources["military_readiness"] == 100.0
    assert len(result.state_changes) == 1
    assert result.state_changes[0].path == "phenology.day_of_year"
