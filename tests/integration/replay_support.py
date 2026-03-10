from __future__ import annotations

import random
import subprocess
import sys
from pathlib import Path

from narrator.agents import RetryOutcome
from narrator.agents.intent import IntentPayload
from narrator.config import SpotlightConfig, SpotlightWeights
from narrator.core.clock import GlobalClock
from narrator.knowledge import BeliefStore, Fact, FactStore, FactVisibility, KnowledgeAssembler
from narrator.models import Character, Granularity, StateMode, WorldState
from narrator.models import Action, ActionResult, Event, StateChange, Verdict
from narrator.orchestrator import EventGenerator, EventPool, GranularityPlanner, NarratorController
from narrator.orchestrator import SpotlightDirector
from narrator.persistence import ActionLogRepository, CheckpointManager, CheckpointRepository
from narrator.persistence import SQLiteDatabase, WorldSnapshotRepository

TOTAL_TICKS = 1000
CHECKPOINT_INTERVAL = 100
ACTIVE_EVENT_INTERVAL = 10


class SparseEventGenerator(EventGenerator):
    def generate(self, world: WorldState, tick: int) -> tuple[Event, ...]:
        if tick % ACTIVE_EVENT_INTERVAL != 0:
            return ()
        target_id = target_character_id(world, tick)
        location_id = world.characters[target_id].location_id
        return (
            Event(
                id=f"incident-{tick}",
                tick_created=tick,
                impact_scope={
                    "location_id": location_id,
                    "target_character_id": target_id,
                },
            ),
        )


class AuditingRetryRuntime:
    def __init__(self) -> None:
        self.call_count = 0

    async def execute(self, character, context, settlement_factory) -> RetryOutcome:
        self.call_count += 1
        assert visible_fact_ids(context) == expected_fact_ids(character)
        settlement = settlement_factory(build_intent(character.id))
        action_key = f"{character.id}_actions"
        event_id = f"incident-{settlement.tick}"
        current_value = settlement.world.resources.get(action_key, 0.0)
        return RetryOutcome(
            result=ActionResult(
                action=Action(
                    character_id=character.id,
                    action_type="observe",
                    parameters={"event_id": event_id},
                    source_event_id=event_id,
                ),
                verdict=Verdict.APPROVED,
                verdict_reason="approved",
                state_changes=(
                    StateChange(
                        path=f"resources.{action_key}",
                        before=current_value,
                        after=current_value + 1.0,
                        reason="record active execution",
                    ),
                    StateChange(
                        path=f"events.{event_id}.resolved",
                        before=False,
                        after=True,
                        reason="resolve event after execution",
                    ),
                ),
                flavor_text="resolved incident",
            ),
            attempts=(),
        )


async def run_long_simulation(
    database: SQLiteDatabase,
    runtime: AuditingRetryRuntime,
) -> tuple[WorldState, object]:
    world = build_world()
    with database.connect() as connection:
        controller = build_controller(
            connection=connection,
            world=world,
            runtime=runtime,
            rng=random.Random(world.seed),
        )
        final_result = await run_ticks(controller, TOTAL_TICKS)
        checkpoint = CheckpointRepository(connection).load(500)
        checkpoint_ticks = CheckpointRepository(connection).list_ticks()
    assert checkpoint_ticks == tuple(range(CHECKPOINT_INTERVAL, TOTAL_TICKS + 1, CHECKPOINT_INTERVAL))
    return final_result.world, checkpoint


async def replay_from_checkpoint(database: SQLiteDatabase, checkpoint_state) -> WorldState:
    replay_rng = random.Random()
    replay_rng.setstate(checkpoint_state.rng_state)
    with database.connect() as connection:
        controller = build_controller(
            connection=connection,
            world=checkpoint_state.world_state,
            runtime=AuditingRetryRuntime(),
            rng=replay_rng,
            start_tick=checkpoint_state.tick,
        )
        final_result = await run_ticks(controller, TOTAL_TICKS - checkpoint_state.tick)
    return final_result.world


def build_controller(
    connection,
    world: WorldState,
    runtime: AuditingRetryRuntime,
    rng: random.Random,
    start_tick: int = 0,
) -> NarratorController:
    return NarratorController(
        world=world,
        clock=GlobalClock(start_tick=start_tick),
        event_pool=EventPool((SparseEventGenerator(),)),
        granularity_planner=GranularityPlanner(instant_mode_max_rounds=2),
        spotlight=SpotlightDirector(build_spotlight_config()),
        knowledge_assembler=build_knowledge(),
        retry_runtime=runtime,
        world_repository=WorldSnapshotRepository(connection),
        action_log_repository=ActionLogRepository(connection),
        checkpoint_manager=CheckpointManager(
            CheckpointRepository(connection),
            interval=CHECKPOINT_INTERVAL,
        ),
        rng=rng,
    )


async def run_ticks(controller: NarratorController, steps: int):
    result = None
    for _ in range(steps):
        result = await controller.run_tick()
    assert result is not None
    return result


def build_world() -> WorldState:
    characters = {
        character.id: character
        for character in (
            Character(id="c0", name="C0", state_mode=StateMode.DORMANT, location_id="harbor"),
            Character(id="c1", name="C1", state_mode=StateMode.DORMANT, location_id="harbor"),
            Character(id="c2", name="C2", state_mode=StateMode.DORMANT, location_id="forest"),
            Character(id="c3", name="C3", state_mode=StateMode.DORMANT, location_id="forest"),
            Character(id="c4", name="C4", state_mode=StateMode.DORMANT, location_id="hill"),
        )
    }
    return WorldState(
        tick=0,
        seed=17,
        granularity=Granularity.DAY,
        characters=characters,
    )


def build_knowledge() -> KnowledgeAssembler:
    fact_store = FactStore(
        facts=(
            Fact(id="global-news", tick_created=0, content="global"),
            Fact(
                id="harbor-order",
                tick_created=0,
                content="harbor",
                visibility=FactVisibility(scope="location", location_ids=("harbor",)),
            ),
            Fact(
                id="private-c0",
                tick_created=0,
                content="private",
                visibility=FactVisibility(scope="private", character_ids=("c0",)),
            ),
        )
    )
    return KnowledgeAssembler(fact_store, BeliefStore())


def build_spotlight_config() -> SpotlightConfig:
    return SpotlightConfig(
        weights=SpotlightWeights(
            geo=0.0,
            relation=1.0,
            availability=0.0,
            narrative_importance=0.0,
            random_noise=0.0,
        ),
        threshold_active=0.9,
        threshold_passive=0.1,
    )


def target_character_id(world: WorldState, tick: int) -> str:
    ordered_ids = tuple(sorted(world.characters))
    index = ((tick // ACTIVE_EVENT_INTERVAL) - 1) % len(ordered_ids)
    return ordered_ids[index]


def build_intent(character_id: str) -> IntentPayload:
    return IntentPayload(
        character_id=character_id,
        action_type="observe",
        parameters={},
        flavor_text="inspect incident",
    )


def visible_fact_ids(context) -> tuple[str, ...]:
    return tuple(entry.entry_id for entry in context.facts)


def expected_fact_ids(character: Character) -> tuple[str, ...]:
    fact_ids = ["global-news"]
    if character.location_id == "harbor":
        fact_ids.append("harbor-order")
    if character.id == "c0":
        fact_ids.append("private-c0")
    return tuple(sorted(fact_ids))


def seed_replay_database(db_path: Path) -> None:
    database = SQLiteDatabase(db_path)
    database.initialize()
    with database.connect() as connection:
        snapshots = WorldSnapshotRepository(connection)
        checkpoints = CheckpointRepository(connection)
        first = build_sample_world(tick=1, food=5.0)
        second = build_sample_world(tick=2, food=4.0)
        snapshots.save(first)
        snapshots.save(second)
        checkpoints.save(2, second, random.Random(7).getstate())


def build_sample_world(tick: int, food: float) -> WorldState:
    return WorldState(
        tick=tick,
        seed=7,
        granularity=Granularity.DAY,
        characters={
            "hero": Character(
                id="hero",
                name="Hero",
                state_mode=StateMode.ACTIVE,
                location_id="camp",
            )
        },
        resources={"food": food},
    )


def run_replay_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "replay.py"
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
