from __future__ import annotations

import random

from narrator.models import Character, Granularity, StateMode, WorldState
from narrator.persistence import CheckpointManager, CheckpointRepository, SQLiteDatabase


def build_world_state(tick: int, food: float) -> WorldState:
    character = Character(
        id="hero",
        name="Hero",
        state_mode=StateMode.ACTIVE,
        location_id="camp",
    )
    return WorldState(
        tick=tick,
        seed=99,
        granularity=Granularity.DAY,
        characters={"hero": character},
        resources={"food": food},
    )


def advance_world(world_state: WorldState, rng: random.Random, steps: int) -> WorldState:
    current = world_state
    for _ in range(steps):
        cost = float(rng.randint(1, 3))
        current = current.model_copy(
            update={
                "tick": current.tick + 1,
                "resources": {"food": current.resources["food"] - cost},
            }
        )
    return current


def test_checkpoint_restore_can_continue_with_same_result(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "narrator.db")
    database.initialize()
    initial_world = build_world_state(tick=0, food=20.0)
    rng = random.Random(initial_world.seed)
    world_at_tick_2 = advance_world(initial_world, rng, steps=2)
    saved_rng_state = rng.getstate()

    with database.connect() as connection:
        repository = CheckpointRepository(connection)
        manager = CheckpointManager(repository, interval=2)
        assert manager.save_if_needed(2, world_at_tick_2, saved_rng_state) is True
        restored = manager.restore(2)

    continued_world = advance_world(world_at_tick_2, rng, steps=3)
    restored_rng = random.Random()
    restored_rng.setstate(restored.rng_state)
    replayed_world = advance_world(restored.world_state, restored_rng, steps=3)

    assert replayed_world == continued_world
