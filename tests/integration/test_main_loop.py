from __future__ import annotations

import random

import pytest

from narrator.agents import RetryOutcome
from narrator.agents.intent import IntentPayload
from narrator.core.clock import GlobalClock
from narrator.knowledge import BeliefStore, FactStore, KnowledgeAssembler
from narrator.models import Character, Granularity, StateMode, WorldState
from narrator.models import Action, ActionResult, Event, StateChange, Verdict
from narrator.orchestrator import (
    EventGenerator,
    EventPool,
    GranularityPlanner,
    NarratorController,
    SpotlightDirector,
)
from narrator.persistence import CheckpointManager, CheckpointRepository, SQLiteDatabase
from narrator.persistence import ActionLogRepository, WorldSnapshotRepository
from narrator.config import SpotlightConfig, SpotlightWeights


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


class SingleEventGenerator(EventGenerator):
    def __init__(self, trace: list[str]) -> None:
        self._trace = trace

    def generate(self, world: WorldState, tick: int) -> tuple[Event, ...]:
        self._trace.append("event_pool")
        return (
            Event(
                id=f"alarm-{tick}",
                tick_created=tick,
                tags=("granularity:instant",),
                impact_scope={"location_id": "town", "target_character_id": "hero"},
            ),
        )


class RecordingRetryRuntime:
    def __init__(self, trace: list[str]) -> None:
        self._trace = trace

    async def execute(self, character, context, settlement_factory) -> RetryOutcome:
        settlement = settlement_factory(_build_intent(character.id))
        assert "alarm-1" in settlement.world.events
        self._trace.append(f"active:{character.id}")
        return RetryOutcome(
            result=ActionResult(
                action=Action(
                    character_id=character.id,
                    action_type="move",
                    parameters={"destination": "gate"},
                ),
                verdict=Verdict.APPROVED,
                verdict_reason="approved",
                state_changes=(
                    StateChange(
                        path="resources.hero_progress",
                        before=None,
                        after=1.0,
                        reason="hero advanced",
                    ),
                ),
                flavor_text="advance",
            ),
            attempts=(),
        )


@pytest.mark.asyncio
async def test_narrator_controller_runs_main_loop_in_order(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "narrator.db")
    database.initialize()
    trace: list[str] = []
    world = WorldState(
        tick=0,
        seed=11,
        granularity=Granularity.DAY,
        characters={
            "hero": Character(
                id="hero",
                name="Hero",
                state_mode=StateMode.DORMANT,
                location_id="town",
                narrative_importance=0.9,
            ),
            "guard": Character(
                id="guard",
                name="Guard",
                state_mode=StateMode.DORMANT,
                location_id="town",
                narrative_importance=0.2,
            ),
            "sleeper": Character(
                id="sleeper",
                name="Sleeper",
                state_mode=StateMode.DORMANT,
                location_id="cave",
                narrative_importance=0.0,
                long_action="sleep",
            ),
        },
    )
    spotlight = SpotlightDirector(_build_spotlight_config())
    event_pool = EventPool((SingleEventGenerator(trace),))
    knowledge = KnowledgeAssembler(FactStore(), BeliefStore())
    retry_runtime = RecordingRetryRuntime(trace)

    with database.connect() as connection:
        controller = NarratorController(
            world=world,
            clock=GlobalClock(start_tick=0),
            event_pool=event_pool,
            granularity_planner=GranularityPlanner(instant_mode_max_rounds=2),
            spotlight=spotlight,
            knowledge_assembler=knowledge,
            retry_runtime=retry_runtime,
            world_repository=WorldSnapshotRepository(connection),
            action_log_repository=ActionLogRepository(connection),
            checkpoint_manager=CheckpointManager(CheckpointRepository(connection), interval=1),
            passive_resolver=lambda current, character, tick: _apply_passive_update(
                current,
                character.id,
                tick,
                trace,
            ),
            rng=random.Random(7),
        )

        result = await controller.run_tick()
        stored_actions = ActionLogRepository(connection).list_by_tick(1)
        stored_world = WorldSnapshotRepository(connection).get(1)

    assert trace == ["event_pool", "active:hero", "passive:guard"]
    assert result.tick == 1
    assert result.world.granularity is Granularity.INSTANT
    assert result.spotlight.active_ids == ("hero",)
    assert result.spotlight.passive_ids == ("guard",)
    assert result.spotlight.dormant_ids == ("sleeper",)
    assert result.checkpoint_saved is True
    assert stored_actions == result.action_results
    assert stored_world == result.world
    assert result.world.resources == {"hero_progress": 1.0, "guard_patrol": 1.0}


def _build_spotlight_config() -> SpotlightConfig:
    return SpotlightConfig(
        weights=SpotlightWeights(
            geo=0.25,
            relation=0.25,
            availability=0.2,
            narrative_importance=0.2,
            random_noise=0.1,
        ),
        threshold_active=0.7,
        threshold_passive=0.4,
    )


def _build_intent(character_id: str) -> IntentPayload:
    return IntentPayload(
        character_id=character_id,
        action_type="move",
        parameters={"destination": "gate"},
        flavor_text="advance",
    )


def _apply_passive_update(
    world: WorldState,
    character_id: str,
    tick: int,
    trace: list[str],
) -> WorldState:
    trace.append(f"passive:{character_id}")
    assert world.resources["hero_progress"] == 1.0
    resources = dict(world.resources)
    resources["guard_patrol"] = float(tick)
    return world.model_copy(update={"resources": resources})
