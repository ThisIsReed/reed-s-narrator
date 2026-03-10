from __future__ import annotations

import random

from narrator.models import Character, Granularity, StateMode, WorldState
from narrator.persistence import CheckpointManager, CheckpointRepository, SQLiteDatabase


def test_checkpoint_manager_respects_interval(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "narrator.db")
    database.initialize()
    world_state = WorldState(
        tick=1,
        seed=5,
        granularity=Granularity.DAY,
        characters={
            "hero": Character(
                id="hero",
                name="Hero",
                state_mode=StateMode.ACTIVE,
                location_id="camp",
            )
        },
    )
    with database.connect() as connection:
        manager = CheckpointManager(CheckpointRepository(connection), interval=3)
        assert manager.save_if_needed(1, world_state, random.Random(5).getstate()) is False
        assert manager.save_if_needed(3, world_state, random.Random(5).getstate()) is True
        assert manager.restore(3).world_state == world_state
