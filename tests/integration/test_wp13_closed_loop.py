from __future__ import annotations

import random

import pytest

from narrator.agents import RetryOutcome
from narrator.agents.intent import IntentPayload
from narrator.config import SpotlightConfig, SpotlightWeights
from narrator.core.clock import GlobalClock
from narrator.knowledge import BeliefStore, FactStore, KnowledgeAssembler
from narrator.models import (
    Action,
    ActionResult,
    Character,
    Granularity,
    StateChange,
    StateMode,
    Verdict,
    WorldState,
)
from narrator.models.event import Event
from narrator.orchestrator import EventGenerator, EventPool, GranularityPlanner, NarratorController
from narrator.orchestrator import SpotlightDirector
from narrator.persistence import (
    ActionLogRepository,
    BeliefRepository,
    CheckpointManager,
    CheckpointRepository,
    FactRepository,
    SQLiteDatabase,
    TickAuditRepository,
    WorldSnapshotRepository,
)


class PlannedEventGenerator(EventGenerator):
    def generate(self, world: WorldState, tick: int) -> tuple[Event, ...]:
        target_id = {1: "hero", 2: "guard"}.get(tick)
        if target_id is None:
            return ()
        return (
            Event(
                id=f"alarm-{tick}",
                tick_created=tick,
                soft_prompts=(f"alarm for {target_id}",),
                impact_scope={"location_id": "camp", "target_character_id": target_id},
            ),
        )


class ClosedLoopRuntime:
    def __init__(self) -> None:
        self.context_log: list[tuple[str, int, tuple[str, ...], tuple[str, ...]]] = []

    async def execute(self, character, context, settlement_factory) -> RetryOutcome:
        facts = tuple(entry.entry_id for entry in context.facts)
        clues = tuple(entry.entry_id for entry in context.clues)
        self.context_log.append((character.id, context.tick, facts, clues))
        if character.id == "hero":
            assert "event:alarm-1" in facts
        if character.id == "guard":
            assert "event:alarm-2" in facts
            assert "action:1:hero" in clues
        intent = IntentPayload(
            character_id=character.id,
            action_type="investigate",
            parameters={"focus": "alarm"},
            flavor_text="respond to alarm",
        )
        settlement = settlement_factory(intent)
        event_id = f"alarm-{settlement.tick}"
        return RetryOutcome(
            result=ActionResult(
                action=Action(
                    character_id=character.id,
                    action_type="investigate",
                    parameters={"focus": "alarm"},
                    source_event_id=event_id,
                ),
                verdict=Verdict.APPROVED,
                verdict_reason="approved",
                state_changes=(
                    StateChange(
                        path=f"resources.{character.id}_progress",
                        before=settlement.world.resources.get(f"{character.id}_progress", 0.0),
                        after=settlement.world.resources.get(f"{character.id}_progress", 0.0) + 1.0,
                        reason="close loop action",
                    ),
                    StateChange(
                        path=f"events.{event_id}.resolved",
                        before=False,
                        after=True,
                        reason="resolved by active character",
                    ),
                ),
            ),
            attempts=(),
        )


def build_world() -> WorldState:
    return WorldState(
        tick=0,
        seed=31,
        granularity=Granularity.DAY,
        characters={
            "hero": Character(
                id="hero",
                name="Hero",
                state_mode=StateMode.DORMANT,
                location_id="camp",
                narrative_importance=0.9,
            ),
            "guard": Character(
                id="guard",
                name="Guard",
                state_mode=StateMode.DORMANT,
                location_id="camp",
                narrative_importance=0.6,
            ),
            "sage": Character(
                id="sage",
                name="Sage",
                state_mode=StateMode.DORMANT,
                location_id="tower",
                narrative_importance=0.1,
            ),
        },
        resources={"military_readiness": 10.0},
    )


def build_controller(
    connection,
    world: WorldState,
    runtime: ClosedLoopRuntime,
    rng: random.Random,
    start_tick: int = 0,
):
    return NarratorController(
        world=world,
        clock=GlobalClock(start_tick=start_tick),
        event_pool=EventPool((PlannedEventGenerator(),)),
        granularity_planner=GranularityPlanner(instant_mode_max_rounds=2),
        spotlight=SpotlightDirector(build_spotlight_config()),
        knowledge_assembler=KnowledgeAssembler(FactStore(), BeliefStore()),
        retry_runtime=runtime,
        world_repository=WorldSnapshotRepository(connection),
        action_log_repository=ActionLogRepository(connection),
        checkpoint_manager=CheckpointManager(CheckpointRepository(connection), interval=1),
        fact_repository=FactRepository(connection),
        belief_repository=BeliefRepository(connection),
        tick_audit_repository=TickAuditRepository(connection),
        rng=rng,
    )


def build_spotlight_config() -> SpotlightConfig:
    return SpotlightConfig(
        weights=SpotlightWeights(
            geo=0.4,
            relation=0.4,
            availability=0.1,
            narrative_importance=0.1,
            random_noise=0.0,
        ),
        threshold_active=0.7,
        threshold_passive=0.35,
    )


@pytest.mark.asyncio
async def test_wp13_closed_loop_survives_checkpoint_replay(tmp_path) -> None:
    continuous_db = SQLiteDatabase(tmp_path / "continuous.db")
    replay_db = SQLiteDatabase(tmp_path / "replay.db")
    continuous_db.initialize()
    replay_db.initialize()

    runtime = ClosedLoopRuntime()
    with continuous_db.connect() as connection:
        controller = build_controller(connection, build_world(), runtime, random.Random(31))
        first = await controller.run_tick()
        second = await controller.run_tick()
        checkpoint = CheckpointRepository(connection).load(1)
        tick_audit = TickAuditRepository(connection).load(1)
        facts = FactRepository(connection).list_all()
        beliefs = BeliefRepository(connection).list_for_character("hero")

    replay_rng = random.Random()
    replay_rng.setstate(checkpoint.rng_state)
    with replay_db.connect() as connection:
        replay_controller = build_controller(
            connection,
            checkpoint.world_state,
            ClosedLoopRuntime(),
            replay_rng,
            start_tick=checkpoint.tick,
        )
        replay_second = await replay_controller.run_tick()

    assert first.world.phenology.day_of_year == 1
    assert second.world == replay_second.world
    assert runtime.context_log[0][0:2] == ("hero", 1)
    assert runtime.context_log[1][0:2] == ("guard", 2)
    assert "action:1:hero" in runtime.context_log[1][3]
    assert first.world.pending_propagation[0].task_id.endswith(":guard:2")
    assert [stage["stage"] for stage in tick_audit["stages"]] == [
        "clock",
        "phenology",
        "event_pool",
        "granularity",
        "knowledge_update",
        "spotlight",
        "active_agent",
        "passive_execution",
        "world_rules",
        "persistence",
        "replay_audit",
    ]
    world_rules_stage = tick_audit["stages"][8]
    assert world_rules_stage["stage"] == "world_rules"
    assert world_rules_stage["audit_log"][0].startswith("unresolved_event_pressure:")
    assert facts[0].fact_id == "event:alarm-1"
    assert beliefs[0].belief_id == "action:1:hero"
