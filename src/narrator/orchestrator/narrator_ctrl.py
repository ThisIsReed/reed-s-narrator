"""Narrator orchestrator main loop."""

from __future__ import annotations

from random import Random
from typing import Protocol

from narrator.agents import RetryOutcome, SettlementContext
from narrator.agents.intent import IntentPayload
from narrator.core.clock import GlobalClock
from narrator.knowledge import CharacterKnowledgeContext, KnowledgeAssembler, KnowledgeMutation
from narrator.models import ActionResult, Character, WorldState
from narrator.persistence import BeliefRecord, FactRecord
from narrator.persistence import (
    ActionLogRepository,
    BeliefRepository,
    CheckpointManager,
    FactRepository,
    WorldSnapshotRepository,
)
from narrator.persistence.tick_audit import TickAuditRepository
from narrator.orchestrator.event_pool import EventPool, EventPoolSnapshot
from narrator.orchestrator.granularity import GranularityDecision, GranularityPlanner
from narrator.orchestrator.tick_helpers import (
    active_audit_entries,
    apply_action_result,
    apply_phenology_stage,
    apply_spotlight_assignments,
    collect_state_changes,
    event_stage,
    granularity_stage,
    knowledge_artifact_ids,
    passive_stage,
    persistence_stage,
    prepare_world,
    replay_audit_stage,
    spotlight_stage,
    stage,
)
from narrator.orchestrator.stages import TickResult, TickStageResult
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
        fact_repository: FactRepository | None = None,
        belief_repository: BeliefRepository | None = None,
        tick_audit_repository: TickAuditRepository | None = None,
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
        self._fact_repository = fact_repository
        self._belief_repository = belief_repository
        self._tick_audit_repository = tick_audit_repository
        self._passive_resolver = passive_resolver or _noop_passive_resolver
        self._rng = rng or Random(world.seed)
        self._instant_rounds = 0
        self._knowledge_assembler.load_world_state(world)
        if self._clock.current_tick() != world.tick:
            raise ValueError("clock tick must match world tick")

    @property
    def world(self) -> WorldState:
        return self._world

    async def run_tick(self) -> TickResult:
        tick = self._clock.advance()
        stages = [stage("clock", audit_log=(f"tick={tick}",))]
        world, phenology_stage = apply_phenology_stage(self._world, tick)
        stages.append(phenology_stage)
        event_snapshot = self._event_pool.generate(world, tick)
        stages.append(event_stage(event_snapshot))
        granularity = self._granularity_planner.decide(
            world.granularity,
            event_snapshot.active_events,
            self._instant_rounds,
        )
        stages.append(granularity_stage(granularity))
        world = prepare_world(world, tick, event_snapshot, granularity)
        self._instant_rounds = granularity.instant_rounds
        world, knowledge_stage = self._apply_knowledge_stage(world, event_snapshot, tick)
        stages.append(knowledge_stage)
        assignments = self._spotlight.assign(world.characters, event_snapshot.active_events, self._rng)
        world = apply_spotlight_assignments(world, assignments, tick)
        stages.append(spotlight_stage(assignments))
        action_results, world, active_stage = await self._run_active_characters(
            world,
            assignments,
            tick,
            granularity,
        )
        stages.append(active_stage)
        world = self._run_passive_characters(world, assignments, tick)
        stages.append(passive_stage(assignments))
        self._world_repository.save(world)
        checkpoint_saved = self._checkpoint_manager.save_if_needed(
            tick,
            world,
            self._rng.getstate(),
        )
        stages.append(persistence_stage(tick, checkpoint_saved))
        stages.append(replay_audit_stage(tick, self._tick_audit_repository is not None))
        self._save_tick_audit(tick, world, action_results, stages)
        self._world = world
        return TickResult(
            tick=tick,
            world=world,
            granularity_reason=granularity.reason,
            event_ids=tuple(event.id for event in event_snapshot.active_events),
            spotlight=assignments,
            action_results=tuple(action_results),
            checkpoint_saved=checkpoint_saved,
            stages=tuple(stages),
        )

    async def _run_active_characters(
        self,
        world: WorldState,
        assignments: SpotlightAssignments,
        tick: int,
        granularity: GranularityDecision,
    ) -> tuple[list[ActionResult], WorldState, TickStageResult]:
        results: list[ActionResult] = []
        audit_log: list[str] = []
        for character_id in assignments.active_ids:
            character = world.characters[character_id]
            context = self._knowledge_assembler.build_context(character, tick)
            outcome = await self._retry_runtime.execute(
                character,
                context,
                _settlement_factory(world, character, tick, granularity.reason),
            )
            self._action_log_repository.save(tick, outcome.result)
            world = apply_action_result(world, outcome.result)
            world, mutation = self._knowledge_assembler.capture_action(world, outcome.result, tick)
            self._persist_knowledge_mutation(tick, mutation)
            results.append(outcome.result)
            audit_log.extend(active_audit_entries(character_id, context, outcome.result, mutation))
        return results, world, stage(
            "active_agent",
            audit_log=tuple(audit_log),
            state_changes=collect_state_changes(results),
            artifact_ids=assignments.active_ids,
        )

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

    def _apply_knowledge_stage(
        self,
        world: WorldState,
        event_snapshot: EventPoolSnapshot,
        tick: int,
    ) -> tuple[WorldState, TickStageResult]:
        world, event_mutation = self._knowledge_assembler.ingest_events(
            world,
            event_snapshot.new_events,
            tick,
        )
        world, diffusion_mutation = self._knowledge_assembler.execute_pending(world, tick)
        self._persist_knowledge_mutation(tick, event_mutation)
        self._persist_knowledge_mutation(tick, diffusion_mutation)
        return world, stage(
            "knowledge_update",
            audit_log=(*event_mutation.audit_log, *diffusion_mutation.audit_log),
            artifact_ids=knowledge_artifact_ids(event_mutation, diffusion_mutation, world),
        )

    def _persist_knowledge_mutation(self, tick: int, mutation: KnowledgeMutation) -> None:
        if self._fact_repository is not None:
            for fact in mutation.facts:
                self._fact_repository.save(
                    FactRecord(
                        fact_id=fact.id,
                        tick=tick,
                        payload=fact.model_dump(mode="json"),
                    )
                )
        if self._belief_repository is None:
            return
        for belief in mutation.beliefs:
            self._belief_repository.save(
                BeliefRecord(
                    character_id=belief.character_id,
                    belief_id=belief.belief_id,
                    tick=tick,
                    payload=belief.model_dump(mode="json"),
                )
            )

    def _save_tick_audit(
        self,
        tick: int,
        world: WorldState,
        action_results: list[ActionResult],
        stages: list[TickStageResult],
    ) -> None:
        if self._tick_audit_repository is None:
            return
        payload = {
            "tick": tick,
            "event_ids": sorted(world.events),
            "action_character_ids": [item.action.character_id for item in action_results],
            "pending_propagation": [task.task_id for task in world.pending_propagation],
            "stages": [stage.model_dump(mode="json") for stage in stages],
        }
        self._tick_audit_repository.save(tick, payload)


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


def _noop_passive_resolver(world: WorldState, character: Character, tick: int) -> WorldState:
    return world
