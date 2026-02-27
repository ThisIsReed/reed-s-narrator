from __future__ import annotations

import pytest
from pydantic import ValidationError

from narrator.models import Action, ActionResult, Character, Granularity, StateMode, Verdict, WorldState


def test_character_invalid_enum_rejected() -> None:
    with pytest.raises(ValidationError):
        Character(
            id="c-1",
            name="A",
            state_mode="INVALID",
            location_id="loc-1",
        )


def test_character_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        Character(
            id="c-1",
            name="A",
            state_mode=StateMode.ACTIVE,
            location_id="loc-1",
            unknown_field=True,
        )


def test_world_state_requires_matching_character_key() -> None:
    with pytest.raises(ValidationError):
        WorldState(
            tick=0,
            seed=123,
            granularity=Granularity.DAY,
            characters={
                "key-x": Character(
                    id="c-1",
                    name="A",
                    state_mode=StateMode.PASSIVE,
                    location_id="loc-1",
                ),
            },
        )


def test_action_result_accepts_valid_contract() -> None:
    result = ActionResult(
        action=Action(
            character_id="c-1",
            action_type="rest",
            parameters={"duration_hours": 8},
        ),
        verdict=Verdict.APPROVED,
    )
    assert result.verdict == Verdict.APPROVED
