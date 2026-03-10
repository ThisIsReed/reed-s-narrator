from __future__ import annotations

import random

from narrator.models import (
    Action,
    ActionResult,
    Character,
    Event,
    Granularity,
    StateChange,
    StateMode,
    Verdict,
    WorldState,
)
from narrator.persistence import (
    ActionLogRepository,
    BeliefRecord,
    BeliefRepository,
    CheckpointRepository,
    EventRepository,
    FactRecord,
    FactRepository,
    SQLiteDatabase,
    WorldSnapshotRepository,
)


def build_world_state(tick: int = 12) -> WorldState:
    hero = Character(
        id="hero",
        name="Hero",
        state_mode=StateMode.ACTIVE,
        location_id="village",
        narrative_importance=0.9,
    )
    event = Event(id="evt-1", tick_created=tick, tags=("battle",))
    return WorldState(
        tick=tick,
        seed=42,
        granularity=Granularity.DAY,
        characters={"hero": hero},
        events={"evt-1": event},
        resources={"food": 12.5},
        flags={"storm": True},
    )


def build_action_result() -> ActionResult:
    return ActionResult(
        action=Action(
            character_id="hero",
            action_type="march",
            parameters={"distance": 3},
            reasoning="follow the road",
        ),
        verdict=Verdict.FALLBACK,
        state_changes=(
            StateChange(
                path="resources.food",
                before=12.5,
                after=10.0,
                reason="march_cost",
            ),
        ),
        retry_count=2,
        is_fallback=True,
        fallback_reason="llm_timeout",
        flavor_text="The troop moves slowly.",
    )


def test_database_initialize_creates_wp04_tables(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "narrator.db")
    database.initialize()
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    table_names = {row["name"] for row in rows}
    assert {
        "action_log",
        "beliefs",
        "checkpoints",
        "events",
        "facts",
        "schema_migrations",
        "tick_audit",
        "world_snapshots",
    }.issubset(table_names)


def test_repositories_round_trip_payloads(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "narrator.db")
    database.initialize()
    world_state = build_world_state()
    action_result = build_action_result()
    with database.connect() as connection:
        WorldSnapshotRepository(connection).save(world_state)
        EventRepository(connection).save(world_state.events["evt-1"])
        FactRepository(connection).save(
            FactRecord(fact_id="fact-1", tick=12, payload={"truth": "storm"})
        )
        BeliefRepository(connection).save(
            BeliefRecord(
                character_id="hero",
                belief_id="belief-1",
                tick=12,
                payload={"known": False},
            )
        )
        ActionLogRepository(connection).save(tick=12, result=action_result)

        loaded_world = WorldSnapshotRepository(connection).get(12)
        loaded_events = EventRepository(connection).list_by_tick(12)
        loaded_facts = FactRepository(connection).list_all()
        loaded_beliefs = BeliefRepository(connection).list_for_character("hero")
        loaded_actions = ActionLogRepository(connection).list_by_tick(12)

    assert loaded_world == world_state
    assert loaded_events == (world_state.events["evt-1"],)
    assert loaded_facts == (FactRecord("fact-1", 12, {"truth": "storm"}),)
    assert loaded_beliefs == (BeliefRecord("hero", "belief-1", 12, {"known": False}),)
    assert loaded_actions == (action_result,)


def test_checkpoint_repository_restores_rng_state(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "narrator.db")
    database.initialize()
    rng = random.Random(7)
    baseline = [rng.randint(1, 100) for _ in range(3)]
    saved_state = rng.getstate()
    world_state = build_world_state(tick=20)
    with database.connect() as connection:
        repository = CheckpointRepository(connection)
        repository.save(tick=20, world_state=world_state, rng_state=saved_state)
        checkpoint = repository.load(20)

    restored_rng = random.Random()
    restored_rng.setstate(checkpoint.rng_state)
    assert checkpoint.world_state == world_state
    assert baseline == [42, 20, 51]
    assert [rng.randint(1, 100) for _ in range(3)] == [
        restored_rng.randint(1, 100) for _ in range(3)
    ]
