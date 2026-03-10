"""Shared demo builders and deterministic runtime pieces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import Random

from narrator.agents import RetryOutcome
from narrator.agents.intent import IntentPayload
from narrator.config import SpotlightConfig, SpotlightWeights
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
from narrator.orchestrator import (
    EventGenerator,
    EventPool,
    GranularityPlanner,
    NarratorController,
    SpotlightDirector,
    TickResult,
)
from narrator.persistence import ActionLogRepository, CheckpointManager, CheckpointRepository
from narrator.persistence import SQLiteDatabase, WorldSnapshotRepository

DEMO_TICKS = 3
CHECKPOINT_INTERVAL = 2

@dataclass(frozen=True)
class DemoEventPlan:
    tick: int
    event_id: str
    location_id: str
    target_character_id: str


@dataclass(frozen=True)
class DemoSimulationArtifacts:
    results: tuple[TickResult, ...]
    context_traces: tuple[str, ...]

class DemoEventGenerator(EventGenerator):
    def __init__(self, plans: tuple[DemoEventPlan, ...]) -> None:
        self._plans = {plan.tick: plan for plan in plans}

    def generate(self, world: WorldState, tick: int) -> tuple[Event, ...]:
        plan = self._plans.get(tick)
        if plan is None:
            return ()
        return (_build_demo_event(plan),)

class DemoRetryRuntime:
    def __init__(self) -> None:
        self._context_traces: list[str] = []

    @property
    def context_traces(self) -> tuple[str, ...]:
        return tuple(self._context_traces)

    async def execute(self, character, context, settlement_factory) -> RetryOutcome:
        self._context_traces.append(format_context_trace(character.id, context))
        intent = IntentPayload(
            character_id=character.id,
            action_type="investigate",
            parameters={"focus": "active_event"},
            flavor_text=f"{character.name} responds to the alarm.",
        )
        settlement = settlement_factory(intent)
        event_id = active_event_id(settlement.world, character.id)
        result = build_action_result(settlement.world, character.id, event_id)
        return RetryOutcome(result=result, attempts=())


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
    with database.connect() as connection:
        controller = build_controller(connection, runtime)
        results = []
        for _ in range(DEMO_TICKS):
            results.append(await controller.run_tick())
    return DemoSimulationArtifacts(
        results=tuple(results),
        context_traces=runtime.context_traces,
    )


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
        rng=Random(23),
    )


def build_demo_world() -> WorldState:
    characters = {
        "scout": Character(
            id="scout",
            name="Scout",
            state_mode=StateMode.DORMANT,
            location_id="watchtower",
            narrative_importance=0.6,
        ),
        "captain": Character(
            id="captain",
            name="Captain",
            state_mode=StateMode.DORMANT,
            location_id="watchtower",
            narrative_importance=0.5,
        ),
        "merchant": Character(
            id="merchant",
            name="Merchant",
            state_mode=StateMode.DORMANT,
            location_id="market",
            narrative_importance=0.4,
        ),
        "hermit": Character(
            id="hermit",
            name="Hermit",
            state_mode=StateMode.DORMANT,
            location_id="ruins",
            narrative_importance=0.1,
            long_action="meditate",
        ),
    }
    return WorldState(tick=0, seed=23, granularity=Granularity.DAY, characters=characters)


def demo_event_generators() -> tuple[EventGenerator, ...]:
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


def format_context_trace(character_id: str, context) -> str:
    facts = ",".join(entry.entry_id for entry in context.facts) or "-"
    clues = ",".join(entry.entry_id for entry in context.clues) or "-"
    return f"{character_id}: facts={facts} clues={clues}"


def active_event_id(world: WorldState, character_id: str) -> str | None:
    active_events = []
    for event in world.events.values():
        if event.resolved:
            continue
        target_id = event.impact_scope.get("target_character_id")
        if target_id == character_id:
            active_events.append(event)
    if not active_events:
        return None
    ordered = sorted(active_events, key=lambda item: (item.tick_created, item.id))
    return ordered[-1].id


def build_action_result(
    world: WorldState,
    character_id: str,
    event_id: str | None,
) -> ActionResult:
    action_key = f"{character_id}_actions"
    before = world.resources.get(action_key, 0.0)
    changes = [
        StateChange(
            path=f"resources.{action_key}",
            before=before,
            after=before + 1.0,
            reason="demo action executed",
        )
    ]
    if event_id is not None:
        changes.append(_resolved_change(event_id))
    return ActionResult(
        action=Action(character_id=character_id, action_type="investigate", parameters={}),
        verdict=Verdict.APPROVED,
        verdict_reason="demo approved",
        state_changes=tuple(changes),
        flavor_text="demo action completed",
    )


def _build_demo_event(plan: DemoEventPlan) -> Event:
    return Event(
        id=plan.event_id,
        tick_created=plan.tick,
        tags=("granularity:instant",),
        impact_scope={
            "location_id": plan.location_id,
            "target_character_id": plan.target_character_id,
        },
        soft_prompts=(f"demo event for {plan.target_character_id}",),
    )


def _resolved_change(event_id: str) -> StateChange:
    return StateChange(
        path=f"events.{event_id}.resolved",
        before=False,
        after=True,
        reason="demo event resolved",
    )
