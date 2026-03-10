"""Narrator orchestrator main loop."""

from __future__ import annotations

from random import Random
from typing import Protocol

from narrator.agents import RetryOutcome, SettlementContext
from narrator.agents.intent import IntentPayload
from narrator.core.clock import GlobalClock
from narrator.knowledge import CharacterKnowledgeContext, KnowledgeAssembler
from narrator.models import ActionResult, Character, Event, WorldState
from narrator.models.base import DomainModel
from narrator.persistence import (
    ActionLogRepository,
    CheckpointManager,
    WorldSnapshotRepository,
)

from narrator.orchestrator.event_pool import EventPool, EventPoolSnapshot
from narrator.orchestrator.granularity import GranularityDecision, GranularityPlanner
from narrator.orchestrator.spotlight import SpotlightAssignments, SpotlightDirector


class RetryRuntime(Protocol):
    async def execute(
        self,
        character: Character,
        context: CharacterKnowledgeContext,
        settlement_factory,
    ) -> RetryOutcome: ...


class PassiveResolver(Protocol):
    def __call__(self, world: WorldState, character: Character, tick: int) -> WorldState: ...


class TickResult(DomainModel):
    tick: int
    world: WorldState
    granularity_reason: str
    event_ids: tuple[str, ...] = ()
    spotlight: SpotlightAssignments
    action_results: tuple[ActionResult, ...] = ()
    checkpoint_saved: bool


class NarratorController:
    def __init__(
        self,
        world: WorldState,
        clock: GlobalClock,
        event_pool: EventPool,
        granularity_planner: GranularityPlanner,
        spotlight: SpotlightDirector,
        knowledge_assembler: KnowledgeAssembler,
        retry_runtime: RetryRuntime,
        world_repository: WorldSnapshotRepository,
        action_log_repository: ActionLogRepository,
        checkpoint_manager: CheckpointManager,
        passive_resolver: PassiveResolver | None = None,
        rng: Random | None = None,
    ) -> None:
        self._world = world
        self._clock = clock
        self._event_pool = event_pool
        self._granularity_planner = granularity_planner
        self._spotlight = spotlight
        self._knowledge_assembler = knowledge_assembler
        self._retry_runtime = retry_runtime
        self._world_repository = world_repository
        self._action_log_repository = action_log_repository
        self._checkpoint_manager = checkpoint_manager
        self._passive_resolver = passive_resolver or _noop_passive_resolver
        self._rng = rng or Random(world.seed)
        self._instant_rounds = 0
        if self._clock.current_tick() != world.tick:
            raise ValueError("clock tick must match world tick")

    @property
    def world(self) -> WorldState:
        return self._world

    async def run_tick(self) -> TickResult:
        tick = self._clock.advance()
        event_snapshot = self._event_pool.generate(self._world, tick)
        granularity = self._granularity_planner.decide(
            self._world.granularity,
            event_snapshot.active_events,
            self._instant_rounds,
        )
        world = _prepare_world(self._world, tick, event_snapshot, granularity)
        self._instant_rounds = granularity.instant_rounds
        assignments = self._spotlight.assign(world.characters, event_snapshot.active_events, self._rng)
        world = _apply_spotlight_assignments(world, assignments, tick)
        action_results, world = await self._run_active_characters(world, assignments, tick, granularity)
        world = self._run_passive_characters(world, assignments, tick)
        self._world_repository.save(world)
        checkpoint_saved = self._checkpoint_manager.save_if_needed(
            tick,
            world,
            self._rng.getstate(),
        )
        self._world = world
        return TickResult(
            tick=tick,
            world=world,
            granularity_reason=granularity.reason,
            event_ids=tuple(event.id for event in event_snapshot.active_events),
            spotlight=assignments,
            action_results=tuple(action_results),
            checkpoint_saved=checkpoint_saved,
        )

    async def _run_active_characters(
        self,
        world: WorldState,
        assignments: SpotlightAssignments,
        tick: int,
        granularity: GranularityDecision,
    ) -> tuple[list[ActionResult], WorldState]:
        results: list[ActionResult] = []
        for character_id in assignments.active_ids:
            character = world.characters[character_id]
            context = self._knowledge_assembler.build_context(character, tick)
            outcome = await self._retry_runtime.execute(
                character,
                context,
                _settlement_factory(world, character, tick, granularity.reason),
            )
            self._action_log_repository.save(tick, outcome.result)
            world = _apply_action_result(world, outcome.result)
            results.append(outcome.result)
        return results, world

    def _run_passive_characters(
        self,
        world: WorldState,
        assignments: SpotlightAssignments,
        tick: int,
    ) -> WorldState:
        updated = world
        for character_id in assignments.passive_ids:
            updated = self._passive_resolver(updated, updated.characters[character_id], tick)
        return updated


def _noop_passive_resolver(world: WorldState, character: Character, tick: int) -> WorldState:
    return world


def _prepare_world(
    world: WorldState,
    tick: int,
    event_snapshot: EventPoolSnapshot,
    granularity: GranularityDecision,
) -> WorldState:
    merged_events = dict(world.events)
    for event in event_snapshot.new_events:
        merged_events[event.id] = event
    return world.model_copy(
        update={
            "tick": tick,
            "granularity": granularity.granularity,
            "events": merged_events,
        }
    )


def _apply_spotlight_assignments(
    world: WorldState,
    assignments: SpotlightAssignments,
    tick: int,
) -> WorldState:
    modes = {entry.character_id: entry.state_mode for entry in assignments.entries}
    characters = {
        character_id: _update_character_state(character, modes[character_id], tick)
        for character_id, character in world.characters.items()
    }
    return world.model_copy(update={"characters": characters})


def _update_character_state(character: Character, mode, tick: int) -> Character:
    updates = {"state_mode": mode}
    if mode.value == "ACTIVE":
        updates["last_active_tick"] = tick
    return character.model_copy(update=updates)


def _settlement_factory(
    world: WorldState,
    character: Character,
    tick: int,
    reason: str,
):
    def factory(intent: IntentPayload) -> SettlementContext:
        return SettlementContext(
            tick=tick,
            character=character,
            intent=intent,
            world=world,
            rule_summary=(reason,),
            rng_seed=world.seed,
        )

    return factory


def _apply_action_result(world: WorldState, result: ActionResult) -> WorldState:
    if not result.state_changes:
        return world
    payload = world.model_dump(mode="json")
    for change in result.state_changes:
        _assign_path(payload, change.path.split("."), change.after)
    return WorldState.model_validate(payload)


def _assign_path(payload: dict[str, object], path_parts: list[str], value: object) -> None:
    if not path_parts:
        raise ValueError("state change path must not be empty")
    current: dict[str, object] = payload
    for part in path_parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            raise KeyError(f"state change path not found: {'.'.join(path_parts)}")
        current = next_value
    current[path_parts[-1]] = value
