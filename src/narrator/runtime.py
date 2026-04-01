"""Formal runtime assembly for the CLI MVP."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from random import Random

from narrator.agents import RetryOutcome
from narrator.agents.intent import IntentPayload
from narrator.config import AppConfig, SpotlightConfig
from narrator.core.clock import GlobalClock
from narrator.knowledge import Belief, BeliefStore, Fact, FactStore, FactVisibility, KnowledgeAssembler
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
from narrator.orchestrator import EventGenerator, EventPool, GranularityPlanner, NarratorController, SpotlightDirector
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

DEFAULT_WORLD_SEED = 101
# Keep the runtime seed fixed so CLI output remains deterministic across runs and replay tests.
DEFAULT_EVENT_INTERVAL = 1
DEFAULT_LOCATION_FACT_SCOPE = "location"
DEFAULT_PRIVATE_FACT_SCOPE = "private"


@dataclass(frozen=True)
class RuntimeCharacterSpec:
    character_id: str
    name: str
    location_id: str
    importance: float


@dataclass(frozen=True)
class RunArtifacts:
    db_path: Path
    max_ticks: int
    checkpoint_interval: int
    results: tuple[object, ...]
    checkpoint_ticks: tuple[int, ...]
    snapshot_ticks: tuple[int, ...]


RUNTIME_CHARACTERS = (
    RuntimeCharacterSpec("warden", "Warden", "gate", 0.9),
    RuntimeCharacterSpec("scribe", "Scribe", "archive", 0.7),
    RuntimeCharacterSpec("trader", "Trader", "market", 0.6),
    RuntimeCharacterSpec("courier", "Courier", "gate", 0.5),
)


class RuntimeEventGenerator(EventGenerator):
    def __init__(self, interval: int = DEFAULT_EVENT_INTERVAL) -> None:
        if interval <= 0:
            raise ValueError("event interval must be greater than 0")
        self._interval = interval

    def generate(self, world: WorldState, tick: int) -> tuple[Event, ...]:
        if tick % self._interval != 0:
            return ()
        target = _target_character_spec(tick)
        event_id = f"incident-{tick}"
        return (
            Event(
                id=event_id,
                tick_created=tick,
                tags=("granularity:instant",),
                impact_scope={
                    "location_id": target.location_id,
                    "target_character_id": target.character_id,
                },
                soft_prompts=(f"{target.name} must respond to {event_id}",),
            ),
        )


class DeterministicRetryRuntime:
    async def execute(self, character, context, settlement_factory) -> RetryOutcome:
        settlement = settlement_factory(_build_intent(character.id))
        event_id = _current_event_id(settlement.world, character.id)
        action_key = f"{character.id}_activity"
        current_value = settlement.world.resources.get(action_key, 0.0)
        state_changes = [
            StateChange(
                path=f"resources.{action_key}",
                before=current_value,
                after=current_value + 1.0,
                reason="record runtime activity",
            )
        ]
        parameters = {"focus": "routine"}
        if event_id is not None:
            state_changes.append(
                StateChange(
                    path=f"events.{event_id}.resolved",
                    before=False,
                    after=True,
                    reason="resolve runtime incident",
                )
            )
            parameters = {"event_id": event_id}
        return RetryOutcome(
            result=ActionResult(
                action=Action(
                    character_id=character.id,
                    action_type="respond",
                    parameters=parameters,
                    source_event_id=event_id,
                ),
                verdict=Verdict.APPROVED,
                verdict_reason="deterministic runtime approved",
                state_changes=tuple(state_changes),
                flavor_text=_flavor_text(character.id, event_id),
            ),
            attempts=(),
        )


def build_runtime_world(seed: int = DEFAULT_WORLD_SEED) -> WorldState:
    characters = {
        spec.character_id: Character(
            id=spec.character_id,
            name=spec.name,
            state_mode=StateMode.DORMANT,
            location_id=spec.location_id,
            narrative_importance=spec.importance,
        )
        for spec in RUNTIME_CHARACTERS
    }
    return WorldState(
        tick=0,
        seed=seed,
        granularity=Granularity.DAY,
        characters=characters,
        resources={
            "order": 100.0,
            "morale": 80.0,
        },
        flags={"runtime_bootstrap": True},
    )


def build_runtime_knowledge() -> KnowledgeAssembler:
    fact_store = FactStore(
        (
            Fact(id="public-notice", tick_created=0, content="城内公告要求维持夜间巡逻。"),
            Fact(
                id="gate-order",
                tick_created=0,
                content="城门在黄昏前后加强盘查。",
                visibility=FactVisibility(
                    scope=DEFAULT_LOCATION_FACT_SCOPE,
                    location_ids=("gate",),
                ),
            ),
            Fact(
                id="scribe-note",
                tick_created=0,
                content="档案室缺一份旧税册。",
                visibility=FactVisibility(
                    scope=DEFAULT_PRIVATE_FACT_SCOPE,
                    character_ids=("scribe",),
                ),
            ),
        )
    )
    belief_store = BeliefStore(
        (
            Belief(
                character_id="warden",
                belief_id="watch-rumor",
                summary="城门附近最近多了几名陌生访客。",
                acquired_tick=0,
                confidence=0.6,
                source_type="rumor",
            ),
        )
    )
    return KnowledgeAssembler(fact_store, belief_store)


def build_runtime_controller(
    connection,
    app_config: AppConfig,
    checkpoint_interval: int,
) -> NarratorController:
    return NarratorController(
        world=build_runtime_world(),
        clock=GlobalClock(start_tick=0),
        event_pool=EventPool((RuntimeEventGenerator(),)),
        granularity_planner=GranularityPlanner(
            instant_mode_max_rounds=app_config.narrator.instant_mode_max_rounds
        ),
        spotlight=SpotlightDirector(_spotlight_config(app_config)),
        knowledge_assembler=build_runtime_knowledge(),
        retry_runtime=DeterministicRetryRuntime(),
        world_repository=WorldSnapshotRepository(connection),
        action_log_repository=ActionLogRepository(connection),
        checkpoint_manager=CheckpointManager(
            CheckpointRepository(connection),
            interval=checkpoint_interval,
        ),
        fact_repository=FactRepository(connection),
        belief_repository=BeliefRepository(connection),
        tick_audit_repository=TickAuditRepository(connection),
        rng=Random(DEFAULT_WORLD_SEED),
    )


async def run_simulation(
    db_path: Path,
    app_config: AppConfig,
    max_ticks: int,
    checkpoint_interval: int,
) -> RunArtifacts:
    database = SQLiteDatabase(db_path)
    database.initialize()
    connection = database.connect()
    try:
        _ensure_runtime_db_is_empty(connection)
        controller = build_runtime_controller(connection, app_config, checkpoint_interval)
        results = []
        for _ in range(max_ticks):
            results.append(await controller.run_tick())
        checkpoints = CheckpointRepository(connection).list_ticks()
        snapshots = WorldSnapshotRepository(connection).list_ticks()
    finally:
        connection.close()
    return RunArtifacts(
        db_path=db_path,
        max_ticks=max_ticks,
        checkpoint_interval=checkpoint_interval,
        results=tuple(results),
        checkpoint_ticks=checkpoints,
        snapshot_ticks=snapshots,
    )


def run_simulation_sync(
    db_path: Path,
    app_config: AppConfig,
    max_ticks: int,
    checkpoint_interval: int,
) -> RunArtifacts:
    return asyncio.run(run_simulation(db_path, app_config, max_ticks, checkpoint_interval))


def _ensure_runtime_db_is_empty(connection) -> None:
    snapshot_ticks = WorldSnapshotRepository(connection).list_ticks()
    checkpoint_ticks = CheckpointRepository(connection).list_ticks()
    if snapshot_ticks or checkpoint_ticks:
        raise RuntimeError("runtime database already contains replay data; use a new --db path")


def _spotlight_config(app_config: AppConfig) -> SpotlightConfig:
    return app_config.spotlight


def _target_character_spec(tick: int) -> RuntimeCharacterSpec:
    index = (tick - 1) % len(RUNTIME_CHARACTERS)
    return RUNTIME_CHARACTERS[index]


def _build_intent(character_id: str) -> IntentPayload:
    return IntentPayload(
        character_id=character_id,
        action_type="respond",
        parameters={},
        flavor_text="处理当前线索",
    )


def _current_event_id(world: WorldState, character_id: str) -> str | None:
    for event_id, event in sorted(world.events.items()):
        if event.resolved:
            continue
        target_character_id = event.impact_scope.get("target_character_id")
        if target_character_id == character_id:
            return event_id
    return None


def _flavor_text(character_id: str, event_id: str | None) -> str:
    if event_id is None:
        return f"{character_id} 完成了例行响应。"
    return f"{character_id} 处理了 {event_id}。"
