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
    LongActionState,
    LongActionStatus,
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
    CheckpointManager,
    CheckpointRepository,
    SQLiteDatabase,
    TickAuditRepository,
    WorldSnapshotRepository,
)


class OneShotInterruptEventGenerator(EventGenerator):
    def generate(self, world: WorldState, tick: int) -> tuple[Event, ...]:
        if tick != 1:
            return ()
        return (
            Event(
                id="alarm-1",
                tick_created=1,
                impact_scope={"location_id": "camp", "target_character_id": "hero"},
                soft_prompts=("alarm",),
            ),
        )


class ResolveEventRuntime:
    async def execute(self, character, context, settlement_factory) -> RetryOutcome:
        intent = IntentPayload(
            character_id=character.id,
            action_type="investigate",
            parameters={"focus": "alarm"},
            flavor_text="respond",
        )
        settlement = settlement_factory(intent)
        return RetryOutcome(
            result=ActionResult(
                action=Action(
                    character_id=character.id,
                    action_type="investigate",
                    parameters={"focus": "alarm"},
                    source_event_id="alarm-1",
                ),
                verdict=Verdict.APPROVED,
                verdict_reason="approved",
                state_changes=(
                    StateChange(
                        path="events.alarm-1.resolved",
                        before=False,
                        after=True,
                        reason="resolved by interrupt response",
                    ),
                ),
            ),
            attempts=(),
        )


def _build_world() -> WorldState:
    return WorldState(
        tick=0,
        seed=41,
        granularity=Granularity.DAY,
        characters={
            "hero": Character(
                id="hero",
                name="Hero",
                state_mode=StateMode.DORMANT,
                location_id="camp",
                narrative_importance=0.1,
                long_action=LongActionState(
                    action_type="march",
                    started_tick=0,
                    remaining_ticks=3,
                ),
            )
        },
    )


def _build_controller(connection, world: WorldState, rng: random.Random, start_tick: int = 0):
    return NarratorController(
        world=world,
        clock=GlobalClock(start_tick=start_tick),
        event_pool=EventPool((OneShotInterruptEventGenerator(),)),
        granularity_planner=GranularityPlanner(instant_mode_max_rounds=1),
        spotlight=SpotlightDirector(_spotlight_config()),
        knowledge_assembler=KnowledgeAssembler(FactStore(), BeliefStore()),
        retry_runtime=ResolveEventRuntime(),
        world_repository=WorldSnapshotRepository(connection),
        action_log_repository=ActionLogRepository(connection),
        checkpoint_manager=CheckpointManager(CheckpointRepository(connection), interval=1),
        tick_audit_repository=TickAuditRepository(connection),
        rng=rng,
    )


def _spotlight_config() -> SpotlightConfig:
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
async def test_wp15_interrupts_long_action_and_replay_restores_consistently(tmp_path) -> None:
    continuous_db = SQLiteDatabase(tmp_path / "continuous.db")
    replay_db = SQLiteDatabase(tmp_path / "replay.db")
    continuous_db.initialize()
    replay_db.initialize()

    with continuous_db.connect() as connection:
        controller = _build_controller(connection, _build_world(), random.Random(41))
        first = await controller.run_tick()
        second = await controller.run_tick()
        checkpoint = CheckpointRepository(connection).load(1)
        tick_one_audit = TickAuditRepository(connection).load(1)
        tick_two_audit = TickAuditRepository(connection).load(2)

    replay_rng = random.Random()
    replay_rng.setstate(checkpoint.rng_state)
    with replay_db.connect() as connection:
        replay_controller = _build_controller(
            connection,
            checkpoint.world_state,
            replay_rng,
            start_tick=checkpoint.tick,
        )
        replay_second = await replay_controller.run_tick()

    assert first.world.characters["hero"].long_action is not None
    assert first.world.characters["hero"].long_action.status is LongActionStatus.PAUSED
    assert first.world.characters["hero"].long_action.interrupt_history[0].event_id == "alarm-1"
    assert second.world.characters["hero"].long_action is not None
    assert second.world.characters["hero"].long_action.status is LongActionStatus.IN_PROGRESS
    assert second.world.characters["hero"].long_action.remaining_ticks == 2
    assert replay_second.world == second.world
    assert [stage["stage"] for stage in tick_one_audit["stages"]] == [
        "clock",
        "phenology",
        "event_pool",
        "granularity",
        "interrupt_scan",
        "knowledge_update",
        "spotlight",
        "active_agent",
        "passive_execution",
        "world_rules",
        "persistence",
        "replay_audit",
    ]
    assert tick_one_audit["stages"][4]["audit_log"] == ["hero:targeted_event_interrupt:alarm-1"]
    assert tick_one_audit["stages"][9]["audit_log"][0] == "long_action_interrupt:matched:1"
    assert tick_two_audit["stages"][4]["audit_log"] == ["signals=-"]
    assert tick_two_audit["stages"][9]["audit_log"][1:3] == [
        "long_action_resume:matched:1",
        "long_action_progress:matched:1",
    ]
