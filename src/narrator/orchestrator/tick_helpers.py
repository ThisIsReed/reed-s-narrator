"""Helpers for orchestrator tick assembly."""

from __future__ import annotations

from narrator.core import RuleContext, RuleEngine, RuleExecutionRecord
from narrator.knowledge import CharacterKnowledgeContext, KnowledgeMutation
from narrator.models import ActionResult, Character, StateChange, WorldState
from narrator.orchestrator.event_pool import EventPoolSnapshot
from narrator.orchestrator.granularity import GranularityDecision
from narrator.orchestrator.stages import TickStageResult
from narrator.orchestrator.spotlight import SpotlightAssignments
from narrator.phenology import apply_phenology


def apply_phenology_stage(world: WorldState, tick: int) -> tuple[WorldState, TickStageResult]:
    result = apply_phenology(world, tick)
    return result.world, stage(
        "phenology",
        audit_log=tuple(phenology_audit_entries(result.audit_log)),
        state_changes=result.state_changes,
    )


def prepare_world(
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


def apply_spotlight_assignments(
    world: WorldState,
    assignments: SpotlightAssignments,
    tick: int,
) -> WorldState:
    modes = {entry.character_id: entry.state_mode for entry in assignments.entries}
    characters = {
        character_id: update_character_state(character, modes[character_id], tick)
        for character_id, character in world.characters.items()
    }
    return world.model_copy(update={"characters": characters})


def update_character_state(character: Character, mode, tick: int) -> Character:
    updates = {"state_mode": mode}
    if mode.value == "ACTIVE":
        updates["last_active_tick"] = tick
    return character.model_copy(update=updates)


def apply_action_result(world: WorldState, result: ActionResult) -> WorldState:
    return apply_state_changes(world, result.state_changes)


def apply_state_changes(world: WorldState, state_changes: tuple[StateChange, ...]) -> WorldState:
    if not state_changes:
        return world
    payload = world.model_dump(mode="json")
    for change in state_changes:
        assign_path(payload, change.path.split("."), change.after)
    return WorldState.model_validate(payload)


def assign_path(payload: dict[str, object], path_parts: list[str], value: object) -> None:
    if not path_parts:
        raise ValueError("state change path must not be empty")
    current: dict[str, object] = payload
    for part in path_parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            raise KeyError(f"state change path not found: {'.'.join(path_parts)}")
        current = next_value
    current[path_parts[-1]] = value


def stage(
    name: str,
    audit_log: tuple[str, ...] = (),
    state_changes: tuple[StateChange, ...] = (),
    artifact_ids: tuple[str, ...] = (),
) -> TickStageResult:
    return TickStageResult(
        stage=name,
        audit_log=audit_log,
        state_changes=state_changes,
        artifact_ids=artifact_ids,
    )


def event_stage(event_snapshot: EventPoolSnapshot) -> TickStageResult:
    event_ids = tuple(event.id for event in event_snapshot.active_events)
    return stage(
        "event_pool",
        audit_log=(f"events={','.join(event_ids) or '-'}",),
        artifact_ids=event_ids,
    )


def granularity_stage(granularity: GranularityDecision) -> TickStageResult:
    return stage(
        "granularity",
        audit_log=(f"granularity={granularity.granularity.value}", f"reason={granularity.reason}"),
    )


def spotlight_stage(assignments: SpotlightAssignments) -> TickStageResult:
    return stage(
        "spotlight",
        audit_log=tuple(
            f"{entry.character_id}={entry.state_mode.value}:{entry.reasons[0]}"
            for entry in assignments.entries
        ),
        artifact_ids=tuple(entry.character_id for entry in assignments.entries),
    )


def passive_stage(assignments: SpotlightAssignments) -> TickStageResult:
    return stage(
        "passive_execution",
        audit_log=(
            f"passive={','.join(assignments.passive_ids) or '-'}",
            f"dormant={','.join(assignments.dormant_ids) or '-'}",
        ),
        artifact_ids=(*assignments.passive_ids, *assignments.dormant_ids),
    )


def apply_world_rules_stage(
    world: WorldState,
    tick: int,
    granularity: GranularityDecision,
    event_snapshot: EventPoolSnapshot,
    assignments: SpotlightAssignments,
    action_results: tuple[ActionResult, ...],
    rule_engine: RuleEngine,
) -> tuple[WorldState, TickStageResult]:
    context = RuleContext(
        tick=tick,
        seed=world.seed,
        metadata={
            "granularity": granularity.granularity.value,
            "event_ids": tuple(event.id for event in event_snapshot.active_events),
            "active_ids": assignments.active_ids,
            "passive_ids": assignments.passive_ids,
            "dormant_ids": assignments.dormant_ids,
            "action_results": action_result_summaries(action_results),
        },
    )
    result = rule_engine.settle(world, context)
    updated_world = apply_state_changes(world, result.state_changes)
    return updated_world, stage(
        "world_rules",
        audit_log=rule_audit_entries(result.audit_log),
        state_changes=result.state_changes,
        artifact_ids=tuple(record.rule_name for record in result.audit_log),
    )


def persistence_stage(tick: int, checkpoint_saved: bool) -> TickStageResult:
    return stage(
        "persistence",
        audit_log=(f"snapshot={tick}", f"checkpoint={'yes' if checkpoint_saved else 'no'}"),
        artifact_ids=(str(tick),),
    )


def replay_audit_stage(tick: int, persisted: bool) -> TickStageResult:
    flag = "persisted" if persisted else "skipped"
    return stage("replay_audit", audit_log=(f"tick={tick}", f"audit={flag}"))


def active_audit_entries(
    character_id: str,
    context: CharacterKnowledgeContext,
    result: ActionResult,
    mutation: KnowledgeMutation,
) -> tuple[str, ...]:
    return (
        f"character={character_id}",
        f"context_facts={','.join(item.entry_id for item in context.facts) or '-'}",
        f"context_clues={','.join(item.entry_id for item in context.clues) or '-'}",
        f"verdict={result.verdict.value}",
        *mutation.audit_log,
    )


def collect_state_changes(results: list[ActionResult]) -> tuple[StateChange, ...]:
    changes = []
    for result in results:
        changes.extend(result.state_changes)
    return tuple(changes)


def action_result_summaries(results: tuple[ActionResult, ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "character_id": result.action.character_id,
            "action_type": result.action.action_type,
            "verdict": result.verdict.value,
            "state_change_count": len(result.state_changes),
            "source_event_id": result.action.source_event_id,
        }
        for result in results
    )


def knowledge_artifact_ids(
    event_mutation: KnowledgeMutation,
    diffusion_mutation: KnowledgeMutation,
    world: WorldState,
) -> tuple[str, ...]:
    ids = [fact.id for fact in event_mutation.facts]
    ids.extend(belief.belief_id for belief in diffusion_mutation.beliefs)
    ids.extend(task.task_id for task in world.pending_propagation)
    return tuple(ids)


def phenology_audit_entries(audit_log) -> tuple[str, ...]:
    return tuple(
        f"{entry.rule_name}:{'matched' if entry.matched else 'skipped'}:{entry.state_change_count}"
        for entry in audit_log
    )


def rule_audit_entries(audit_log: tuple[RuleExecutionRecord, ...]) -> tuple[str, ...]:
    return tuple(
        f"{entry.rule_name}:{'matched' if entry.matched else 'skipped'}:{entry.state_change_count}"
        for entry in audit_log
    )
