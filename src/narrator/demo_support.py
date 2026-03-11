"""Shared builders for the local demo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import Random

from narrator.config import SpotlightConfig, SpotlightWeights
from narrator.core.clock import GlobalClock
from narrator.demo_runtime import DemoEventGenerator, DemoEventPlan, DemoRetryRuntime
from narrator.knowledge import Belief, BeliefStore, Fact, FactStore, FactVisibility, KnowledgeAssembler
from narrator.models import Character, Granularity, StateMode, WorldState
from narrator.orchestrator import EventPool, GranularityPlanner, NarratorController, SpotlightDirector, TickResult
from narrator.persistence import (
    ActionLogRepository,
    BeliefRecord,
    BeliefRepository,
    CheckpointManager,
    CheckpointRepository,
    FactRecord,
    FactRepository,
    SQLiteDatabase,
    TickAuditRepository,
    WorldSnapshotRepository,
)

DEMO_TICKS = 4
CHECKPOINT_INTERVAL = 2


@dataclass(frozen=True)
class DemoSimulationArtifacts:
    results: tuple[TickResult, ...]
    context_traces: tuple[str, ...]
    fact_records: tuple[FactRecord, ...]
    belief_records: tuple[BeliefRecord, ...]
    tick_audits: tuple[dict[str, object], ...]


def build_phenology_world() -> WorldState:
    return WorldState(
        tick=0,
        seed=19,
        granularity=Granularity.DAY,
        characters={
            "marshal": Character(
                id="marshal",
                name="Marshal",
                state_mode=StateMode.PASSIVE,
                location_id="frontier",
                long_action="march",
            )
        },
        resources={
            "military_readiness": 100.0,
            "grain_stock": 120.0,
            "disease_pressure": 0.0,
        },
        flags={"poor_harvest": True},
    )


def build_isolation_assembler() -> KnowledgeAssembler:
    fact_store = FactStore(
        (
            Fact(id="fact-public", tick_created=1, content="钟楼敲了三下。"),
            Fact(
                id="fact-palace",
                tick_created=1,
                content="王宫卫队今晚换防。",
                visibility=FactVisibility(scope="location", location_ids=("palace",)),
            ),
            Fact(
                id="fact-secret",
                tick_created=1,
                content="密道入口在祭坛后。",
                visibility=FactVisibility(scope="private", character_ids=("rival",)),
            ),
        )
    )
    belief_store = BeliefStore(
        (
            Belief(
                character_id="hero",
                belief_id="rumor-secret",
                summary="有人传言祭坛附近藏着不该出现的脚印。",
                acquired_tick=2,
                fact_id="fact-secret",
                confidence=0.4,
                source_type="rumor",
            ),
        )
    )
    return KnowledgeAssembler(fact_store, belief_store)


def build_character(character_id: str, location_id: str) -> Character:
    return Character(
        id=character_id,
        name=character_id.title(),
        state_mode=StateMode.ACTIVE,
        location_id=location_id,
    )


async def run_demo_simulation(db_path: Path) -> DemoSimulationArtifacts:
    database = SQLiteDatabase(db_path)
    database.initialize()
    runtime = DemoRetryRuntime()
    connection = database.connect()
    try:
        controller = build_controller(connection, runtime)
        results = [await controller.run_tick() for _ in range(DEMO_TICKS)]
        return DemoSimulationArtifacts(
            results=tuple(results),
            context_traces=runtime.context_traces,
            fact_records=FactRepository(connection).list_all(),
            belief_records=_belief_records(connection, controller.world),
            tick_audits=_tick_audits(connection, results),
        )
    finally:
        connection.close()


def build_controller(connection, runtime: DemoRetryRuntime) -> NarratorController:
    return NarratorController(
        world=build_demo_world(),
        clock=GlobalClock(start_tick=0),
        event_pool=EventPool(demo_event_generators()),
        granularity_planner=GranularityPlanner(instant_mode_max_rounds=2),
        spotlight=SpotlightDirector(demo_spotlight_config()),
        knowledge_assembler=build_demo_knowledge(),
        retry_runtime=runtime,
        world_repository=WorldSnapshotRepository(connection),
        action_log_repository=ActionLogRepository(connection),
        checkpoint_manager=CheckpointManager(
            CheckpointRepository(connection),
            interval=CHECKPOINT_INTERVAL,
        ),
        fact_repository=FactRepository(connection),
        belief_repository=BeliefRepository(connection),
        tick_audit_repository=TickAuditRepository(connection),
        rng=Random(23),
    )


def build_demo_world() -> WorldState:
    return WorldState(
        tick=0,
        seed=23,
        granularity=Granularity.DAY,
        characters={
            "scout": _character("scout", "Scout", "watchtower", 0.6),
            "captain": _character("captain", "Captain", "watchtower", 0.5),
            "merchant": _character("merchant", "Merchant", "market", 0.45),
            "clerk": _character("clerk", "Clerk", "market", 0.25),
            "hermit": _character("hermit", "Hermit", "ruins", 0.1, "meditate"),
        },
    )


def demo_event_generators() -> tuple[DemoEventGenerator, ...]:
    plans = (
        DemoEventPlan(1, "alarm-1", "watchtower", "scout"),
        DemoEventPlan(2, "alarm-2", "watchtower", "captain"),
        DemoEventPlan(3, "alarm-3", "market", "merchant"),
    )
    return (DemoEventGenerator(plans),)


def demo_spotlight_config() -> SpotlightConfig:
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


def build_demo_knowledge() -> KnowledgeAssembler:
    fact_store = FactStore(
        (
            Fact(id="global-bulletin", tick_created=0, content="港口今天风急。"),
            Fact(
                id="watchtower-order",
                tick_created=0,
                content="watchtower keeps double watch",
                visibility=FactVisibility(scope="location", location_ids=("watchtower",)),
            ),
            Fact(
                id="market-ledger",
                tick_created=0,
                content="merchant owes harbor tax",
                visibility=FactVisibility(scope="private", character_ids=("merchant",)),
            ),
        )
    )
    belief_store = BeliefStore(
        (
            Belief(
                character_id="scout",
                belief_id="watch-rumor",
                summary="北塔楼昨夜似乎看到陌生火光。",
                acquired_tick=0,
                confidence=0.6,
                source_type="rumor",
            ),
        )
    )
    return KnowledgeAssembler(fact_store, belief_store)


def _belief_records(connection, world: WorldState) -> tuple[BeliefRecord, ...]:
    repository = BeliefRepository(connection)
    records = []
    for character_id in sorted(world.characters):
        records.extend(repository.list_for_character(character_id))
    return tuple(records)


def _tick_audits(connection, results: list[TickResult]) -> tuple[dict[str, object], ...]:
    repository = TickAuditRepository(connection)
    return tuple(repository.load(result.tick) for result in results)


def _character(
    character_id: str,
    name: str,
    location_id: str,
    importance: float,
    long_action: str | None = None,
) -> Character:
    return Character(
        id=character_id,
        name=name,
        state_mode=StateMode.DORMANT,
        location_id=location_id,
        narrative_importance=importance,
        long_action=long_action,
    )
